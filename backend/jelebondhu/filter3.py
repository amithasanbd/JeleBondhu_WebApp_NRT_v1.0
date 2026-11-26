"""Filter 3 - fisheries sustainability and regulatory compliance.

    U = G_MPA * G_season * G_zone * (u_buf * u_crowd * u_life)^(1/3)

* Legal gates come ONLY from the versioned, approved ruleset ``ban_rules_bd.json`` and the
  versioned spatial bundle ``bd_mpas.geojson`` - never from bounding boxes or code constants.
* Crowding and life-stage terms are not assessed (no consented crowding data / authoritative
  nursery polygons) and are excluded from the geometric mean and reported as ``not_assessed``.
* State order: NO-GO(3) > UNKNOWN(2) > CAUTION(1) > PASS(0).  PASS means "no identified
  restriction" - not a licence and not a safety clearance.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import geo
from .config import Config, mask_of

PASS, CAUTION, UNKNOWN, NOGO = 0, 1, 2, 3
STATE_NAMES = {0: "PASS", 1: "CAUTION", 2: "UNKNOWN", 3: "NO-GO"}
DHAKA = dt.timezone(dt.timedelta(hours=6))
REQUIRED_RULE_FIELDS = ["id", "start_date", "end_date", "scope_id", "species", "vessel_types", "gear_types", "effect",
                        "source_ref", "approval_status"]
EFFECTS = {"NO-GO", "CAUTION"}


# ----------------------------------------------------------------------------
# ruleset validation
# ----------------------------------------------------------------------------
def validate_ruleset(rules: dict, today: dt.date) -> Tuple[str, List[str]]:
    """Return ('ok'|'stale'|'invalid', problems)."""
    problems: List[str] = []
    for k in ("schema_version", "rules_version", "spatial_version", "reviewed_at", "review_due", "rules", "regimes"):
        if k not in rules or rules[k] in (None, ""):
            problems.append(f"missing bundle field '{k}'")
    if problems:
        return "invalid", problems
    for r in rules["rules"]:
        for k in REQUIRED_RULE_FIELDS:
            if k not in r or r[k] is None:
                problems.append(f"rule {r.get('id','?')}: missing/null '{k}' (null means unknown, not unrestricted)")
        try:
            s = dt.date.fromisoformat(r["start_date"])
            e = dt.date.fromisoformat(r["end_date"])
            if e < s:
                problems.append(f"rule {r['id']}: end_date before start_date")
        except Exception:
            problems.append(f"rule {r.get('id','?')}: bad date format")
        if r.get("effect") not in EFFECTS:
            problems.append(f"rule {r.get('id','?')}: effect must be one of {sorted(EFFECTS)}")
        if r.get("regime") not in rules["regimes"]:
            problems.append(f"rule {r.get('id','?')}: unknown regime")
    if problems:
        return "invalid", problems
    try:
        due = dt.date.fromisoformat(rules["review_due"])
    except Exception:
        return "invalid", ["bad review_due"]
    if today > due:
        return "stale", [f"ruleset review overdue since {rules['review_due']}"]
    return "ok", []


def _local_hours(t_utc_h: np.ndarray) -> np.ndarray:
    """UTC hours-since-epoch -> Dhaka local hours-since-epoch."""
    return t_utc_h + 6.0


def _date_to_local_hours(d: dt.date) -> float:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() / 3600.0


def _indicative_windows(win: dict, years: range) -> List[Tuple[int, float, float]]:
    sm, sd = map(int, win["start"].split("-"))
    em, ed = map(int, win["end"].split("-"))
    out = []
    for y in years:
        s = dt.date(y, sm, sd)
        e = dt.date(y + 1 if (em, ed) < (sm, sd) else y, em, ed)
        out.append((y, _date_to_local_hours(s), _date_to_local_hours(e) + 24.0))
    return out


# ----------------------------------------------------------------------------
# spatial context (static per run)
# ----------------------------------------------------------------------------
@dataclass
class SpatialContext:
    mpas: List[dict]
    ifa_rings: List[List[np.ndarray]]
    grounds: List[dict]
    version: str

    @classmethod
    def load(cls, root: Path) -> "SpatialContext":
        gj = json.load(open(root / "data/spatial/bd_mpas.geojson", encoding="utf8"))
        mpas = []
        for f in gj["features"]:
            rings = [np.array(r, float) for r in f["geometry"]["coordinates"]]
            valid = all(len(r) >= 4 for r in rings) and not any(geo.ring_self_intersects(r) for r in rings)
            mpas.append({"props": f["properties"], "rings": rings, "valid": bool(valid)})
        ifa = json.load(open(root / "data/spatial/ifa.geojson", encoding="utf8"))["features"][0]["geometry"]
        polys = ifa["coordinates"] if ifa["type"] == "MultiPolygon" else [ifa["coordinates"]]
        ifa_rings = [[np.array(r, float) for r in p] for p in polys]
        g = json.load(open(root / "data/spatial/fishing_grounds.geojson", encoding="utf8"))
        grounds = [{"props": f["properties"], "rings": [np.array(f["geometry"]["coordinates"][0], float)]} for f in g["features"]]
        return cls(mpas, ifa_rings, grounds, gj.get("spatial_version", "?"))

    def station_info(self, lat: np.ndarray, lon: np.ndarray, effect_map: Dict[str, str], buffer_kinds: List[str]) -> Dict[str, np.ndarray]:
        n = len(lat)
        mpa_state = np.zeros(n, dtype=np.int8)   # 0 outside, 2 UNKNOWN, 3 NO-GO
        mpa_idx = np.full(n, -1, dtype=np.int16)
        dist = np.full(n, np.inf)
        for i, m in enumerate(self.mpas):
            st = m["props"].get("legal_status", "candidate_geometry")
            eff = effect_map.get(st, "UNKNOWN")
            code = NOGO if eff == "NO-GO" else UNKNOWN
            if not m["valid"]:
                code = UNKNOWN
            inside = geo.covers(lon, lat, m["rings"])
            if not m["valid"]:  # invalid polygon: membership unreliable -> whole bbox is UNKNOWN
                r = np.vstack(m["rings"])
                inside = inside | ((lon >= r[:, 0].min()) & (lon <= r[:, 0].max()) & (lat >= r[:, 1].min()) & (lat <= r[:, 1].max()))
            upd = inside & (code > mpa_state)
            mpa_state[upd] = code
            mpa_idx[upd] = i
            upd2 = inside & (mpa_idx < 0)
            mpa_idx[upd2] = i
            if st in buffer_kinds or not buffer_kinds:
                d = geo.distance_to_rings_km(lon, lat, m["rings"])
                dist = np.where(inside, 0.0, np.minimum(dist, d))
        in_ifa = np.zeros(n, dtype=bool)
        for poly in self.ifa_rings:
            in_ifa |= geo.points_in_rings(lon, lat, poly)
        gmask = np.zeros(n, dtype=np.int16)
        for j, g in enumerate(self.grounds):
            gmask |= (geo.covers(lon, lat, g["rings"]).astype(np.int16) << j)
        return {"mpa_state": mpa_state, "mpa_idx": mpa_idx, "dist_mpa_km": dist, "in_ifa": in_ifa, "ground_mask": gmask}


# ----------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------
def evaluate(cfg: Config, rules: dict, rules_status: str, sp: Dict[str, np.ndarray], vessel: str,
             t0_h: np.ndarray, t1_h: np.ndarray, depth_ok: np.ndarray,
             target_species: str = "unspecified") -> Dict[str, Any]:
    """Evaluate Filter 3 for every station and one trip interval per station.

    ``t0_h`` / ``t1_h``: trip start / end as UTC hours since epoch (arrays of length n).
    """
    n = len(t0_h)
    state = np.zeros(n, dtype=np.int8)
    mask = np.zeros(n, dtype=np.int64)
    bit = lambda *c: mask_of(cfg, *c)  # noqa: E731

    if rules_status == "invalid":
        state[:] = UNKNOWN
        mask |= bit("RULES_STALE")
    elif rules_status == "stale":
        state[:] = UNKNOWN
        mask |= bit("RULES_STALE")

    a = _local_hours(np.asarray(t0_h, float))
    b = _local_hours(np.asarray(t1_h, float))
    y0 = int(dt.datetime.fromtimestamp(float(np.min(t0_h)) * 3600, dt.timezone.utc).astimezone(DHAKA).year)
    y1 = int(dt.datetime.fromtimestamp(float(np.max(t1_h)) * 3600, dt.timezone.utc).astimezone(DHAKA).year)
    active = {}

    # --- national closures (hard gates) + missing-year approval -----------------------
    usable = rules_status in ("ok", "stale")
    if usable:
        for regime_id, reg in rules.get("regimes", {}).items():
            if reg["kind"] != "national_closure":
                continue
            rcode = reg["reason"]
            hit = np.zeros(n, dtype=bool)
            specified_hit = np.zeros(n, dtype=bool)
            for r in rules["rules"]:
                if r.get("regime") != regime_id or r.get("approval_status") != "approved" or r["effect"] != "NO-GO":
                    continue
                ws = _date_to_local_hours(dt.date.fromisoformat(r["start_date"]))
                we = _date_to_local_hours(dt.date.fromisoformat(r["end_date"])) + 24.0  # inclusive end date
                touches = (a < we) & (b > ws)
                hit |= touches
                target = r.get("applies_when_target")
                if target is None or target_species.lower() == str(target).lower():
                    specified_hit |= touches
            # A species-specific Hilsa ban is not an assertion that EVERY other
            # fishery is banned. When species/gear is unspecified, withdraw a
            # compliance clearance instead of wrongly issuing general NO-GO or SAFE.
            state[hit & ~specified_hit] = np.maximum(state[hit & ~specified_hit], UNKNOWN)
            state[specified_hit] = NOGO
            mask[hit] |= bit(rcode)
            active[regime_id] = bool(hit.any())
            # missing approval for a year whose indicative window the trip touches
            approved = set(reg.get("approved_years", []))
            for (Y, ws, we) in _indicative_windows(reg["indicative_window"], range(y0 - 1, y1 + 1)):
                if Y in approved:
                    continue
                touch = (a < we) & (b > ws) & ~hit
                state[touch] = np.maximum(state[touch], UNKNOWN)
                mask[touch] |= bit("RULES_YEAR_UNAPPROVED")

    # --- species conservation info (Jatka): flag only, applied downstream when target=hilsa
    jatka_active = np.zeros(n, dtype=bool)
    for r in (rules.get("rules", []) if usable else []):
        if rules["regimes"].get(r.get("regime"), {}).get("kind") == "species_conservation" and r.get("approval_status") == "approved":
            ws = _date_to_local_hours(dt.date.fromisoformat(r["start_date"]))
            we = _date_to_local_hours(dt.date.fromisoformat(r["end_date"])) + 24.0
            jatka_active |= (a < we) & (b > ws)
    mask[jatka_active] |= bit("JATKA_RISK")

    # --- MPA gates --------------------------------------------------------------------
    ms = sp["mpa_state"]
    state = np.maximum(state, ms)
    mask[ms == NOGO] |= bit("MPA_VERIFIED")
    mask[ms == UNKNOWN] |= bit("MPA_UNVERIFIED")
    buf_km = cfg.filter3["mpa"]["buffer_km"]
    u_buf = np.clip(sp["dist_mpa_km"] / buf_km, 0.0, 1.0)
    u_buf = np.where(np.isfinite(sp["dist_mpa_km"]), u_buf, 1.0)
    near = (ms == 0) & (u_buf < cfg.filter3["mpa"]["buffer_caution_below_u"])
    state[near] = np.maximum(state[near], CAUTION)
    mask[near] |= bit("MPA_BUFFER")

    # --- vessel-zone rules (IFA) -------------------------------------------------------
    gz = np.ones(n)
    for vz in (rules.get("vessel_zone_rules", []) if usable else rules.get("vessel_zone_rules", [])):
        if vessel not in vz["vessel_types"] and "ALL" not in vz["vessel_types"]:
            continue
        zone = sp["in_ifa"] if vz["zone"] == "IFA" else np.zeros(n, dtype=bool)
        if vz.get("approval_status") == "approved":
            state[zone] = np.maximum(state[zone], NOGO if vz["effect"] == "NO-GO" else CAUTION)
            mask[zone] |= bit("VZ_PROHIBITED")
            gz[zone] = 0.0
        else:
            state[zone] = np.maximum(state[zone], UNKNOWN)
            mask[zone] |= bit("VZ_UNRESOLVED")
            gz[zone] = 0.0
    mask[sp["in_ifa"]] |= bit("IFA_TAG")

    # --- missing depth -> UNKNOWN (cannot confirm wet / zone) ----------------------------
    state[~depth_ok] = np.maximum(state[~depth_ok], UNKNOWN)

    g_mpa = np.where(ms >= UNKNOWN, 0.0, 1.0)
    g_season = np.where(np.isin(state, (NOGO, UNKNOWN)) & (mask & (bit("BAN_BOB_58D", "BAN_HILSA_22D", "RULES_YEAR_UNAPPROVED", "RULES_STALE")) != 0), 0.0, 1.0)
    U = g_mpa * g_season * gz * u_buf  # u_crowd, u_life not assessed -> excluded from the geometric mean
    U = np.where(state >= UNKNOWN, 0.0, U)
    return {"state": state, "mask": mask, "U": U, "u_buf": u_buf, "jatka_active": jatka_active,
            "components": {"u_buf": "assessed", "u_crowd": "not_assessed", "u_life": "not_assessed"}, "active_regimes": active}
