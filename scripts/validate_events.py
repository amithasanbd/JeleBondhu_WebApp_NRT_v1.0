#!/usr/bin/env python3
"""Event-grouped validation of the thesis seasonal PAI against the 2020-2025 in-situ fisheries records.

Why event-grouped: each fishing event (DLC_ID) appears once per species (26 rows). Treating rows as independent would
inflate confidence 26-fold. Here every statistic is computed on ONE ROW PER EVENT, and confidence intervals use a
spatial-block bootstrap (0.5 degree blocks) so that clustered events do not masquerade as independent evidence.

Output: data/static/validation_summary.json (rendered in the web app's Evidence tab).
This is an honest *agreement check*, not proof of predictive skill: PAI is a static 2025 seasonal field and the observations
are sparse, clustered and have known data-quality issues (reported below).
"""
import argparse, datetime as dt, json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEASON = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon", 6: "Monsoon", 7: "Monsoon",
          8: "Monsoon", 9: "Monsoon", 10: "Post-monsoon", 11: "Post-monsoon"}
MAX_KM = 40.0


def hav(la1, lo1, la2, lo2):
    r = np.pi / 180
    a = np.sin((la2 - la1) * r / 2) ** 2 + np.cos(la1 * r) * np.cos(la2 * r) * np.sin((lo2 - lo1) * r / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def spearman(a, b):
    a, b = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def block_boot(df, stat, B=2000, seed=1):
    rng = np.random.default_rng(seed)
    groups = [g.index.to_numpy() for _, g in df.groupby("block")]
    out = []
    for _ in range(B):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[k] for k in pick])
        v = stat(df.loc[idx])
        if np.isfinite(v):
            out.append(v)
    if len(out) < 50:
        return (float("nan"), float("nan"))
    return tuple(float(x) for x in np.percentile(out, [2.5, 97.5]))



def seasonal_pai_values(thesis, stations, seasons, positions):
    """Resolve seasonal PAI by position or station ID without inventing missing values.

    Supports legacy arrays (PAI x1000) and explicitly labelled dictionaries.
    Missing/invalid entries remain NaN. A dictionary may use station IDs or
    zero-based position strings; station IDs take precedence.
    """
    payload = thesis.get("pai", {})
    ids = stations.get("id", stations.get("station_id"))
    if ids is None:
        ids = list(range(1, len(stations["lat"]) + 1))
    if len(ids) != len(stations["lat"]):
        raise ValueError("Station ID and coordinate array lengths differ")
    unit = str(thesis.get("unit", "")).lower()
    fraction = any(token in unit for token in ("fraction", "0-1", "0 to 1"))
    milliscale = "x1000" in unit or "1000" in unit
    if not (fraction or milliscale):
        raise ValueError("Unknown PAI unit: declare 'PAI x1000' or 'PAI fraction (0-1)'")
    result = []
    for season, pos in zip(seasons, positions):
        pos = int(pos)
        series = payload.get(season)
        if series is None:
            result.append(np.nan)
            continue
        if isinstance(series, list):
            raw = series[pos] if 0 <= pos < len(series) else None
        elif isinstance(series, dict):
            sid = str(ids[pos])
            # ID first; positional fallback only when the dictionary explicitly
            # identifies itself as position-keyed.
            if thesis.get("key_type") == "position":
                raw = series.get(str(pos))
            else:
                raw = series.get(sid)
        else:
            raise ValueError(f"Unsupported seasonal PAI type for {season}: {type(series).__name__}")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float("nan")
        if not np.isfinite(value) or value < 0:
            result.append(np.nan)
            continue
        result.append(value if fraction else value / 1000.0)
    return np.asarray(result, dtype=float)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx")
    ap.add_argument("--out", default=str(ROOT / "data/static/validation_summary.json"))
    a = ap.parse_args()
    try:  # workbook contains chartsheets that confuse openpyxl
        from openpyxl.reader.excel import ExcelReader
        ExcelReader.read_chartsheet = lambda self, *x, **k: None
    except Exception:
        pass
    xl = a.xlsx or next((ROOT / "data/raw").glob("*Commercial_Fisheries_PlotReady*.xlsx"))
    df = pd.read_excel(xl, engine="openpyxl")
    st = json.load(open(ROOT / "data/static/stations.json"))
    thesis = json.load(open(ROOT / "data/static/thesis_pai_2025.json"))
    slat, slon, sdep = np.array(st["lat"]), np.array(st["lon"]), np.array(st["depth_m"], float)

    # ---------------- data-quality diagnostics (honest reporting) -------------------------------------------------
    dq = []
    ev_rows = df.groupby("DLC_ID").size()
    dq.append(("Rows / events / species", f"{len(df):,} / {df.DLC_ID.nunique():,} / {df.Scientific_Name.nunique()}"))
    dq.append(("Rows per event (median, min-max)", f"{int(ev_rows.median())} ({ev_rows.min()}-{ev_rows.max()})"))
    sst_by_ev = df.groupby("DLC_ID")["SST_Source_C"].nunique()
    dq.append(("Events whose SST value differs between species rows", f"{int((sst_by_ev > 1).sum())} of {len(sst_by_ev)}"))
    cpue_bad = int((~np.isfinite(df.CPUE) | (df.Effort_Value <= 0) | (df.Fishing_Hours <= 0)).sum())
    dq.append(("Distinct fishing-hours values per event (median) - should be 1", f"{int(df.groupby('DLC_ID').Fishing_Hours.nunique().median())}"))
    dq.append(("Distinct effort values per event (median) - should be 1", f"{int(df.groupby('DLC_ID').Effort_Value.nunique().median())}"))
    spm = df.groupby("Scientific_Name").CPUE.mean()
    dq.append(("Spread of species-mean CPUE (CV across 26 species)", f"{spm.std() / spm.mean():.3f}  (real catches are far more unequal between species)"))
    tot = df.groupby("DLC_ID").CPUE.sum()
    dq.append(("Spread of event-total CPUE (CV across events)", f"{tot.std() / tot.mean():.3f}"))
    dq.append(("Rows with undefined CPUE (effort/hours <= 0 or missing)", f"{cpue_bad}"))
    dq.append(("Distinct SST values (rows)", f"{df.SST_Source_C.nunique()} distinct of {len(df)}"))
    dq.append(("Months with no records", ", ".join(str(m) for m in range(1, 13) if m not in set(df.Month)) or "none"))
    dq.append(("Season coverage flags", ", ".join(f"{k}: {v}" for k, v in df.drop_duplicates("DLC_ID").Season_Coverage.value_counts().items())))

    # ---------------- event table (one row per event) ----------------------------------------------------------------
    ev = df.groupby("DLC_ID").agg(lat=("Latitude_dd", "first"), lon=("Longitude_dd", "first"), month=("Month", "first"),
                                  year=("Calendar_Year", "first"), cpue=("CPUE", "sum"), nsp=("Catch_kg", lambda s: int((s > 0).sum()))).reset_index()
    ev["season"] = ev.month.map(SEASON)
    D = hav(ev.lat.to_numpy()[:, None], ev.lon.to_numpy()[:, None], slat[None, :], slon[None, :])
    j = D.argmin(axis=1)
    ev["km"] = D[np.arange(len(ev)), j]
    ev["st"] = j
    ev["depth"] = sdep[j]
    ev["pai"] = seasonal_pai_values(thesis, st, ev.season, ev.st)
    keep = (ev.km <= MAX_KM) & np.isfinite(ev.pai) & np.isfinite(ev.cpue)
    n_all = len(ev)
    ev = ev[keep].reset_index(drop=True)
    ev["block"] = (np.floor(ev.lat / 0.5).astype(int).astype(str) + "_" + np.floor(ev.lon / 0.5).astype(int).astype(str))
    dq.append((f"Events matched to a thesis station within {MAX_KM:.0f} km", f"{len(ev)} of {n_all}"))
    dq.append(("Spatial blocks (0.5 deg) containing events", f"{ev.block.nunique()}"))

    rows = []
    rho = spearman(ev.pai, ev.cpue)
    lo, hi = block_boot(ev, lambda d: spearman(d.pai, d.cpue))
    rows.append(("Spearman rho: PAI vs event CPUE (all seasons)", f"{rho:+.3f}  [95% block-bootstrap CI {lo:+.3f}, {hi:+.3f}]"))
    rng = np.random.default_rng(7)
    perm = []
    for _ in range(2000):
        p = ev.copy()
        p["pai"] = p.groupby("season")["pai"].transform(lambda s: rng.permutation(s.to_numpy()))
        perm.append(spearman(p.pai, p.cpue))
    pval = float((np.abs(perm) >= abs(rho)).mean())
    rows.append(("Permutation p-value (shuffling PAI within season)", f"{pval:.3f}  (ignores spatial autocorrelation: treat as optimistic)"))
    rows.append(("Baseline: Spearman rho of station depth vs event CPUE", f"{spearman(ev.depth, ev.cpue):+.3f}"))
    hil = df[df.Scientific_Name == "Tenualosa ilisha"][["DLC_ID", "CPUE"]].rename(columns={"CPUE": "hilsa"})
    ev = ev.merge(hil, on="DLC_ID", how="left")
    h_ok = ev.dropna(subset=["hilsa"]).reset_index(drop=True)
    hl, hh = block_boot(h_ok, lambda d: spearman(d.pai, d.hilsa), B=1000)
    rows.append((f"Hilsa-only: Spearman rho PAI vs hilsa CPUE (n={len(h_ok)})", f"{spearman(h_ok.pai, h_ok.hilsa):+.3f}  [{hl:+.3f}, {hh:+.3f}]"))
    for s in ["Winter", "Pre-monsoon", "Monsoon", "Post-monsoon"]:
        d = ev[ev.season == s].reset_index(drop=True)
        if len(d) >= 12:
            l, h = block_boot(d, lambda x: spearman(x.pai, x.cpue), B=1000)
            rows.append((f"  {s} (n={len(d)})", f"{spearman(d.pai, d.cpue):+.3f}  [{l:+.3f}, {h:+.3f}]"))
        else:
            rows.append((f"  {s} (n={len(d)})", "too few events"))
    t = ev.pai.quantile([1 / 3, 2 / 3]).to_numpy()
    top, bot = ev[ev.pai >= t[1]].cpue, ev[ev.pai <= t[0]].cpue
    def ratio(d):
        tp, bt = d[d.pai >= d.pai.quantile(2 / 3)].cpue.median(), d[d.pai <= d.pai.quantile(1 / 3)].cpue.median()
        return tp / bt if bt > 0 else float("nan")
    rl, rh = block_boot(ev, ratio, B=1000)
    rows.append(("Median CPUE ratio, top vs bottom PAI tercile", f"{ratio(ev):.2f}  [{rl:.2f}, {rh:.2f}]  (n={len(top)} vs {len(bot)})"))

    verdict = ("The CI includes zero: the thesis PAI shows NO demonstrated agreement with observed event CPUE in this sample."
               if lo <= 0 <= hi else
               ("Positive rank agreement (CI above zero), modest and descriptive only." if lo > 0 else
                "Negative rank agreement (CI below zero): PAI is inversely related to observed CPUE in this sample - do not present PAI as a catch predictor."))
    out = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "method": "One row per event (DLC_ID); nearest thesis station <= 40 km; seasonal PAI 2025; spatial-block bootstrap (0.5 deg).",
           "sections": [
               {"title": "Agreement of thesis PAI with observed CPUE (event-grouped)", "rows": rows,
                "notes": [verdict, "Static 2025 seasonal PAI vs 2020-2025 events; sparse, clustered, not independent of fishing-ground choice (fishers go where fish usually are). This is an agreement check, NOT proof of predictive skill and NOT a validation of the live experimental Filter 1."]},
               {"title": "Data-quality diagnostics of the in-situ workbook", "rows": dq,
                "notes": ["Effort and hours differ between species rows of the SAME event and all species have near-equal mean CPUE: this is inconsistent with real one-operation-per-event logbook data. Re-check the workbook against the original logbooks before any calibration; until then a null result here cannot be attributed to the PAI alone."]}]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:3500])


if __name__ == "__main__":
    main()
