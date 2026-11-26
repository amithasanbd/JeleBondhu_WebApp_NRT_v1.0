"""End-to-end NRT run: ingest -> harmonise -> three filters -> decision -> versioned bundle."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import SCHEMA_VERSION, __version__, filter1, filter2, filter3, geo
from .bmd import BmdState
from .config import Config, mask_of
from .engine import (S_, C_, U_, LETTERS, SEASON_OF_MONTH, Stations, choose_rep_points, combine_confidence, confidence_components,
                     decide, load_stations, pick_zones, sample_environment)
from .fields import Bathymetry
from .ingest_cmems import CmemsResult
from .ingest_openmeteo import HazardSet
from .reference import load_reference

DHAKA = dt.timezone(dt.timedelta(hours=6))

HEADLINES = {
    "S": ("Conditions look favourable for the zones listed. Check the official BMD warning before you leave.",
          "তালিকার এলাকাগুলোর জন্য অবস্থা অনুকূল। রওনা দেওয়ার আগে আবহাওয়া অধিদপ্তরের সতর্কবার্তা দেখে নিন।"),
    "C": ("Be careful. Conditions are marginal. Check official warnings and consider other zones.",
          "সতর্ক থাকুন। অবস্থা সীমারেখায়। সরকারি সতর্কবার্তা দেখুন এবং অন্য এলাকা ভাবুন।"),
    "N": ("Do not go. Conditions are dangerous or fishing is not allowed.",
          "যাবেন না। অবস্থা বিপজ্জনক অথবা মাছ ধরা নিষেধ।"),
    "U": ("No reliable advice right now. Follow the official BMD warning and local flag signals.",
          "এখন নির্ভরযোগ্য পরামর্শ নেই। আবহাওয়া অধিদপ্তরের সতর্কবার্তা ও স্থানীয় সংকেত মেনে চলুন।"),
}
SMS_STATE = {"S": ("অনুকূল", "FAVOURABLE"), "C": ("সতর্ক", "CAUTION"), "N": ("যাবেন না", "DO NOT GO"), "U": ("পরামর্শ নেই", "NO ADVICE")}


def _ints(a: np.ndarray, scale: float = 1.0, nan: int = -1) -> List[int]:
    a = np.asarray(a, float)
    return np.where(np.isfinite(a), np.rint(a * scale), nan).astype(int).tolist()


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf8")


def _letters(cls: np.ndarray) -> str:
    return "".join(LETTERS[cls])


class Bundle:
    def __init__(self):
        self.files: Dict[str, bytes] = {}
        self.qc: Dict[str, Any] = {}
        self.meta: Dict[str, Any] = {}

    def add(self, rel: str, obj):
        self.files[rel] = _dump(obj)


def publication_times(now: dt.datetime, bmd: BmdState, pl: dict):
    """Never advertise a positive class beyond the human BMD verification/validity.

    The browser withdraws positive classes at ``stale_after``. Therefore both
    valid_until AND stale_after must be capped by the *earliest* of the
    bulletin expiration, verification age and bulletin issue-time limit.
    """
    valid = now + dt.timedelta(hours=pl["bundle_valid_hours"])
    stale = now + dt.timedelta(hours=pl["stale_after_hours"])
    expire = now + dt.timedelta(hours=pl["expire_after_hours"])
    if bmd.verified:
        bounds = []
        for name in ("valid_to", "verified_at", "issued_at"):
            raw = bmd.record.get(name)
            if not raw:
                continue
            try:
                stamp = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=DHAKA)
                stamp = stamp.astimezone(dt.timezone.utc)
                if name != "valid_to":
                    stamp += dt.timedelta(hours=pl["bmd"]["max_verification_age_h"])
                bounds.append(stamp)
            except (ValueError, TypeError):
                continue
        if not bounds:
            # A record without trustworthy date metadata cannot grant a
            # positive clearance, even if a fabricated BmdState says verified.
            stale = min(stale, now)
            valid = min(valid, now)
        else:
            deadline = min(bounds)
            valid = min(valid, deadline)
            stale = min(stale, deadline)
    return valid, stale, expire


# ----------------------------------------------------------------------------
def run_pipeline(cfg: Config, now: dt.datetime, cmems: Optional[CmemsResult], hazards: Optional[HazardSet], bmd: BmdState,
                 mode: str = "live", probe: Optional[dict] = None, log=print) -> Bundle:
    """Compute a complete advisory bundle. ``mode`` is 'live' or 'demo' (synthetic data, never publish as live)."""
    t_start = dt.datetime.now(dt.timezone.utc)
    root = cfg.root
    pl = cfg.pipeline
    bundle = Bundle()
    demo = mode != "live"
    now = now.astimezone(dt.timezone.utc)
    now_h = int(now.timestamp() // 3600)
    month_local = now.astimezone(DHAKA).month
    season = SEASON_OF_MONTH[month_local]

    st = load_stations(cfg)
    bathy = Bathymetry(root / "data/spatial/bathy_grid.npz")
    sctx = filter3.SpatialContext.load(root)
    rules_status, rules_problems = filter3.validate_ruleset(cfg.rules, now.astimezone(DHAKA).date())
    ref = load_reference(root, st.n)
    # A climatology file alone DOES NOT establish the original frozen thesis
    # AHP/TOPSIS/membership functions. This codebase implements only the
    # transparent reconstruction and cannot issue a "frozen/validated" label.
    f1_mode = "experimental"
    if cfg.filter1.get("mode") == "frozen":
        log("Frozen PAI requested but exact thesis algorithm is not implemented; retaining EXPERIMENTAL status")
    log(f"stations={st.n} rules={rules_status} reference={'yes' if ref else 'no'} F1 mode={f1_mode} season={season}")

    # --------------------------------------------------------------------- Filter 1
    wet = bathy.is_wet(st.lat, st.lon, pl["station_min_depth_m"]) & st.in_eez
    var = sample_environment(cfg, cmems, st, bathy, month_local, ref)
    f1 = filter1.compute(cfg.filter1, var, wet, have_reference=ref is not None)
    pai = f1["PAI"]
    cls1 = filter1.classify(cfg.filter1, pai, f1_mode)
    comp_ids, drv_pos, drv_neg = filter1.drivers(cfg.filter1, f1["contrib"], wet)
    thesis = None
    tp = root / "data/static/thesis_pai_2025.json"
    if tp.exists():
        arr = np.array(json.load(open(tp))["pai"][season], float)
        arr[arr < 0] = np.nan
        thesis = arr / 1000.0
    agreement = filter1.spearman(pai, thesis) if thesis is not None else None

    # --------------------------------------------------------------------- static spatial info (Filter 3)
    sp = sctx.station_info(st.lat, st.lon, cfg.filter3["mpa"]["legal_status_effect"], cfg.filter3["mpa"]["buffer_applies_to"])
    gnames = [[g["props"]["name"] for j, g in enumerate(sctx.grounds) if (sp["ground_mask"][i] >> j) & 1] for i in range(st.n)]
    depth = var["depth"]
    depth_ok = np.isfinite(depth)

    # --------------------------------------------------------------------- hazards
    hf = None
    if hazards is not None and hazards.valid_fraction() > 0:
        hf = filter2.HazardField(hazards, np.datetime64(now.replace(tzinfo=None), "h"), pl["idw"], cfg.filter2["thunderstorm_weather_codes"])
        log(f"hazard horizon: {hf.H} h from {hf.t[0]}")
    H = hf.H if hf is not None else 0
    H_trip = min(H, 96)  # seven-day weather outlook is separate; near-term trip model only

    # --------------------------------------------------------------------- per port / vessel / departure
    departs = pl["depart_offsets_h"]
    Kp = pl["route_samples"] + 1
    advisories: Dict[str, Any] = {}
    lite: Dict[str, Any] = {}
    sms: Dict[str, Any] = {}
    class_stats: Dict[str, Any] = {}
    conf_global: Dict[str, Any] = {}
    unverified_blocks = pl["bmd"].get("unverified_blocks", ["S", "C"])
    all_cls_default = None

    for port_id, port in cfg.ports["ports"].items():
        # Separate seven-day marine-weather OUTLOOK. It is NOT a fishing-clearance
        # decision and never reuses today's PAI as tomorrow's catch forecast.
        seven_day_outlook = []
        if hf is not None:
            en = port["entry"]
            entry_hz, _ = hf.at(np.array([en["lat"]]), np.array([en["lon"]]))
            for day in range(7):
                a, b = day * 24, min((day + 1) * 24, H)
                if a >= b:
                    break
                def aggregate(key, kind="max"):
                    values = entry_hz[key][0, a:b]
                    finite = values[np.isfinite(values)]
                    if finite.size < max(6, (b - a) * .75):
                        return None
                    val = float(np.min(finite) if kind == "min" else np.max(finite))
                    return round(val, 1)
                seven_day_outlook.append({
                    "day": day + 1, "start_utc": str(hf.t[a]) + ":00Z",
                    "hours_covered": b - a,
                    "max_wave_m": aggregate("wave_height_m"),
                    "max_wind_ms": aggregate("wind_speed_ms"),
                    "max_gust_ms": aggregate("wind_gust_ms"),
                    "min_visibility_km": aggregate("visibility_km", "min"),
                    "thunder_predicted": bool(aggregate("thunderstorm") > 0) if aggregate("thunderstorm") is not None else None,
                    "type": "weather_outlook_only", "official_clearance": False
                })
        routes = filter2.build_routes(cfg, bathy, port_id, st.lat, st.lon)
        if hf is not None:
            hz_pts, support_pts = hf.at(routes.lat.ravel(), routes.lon.ravel(), hours=H_trip)
            hz_pts = {k: v.reshape(st.n, Kp, H_trip) for k, v in hz_pts.items()}
            support_cell = support_pts.reshape(st.n, Kp).min(axis=1)
            bmd_cls = bmd.class_at(routes.lat, routes.lon)
        for vessel_id, vessel in cfg.vessels["vessels"].items():
            key = f"{vessel_id}__{port_id}"
            if hf is not None:
                sc = filter2.hazard_scores(vessel, {k: v.reshape(st.n * Kp, H_trip) for k, v in hz_pts.items()}, tuple(cfg.filter2["lower_is_worse"]))
                sc = {k: v.reshape(st.n, Kp, H_trip) for k, v in sc.items()}
                sphys = filter2.s_phys(sc)
            dep_out = []
            for d in departs:
                if hf is not None and H_trip - d >= 6:
                    r2 = filter2.evaluate_trip(cfg, vessel_id, routes, sphys, sc, d, H_trip, bmd, bmd_cls)
                    support = support_cell
                else:
                    spd = vessel["speed_kn"]
                    Rt = 2 * routes.dist_nm / spd + vessel["fishing_hours"]
                    r2 = {"state": np.full(st.n, filter2.UNKNOWN, dtype=np.int8),
                          "mask": np.full(st.n, mask_of(cfg, "DATA_HAZARD_MISSING", "BMD_UNVERIFIED") if not bmd.verified else mask_of(cfg, "DATA_HAZARD_MISSING"), dtype=np.int64),
                          "S": np.zeros(st.n), "s_trip": np.full(st.n, np.nan), "W_h": np.full(st.n, np.nan),
                          "margin_h": np.full(st.n, np.nan), "R_T": Rt, "dist_nm": routes.dist_nm,
                          "in_range": routes.dist_nm <= vessel["max_range_nm"], "horizon_limited": np.zeros(st.n, bool)}
                    support = np.zeros(st.n)
                R_T = r2["R_T"]
                t0 = np.full(st.n, float(now_h + d))
                r3 = filter3.evaluate(cfg, cfg.rules, rules_status, sp, vessel_id, t0, t0 + R_T, depth_ok)
                comps, env_age = confidence_components(cfg, now, cmems, hazards if hf is not None else None, f1, f1_mode, support,
                                                       d + R_T / 2.0)
                conf = combine_confidence(comps)
                mask = r2["mask"] | r3["mask"]
                if f1_mode == "experimental":
                    mask |= mask_of(cfg, "ENV_EXPERIMENTAL")
                cls, pre, mask = decide(cfg, wet & routes.station_wet, r2["in_range"], r2["state"], r3["state"], pai, cls1["cls"], conf,
                                        bmd.verified, mask, bmd_block=tuple(unverified_blocks))
                # A bulletin that is valid NOW is not clearance for an entire
                # future fishing trip. Withdraw positive/caution classes whenever
                # the planned return falls outside the bulletin validity window.
                from .bmd import _parse as parse_bmd_time
                try:
                    valid_from = parse_bmd_time(bmd.record.get("valid_from")) if bmd.verified else None
                    valid_to = parse_bmd_time(bmd.record.get("valid_to")) if bmd.verified else None
                except (TypeError, ValueError):
                    valid_from, valid_to = None, None
                starts_at = now + dt.timedelta(hours=int(d))
                if valid_from is not None and valid_to is not None:
                    covered = np.isfinite(R_T) & (starts_at >= valid_from) & (
                        (now.timestamp() / 3600.0 + d + np.asarray(R_T, dtype=float)) <= valid_to.timestamp() / 3600.0
                    )
                else:
                    covered = np.zeros(st.n, dtype=bool)
                not_covered = ~covered
                cls = np.where(not_covered & np.isin(cls, (S_, C_)), U_, cls)
                mask |= np.where(not_covered, mask_of(cfg, "BMD_UNVERIFIED"), 0)
                S = np.nan_to_num(r2["S"])
                U = r3["U"]
                A = np.where(np.isin(pre, (0, 1)), np.nan_to_num(pai) * np.minimum(S, U), 0.0)
                zones_all = pick_zones(st, cls, A, r2["dist_nm"], R_T, np.nan_to_num(pai), S, U, mask, gnames, n=3, pre=pre)
                zones = [z for z in zones_all if z["kind"] in ("safe", "caution")]
                pending = [z for z in zones_all if z["kind"] == "pending_official_check"]
                counts = {LETTERS[i]: int((cls == i).sum()) for i in range(6)}
                best = "S" if counts["S"] else "C" if counts["C"] else "U" if counts["U"] else "N" if counts["N"] else "U"
                sel = cls == "SCNURL".index(best)
                why = []
                if best != "S" and sel.any():
                    mm = mask[sel]
                    wanted = {"N": {"bad"}, "U": {"unknown"}, "C": {"warn", "bad"}}.get(best, set())
                    for code in cfg.reasons["codes"]:
                        if code["severity"] not in wanted or code["code"] == "JATKA_RISK":
                            continue
                        k = int(((mm >> code["bit"]) & 1).sum())
                        if k:
                            why.append({"bit": code["bit"], "n": k, "share": round(k / int(sel.sum()), 2)})
                    why.sort(key=lambda w: -w["n"])
                    why = why[:4]
                bmd_pending = max(0, int(((pre == S_) | (pre == C_)).sum() - ((cls == S_) | (cls == C_)).sum()))
                depart_dt = (now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=d)).astimezone(DHAKA)
                dep_out.append({
                    "offset_h": d, "depart_bdt": depart_dt.strftime("%Y-%m-%d %H:%M"),
                    "c": _letters(cls), "pre": _letters(pre), "s": _ints(S, 100), "u": _ints(U, 100), "a": _ints(A, 1000),
                    "rt": _ints(R_T if np.ndim(R_T) else np.full(st.n, R_T), 1), "d": _ints(r2["dist_nm"], 1),
                    "m": _ints(np.clip(r2["margin_h"], -99, 99), 1, nan=-100), "cf": _ints(conf, 100), "rb": mask.astype(np.int64).tolist(),
                    "route_ok": int(routes.route_ok.sum()), "zones": zones, "zones_pending": pending, "counts": counts, "overall": best,
                    "jatka_active": bool(r3["jatka_active"].any()), "why": why, "bmd_pending": bmd_pending,
                })
                if vessel_id == cfg.vessels["default_vessel"] and d == 0 and all_cls_default is None:
                    all_cls_default = cls.copy()
                    conf_global = {k: (round(float(np.nanmedian(np.asarray(v, float)[wet])), 3) if wet.any() else None) for k, v in comps.items()}
                    conf_global["env_age_h"] = env_age
                class_stats[f"{key}@{d}"] = counts
            advisories[key] = dep_out
            # ---------- fisher-lite summary
            hazard_sum = None
            if hf is not None:
                sp0 = sphys[0, 0, :]                    # entry point (same for every station of the port)
                def first_h(th):
                    idx = np.where(np.nan_to_num(sp0, nan=1.0) <= th)[0]
                    return int(idx[0]) if len(idx) else None
                H24 = min(24, H)
                hazard_sum = {
                    "max_wave_m": round(float(np.nanmax(hz_pts["wave_height_m"][0, 0, :H24])), 1),
                    "max_wind_ms": round(float(np.nanmax(hz_pts["wind_speed_ms"][0, 0, :H24])), 1),
                    "max_gust_ms": round(float(np.nanmax(hz_pts["wind_gust_ms"][0, 0, :H24])), 1),
                    "min_vis_km": round(float(np.nanmin(hz_pts["visibility_km"][0, 0, :H24])), 1) if np.isfinite(hz_pts["visibility_km"][0, 0, :H24]).any() else None,
                    "thunder_24h": bool(np.nanmax(np.nan_to_num(hz_pts["thunderstorm"][0, 0, :H24])) > 0),
                    "first_stop_h": first_h(0.0), "first_caution_h": first_h(cfg.filter2["caution_below"]),
                }
            lite[key] = {"v": 1, "vessel": vessel_id, "port": port_id,
                         "departs": [{"offset_h": x["offset_h"], "depart_bdt": x["depart_bdt"], "overall": x["overall"],
                                      "headline_en": HEADLINES[x["overall"]][0], "headline_bn": HEADLINES[x["overall"]][1],
                                      "zones": x["zones"], "counts": x["counts"], "why": x["why"],
                                      "bmd_pending": x["bmd_pending"], "jatka_active": x["jatka_active"]} for x in dep_out],
                         "hazard24": hazard_sum, "outlook7": seven_day_outlook}
            d0 = dep_out[0]
            ov = d0["overall"]
            zt = ""
            if d0["zones"]:
                z = d0["zones"][0]
                zt_bn = f" এলাকা {z['lat']:.2f}N {z['lon']:.2f}E, {z['dist_nm']} নটিক্যাল মাইল।"
                zt_en = f" Zone {z['lat']:.2f}N {z['lon']:.2f}E, {z['dist_nm']} NM."
            else:
                zt_bn, zt_en = "", ""
            sms[key] = {"bn": f"জেলেবন্ধু {port['name_bn']}: {SMS_STATE[ov][0]}।{zt_bn} সরকারি সতর্কবার্তা দেখুন।",
                        "en": f"JeleBondhu {port['name_en']}: {SMS_STATE[ov][1]}.{zt_en} Check official BMD warning."}

    # --------------------------------------------------------------------- QC / publication gate
    qc = run_qc(cfg, pai, cls1["cls"], wet, hazards, hf, rules_status, advisories, mode)
    bundle.qc = qc

    # --------------------------------------------------------------------- files
    gen = dt.datetime.now(dt.timezone.utc)
    bundle_id = now.strftime("%Y%m%dT%H%MZ") + "-" + hashlib.sha256((cfg.config_hash + str(now_h)).encode()).hexdigest()[:6]
    valid_until, stale_at, expire_at = publication_times(now, bmd, pl)
    f1_label = (cfg.filter1["label_frozen_en"] if f1_mode == "frozen" else cfg.filter1["label_experimental_en"])
    f1_label_bn = cfg.filter1["label_experimental_bn"] if f1_mode != "frozen" else cfg.filter1["label_frozen_en"]

    cells = {
        "n": st.n, "mode": f1_mode, "label_en": f1_label, "label_bn": f1_label_bn, "meaning": cfg.filter1["output_meaning"],
        "pai": _ints(pai, 100), "ppi": _ints(f1["S"]["PPI"], 100), "pfzi": _ints(f1["S"]["PFZI"], 100),
        "ohi": _ints(f1["S"]["OHI"], 100), "vi": _ints(f1["S"]["VI"], 100), "pcls": cls1["cls"].astype(int).tolist(),
        "p60": cls1["p60"], "p80": cls1["p80"],
        "sst": _ints(var.get("sst", np.full(st.n, np.nan)), 10), "sss": _ints(var.get("sss", np.full(st.n, np.nan)), 10),
        "chl": _ints(var.get("chl", np.full(st.n, np.nan)), 100), "cur": _ints(var.get("current_speed", np.full(st.n, np.nan)), 100),
        "o2": _ints(var.get("o2", np.full(st.n, np.nan)), 1), "ph": _ints(var.get("ph", np.full(st.n, np.nan)), 100),
        "wet": wet.astype(int).tolist(), "ifa": sp["in_ifa"].astype(int).tolist(), "gm": sp["ground_mask"].astype(int).tolist(),
        "mpa": sp["mpa_idx"].astype(int).tolist(), "mpa_state": sp["mpa_state"].astype(int).tolist(),
        "dmpa": _ints(np.minimum(sp["dist_mpa_km"], 999), 1), "hilsa_zone": ((depth <= 50) | sp["in_ifa"]).astype(int).tolist(),
        "depth": _ints(depth, 1, nan=0), "drv_comp": comp_ids, "drv_pos": drv_pos.astype(int).ravel().tolist(),
        "drv_neg": drv_neg.astype(int).ravel().tolist(), "thesis_season": season,
        "thesis_pai": _ints(thesis, 1000) if thesis is not None else None,
    }
    bundle.add("cells.json", cells)
    bundle.add("reasons.json", cfg.reasons)

    for key, dep in advisories.items():
        bundle.add(f"advisory/{key}.json", {"v": 1, "key": key, "bundle_id": bundle_id, "departs": dep})
        bundle.add(f"lite/{key}.json", {**lite[key], "bundle_id": bundle_id})
    bundle.add("sms.json", {"note": "SMS-ready texts (no gateway connected). Bangla uses UCS-2: ~70 chars per segment.", "items": sms,
                           "bundle_id": bundle_id})

    if hazards is not None:
        bundle.add("hazard.json", hazard_payload(hazards, hf))

    warnings = {
        "bmd": {"verified": bmd.verified, "reason": bmd.reason, "record": bmd.record, "probe": probe},
        "rules": {"status": rules_status, "problems": rules_problems, "rules_version": cfg.rules["rules_version"],
                  "reviewed_at": cfg.rules["reviewed_at"], "review_due": cfg.rules["review_due"], "regimes": cfg.rules["regimes"],
                  "rules": cfg.rules["rules"], "vessel_zone_rules": cfg.rules["vessel_zone_rules"],
                  "unevaluated": cfg.rules["unevaluated_regimes"]},
        "mpas": [{"id": m["props"]["id"], "name": m["props"]["name"], "legal_status": m["props"]["legal_status"],
                  "reported_km2": m["props"]["reported_km2"], "computed_km2": m["props"]["computed_km2"],
                  "geometry_valid": m["valid"], "stations_inside": int(((sp["mpa_idx"] == i)).sum()), "note": m["props"]["note"]}
                 for i, m in enumerate(sctx.mpas)],
    }
    bundle.add("warnings.json", warnings)

    prov = {
        "schema_version": SCHEMA_VERSION, "app_release": pl["release"], "backend_version": __version__,
        "git_sha": os.environ.get("GITHUB_SHA", "")[:12], "config_hash": cfg.config_hash,
        "rules_version": cfg.rules["rules_version"], "spatial_version": sctx.version,
        "mode": mode, "filter1": {"mode": f1_mode, "label": f1_label, "components_used": f1["used_vars"],
                                 "weights": {k: v["weight"] for k, v in cfg.filter1["subindices"].items()},
                                 "p60": cls1["p60"], "p80": cls1["p80"], "agreement_with_thesis_season_spearman": agreement,
                                 "agreement_note": "Informational spatial rank correlation with the thesis 2025 seasonal PAI; not a validation.",
                                 "status": cfg.filter1["_status"]},
        "filter2": {"status": cfg.filter2["_status"], "vessels": cfg.vessels["vessels"], "vessel_status": cfg.vessels["_status"]},
        "filter3": {"status": cfg.filter3["_status"], "components": {"u_buf": "assessed", "u_crowd": "not_assessed", "u_life": "not_assessed"}},
        "sources": {
            "cmems": {"used": cmems is not None and bool(cmems.fields), "valid_time": cmems.valid_time.isoformat() if cmems and cmems.valid_time else None,
                      "datasets": cmems.status if cmems else {}, "attribution": pl["cmems"]["attribution"]},
            "open_meteo": {"used": hazards is not None, "fetched_at": hazards.fetched_at.isoformat() if hazards else None,
                           "points": int(hazards.npts) if hazards else 0, "horizon_h": H, "attribution": pl["openmeteo"]["attribution"],
                           "errors": hazards.errors[:5] if hazards else []},
            "bmd": {"verified": bmd.verified, "reason": bmd.reason, "record_issued": bmd.record.get("issued_at"),
                    "verified_by": bmd.record.get("verified_by"), "verified_at": bmd.record.get("verified_at")},
        },
        "confidence_median_default_trip": conf_global, "qc": qc,
        "disclaimer_en": "Research prototype. Not an official weather warning, navigation aid or legal advice. SAFE means model-assessed conditions are favourable - never a guarantee. Always follow BMD warnings, local signals and fisheries law.",
        "disclaimer_bn": "এটি গবেষণা প্রোটোটাইপ। এটি সরকারি আবহাওয়া সতর্কবার্তা, নৌচলাচল সহায়তা বা আইনি পরামর্শ নয়। 'অনুকূল' মানে নিরাপত্তার নিশ্চয়তা নয়। সর্বদা আবহাওয়া অধিদপ্তরের সতর্কবার্তা, স্থানীয় সংকেত ও মৎস্য আইন মেনে চলুন।",
    }
    bundle.add("provenance.json", prov)

    ports_meta = {k: {"name_en": v["name_en"], "name_bn": v["name_bn"], "lat": v["lat"], "lon": v["lon"], "entry": v["entry"], "site": v["site"]}
                  for k, v in cfg.ports["ports"].items()}
    vessels_meta = {k: {"label_en": v["label_en"], "label_bn": v["label_bn"], "speed_kn": v["speed_kn"], "fishing_hours": v["fishing_hours"],
                        "max_range_nm": v["max_range_nm"], "hazards": v["hazards"]} for k, v in cfg.vessels["vessels"].items()}
    status = {"bundle_id": bundle_id, "mode": mode, "generated_at": gen.isoformat(), "analysis_time": now.isoformat(),
              "valid_until": valid_until.isoformat(), "stale_after": stale_at.isoformat(),
              "expire_after": expire_at.isoformat(), "qc_passed": qc["passed"],
              "bmd_verified": bmd.verified, "rules_status": rules_status, "f1_mode": f1_mode}
    bundle.add("status.json", status)
    manifest = {
        **status, "schema_version": SCHEMA_VERSION, "app_release": pl["release"], "rules_version": cfg.rules["rules_version"],
        "spatial_version": sctx.version, "config_hash": cfg.config_hash, "depart_offsets_h": departs, "ports": ports_meta,
        "vessels": vessels_meta, "default_vessel": cfg.vessels["default_vessel"], "n_cells": st.n,
        "files": {rel: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for rel, b in sorted(bundle.files.items())},
        "runtime_s": round((dt.datetime.now(dt.timezone.utc) - t_start).total_seconds(), 1),
    }
    bundle.files["manifest.json"] = _dump(manifest)
    bundle.meta = {"bundle_id": bundle_id, "manifest": manifest}
    return bundle


# ----------------------------------------------------------------------------
def hazard_payload(hs: HazardSet, hf: Optional["filter2.HazardField"]) -> dict:
    """Representative-point series for the dashboard (hourly 72 h, then 3-hourly)."""
    i0 = hf.i0 if hf is not None else 0
    t = hs.t_utc[i0:]
    nt = len(t)
    sel = list(range(min(72, nt))) + list(range(72, nt, 3))
    codes = hs.data["weather_code"][:, i0:]
    th = np.where(np.isfinite(codes), np.isin(codes, [95, 96, 99]).astype(float), np.nan)

    def pack(a, sc):
        return [_ints(row[sel], sc) for row in a[:, i0:]]

    return {"t0_utc": str(t[0]) + ":00Z", "sel_hours": sel,
            "pts": [{"lat": round(float(a), 3), "lon": round(float(b), 3)} for a, b in zip(hs.lat, hs.lon)],
            "wave_m10": pack(hs.data["wave_height"], 10), "wind_ms10": pack(hs.data["wind_speed"], 10),
            "gust_ms10": pack(hs.data["wind_gust"], 10), "vis_km10": pack(hs.data["visibility"], 10),
            "thunder": [_ints(r[sel], 1) for r in th], "wave_dir": pack(hs.data["wave_direction"], 1),
            "units": "tenths of m / m s-1 / km; thunder 0/1; direction degrees; -1 = missing"}


def run_qc(cfg: Config, pai, pcls, wet, hazards, hf, rules_status, advisories, mode) -> dict:
    q = cfg.pipeline["qc"]
    checks = []

    def chk(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    n_wet = int(wet.sum())
    cov = float(np.isfinite(pai[wet]).mean()) if n_wet else 0.0
    chk("pai_coverage", cov >= q["min_wet_cells_with_pai_fraction"], f"{cov:.2f} of wet cells have PAI")
    hv = hazards.valid_fraction() if hazards is not None else 0.0
    chk("hazard_points_valid", hv >= q["min_valid_hazard_points_fraction"], f"{hv:.2f} of representative points valid")
    valid = np.isfinite(pai) & wet
    hi = float((pcls[valid] == 2).mean()) if valid.any() else 0.0
    chk("not_all_high", hi <= q["max_high_class_fraction"], f"high-class fraction {hi:.2f}")
    chk("rules_bundle", rules_status in ("ok",), f"ruleset status: {rules_status}")
    letters = set("".join(d["c"] for dep in advisories.values() for d in dep))
    chk("valid_categories", letters <= set("SCNURL"), f"categories seen: {''.join(sorted(letters))}")
    chk("not_empty", bool(advisories) and any(set(d["c"]) - set("L") for dep in advisories.values() for d in dep), "advisory contains non-land cells")
    # Publication gate: only hard failures block publication. Missing hazards/ocean data still publish
    # (as NO ADVISORY) so the public never sees a stale 'SAFE'.
    hard = ["valid_categories", "not_empty", "not_all_high"]
    if mode == "live":
        # Without a hazard forecast we would publish a blanket NO ADVICE over a previous, still-valid bundle.
        # Failing the gate makes the workflow carry the previous bundle forward (it ages and is down-graded in the browser).
        hard.append("hazard_points_valid")
    passed = all(c["ok"] for c in checks if c["name"] in hard)
    return {"passed": passed, "mode": mode, "checks": checks}
