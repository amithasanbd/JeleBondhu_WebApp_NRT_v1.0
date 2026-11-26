"""Non-compensatory Triple-Filter engine, confidence gate and recommendation builder.

Final class letters (one per station and trip):
    S  SAFE        no verified restriction, safety checks pass, confidence sufficient
    C  CAUTION     marginal conditions, low suitability, reduced confidence, caution rules
    N  NO-GO       confirmed prohibition / critical hazard / insufficient trip window
    U  NO ADVISORY missing or stale critical data, unverified bulletin, unresolved rules/route
    R  out of range for the selected vessel (not a prohibition)
    L  not open sea (land / shallow)

Priority (never compensatory):
    1  confirmed prohibition or official warning ........................ N
    2  forecast vessel hazard / insufficient return margin ............. N
    3  data confidence < 0.3, missing inputs, unresolved rules/route ... U
    4  caution conditions (low PAI, marginal, C<0.5, cautionary signal) . C
    5  otherwise SAFE - unless the BMD warning is not verified -> U
Ranking score: A = PAI * min(S, U)  (used only to order zones that are already S or C).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from . import filter1, filter2, filter3, geo
from .bmd import BmdState
from .config import Config, mask_of
from .fields import Bathymetry, GriddedField
from .filter3 import CAUTION, NOGO, PASS, UNKNOWN
from .ingest_cmems import CmemsResult, derive
from .ingest_openmeteo import HazardSet
from .reference import anomalies, load_reference

LETTERS = np.array(["S", "C", "N", "U", "R", "L"])
S_, C_, N_, U_, R_, L_ = range(6)

SEASON_OF_MONTH = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon",
                   6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Post-monsoon", 11: "Post-monsoon"}


@dataclass
class Stations:
    id: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    depth: np.ndarray
    in_eez: np.ndarray

    @property
    def n(self):
        return len(self.lat)


def load_stations(cfg: Config) -> Stations:
    import json

    s = json.load(open(cfg.root / "data/static/stations.json", encoding="utf8"))
    return Stations(np.array(s["id"]), np.array(s["lat"], float), np.array(s["lon"], float),
                    np.array(s["depth_m"], float), np.array(s["in_eez"], bool))


def choose_rep_points(cfg: Config, st: Stations, bathy: Bathymetry) -> np.ndarray:
    """Representative offshore points for the Open-Meteo requests (deterministic).

    One station per ``rep_point_step_deg`` lattice node (nearest wet station within 0.45 step)
    plus every port's sea-entry waypoint. Returns array (m,2) of [lat, lon].
    """
    step = cfg.pipeline["rep_point_step_deg"]
    bb = cfg.pipeline["bbox"]
    wet = bathy.is_wet(st.lat, st.lon, cfg.pipeline["station_min_depth_m"]) & st.in_eez
    pts = []
    for la in np.arange(bb["lat_min"], bb["lat_max"] + 1e-9, step):
        for lo in np.arange(bb["lon_min"], bb["lon_max"] + 1e-9, step):
            d = np.hypot(st.lat - la, (st.lon - lo) * np.cos(np.radians(la)))
            d = np.where(wet, d, np.inf)
            i = int(np.argmin(d))
            if d[i] <= 0.75 * step:
                pts.append((round(float(st.lat[i]), 4), round(float(st.lon[i]), 4)))
    for p in cfg.ports["ports"].values():
        pts.append((round(p["entry"]["lat"], 4), round(p["entry"]["lon"], 4)))
    uniq = sorted(set(pts))
    return np.array(uniq, float)


# ----------------------------------------------------------------------------
def sample_environment(cfg: Config, cmems: Optional[CmemsResult], st: Stations, bathy: Bathymetry,
                       month: int, ref) -> Dict[str, np.ndarray]:
    var: Dict[str, np.ndarray] = {}
    depth = bathy.depth_m(st.lat, st.lon)
    var["depth"] = np.where(np.isfinite(depth), depth, st.depth)
    if cmems is not None and cmems.fields:
        d = derive(cmems)
        for name, gf in d.items():
            var[name] = gf.sample(st.lat, st.lon)
    var.update(anomalies(ref, month, var))
    return var


def confidence_components(cfg: Config, now: dt.datetime, cmems: Optional[CmemsResult], hz: Optional[HazardSet],
                          f1: dict, mode: str, support: np.ndarray, lead_h: np.ndarray) -> Dict[str, np.ndarray]:
    c = cfg.pipeline["confidence"]
    n = len(support)
    if cmems is not None and cmems.valid_time is not None:
        age = (now - cmems.valid_time).total_seconds() / 3600.0
        fresh = float(np.clip(1.0 - (age - c["env_fresh_full_h"]) / (c["env_fresh_zero_h"] - c["env_fresh_full_h"]), 0, 1))
    else:
        age, fresh = None, 0.0
    env_complete = np.nan_to_num(f1["completeness"], nan=0.0)
    hz_complete = hz.valid_fraction() if hz is not None else 0.0
    calib = c["calibration_factor"]["calibrated" if mode == "frozen" else "experimental"]
    lead = np.clip(1.0 - (lead_h - c["lead_full_h"]) / (c["lead_zero_h"] - c["lead_full_h"]) * (1.0 - c["lead_floor"]), c["lead_floor"], 1.0)
    return {"env_fresh": np.full(n, fresh), "env_complete": env_complete, "hazard_complete": np.full(n, hz_complete),
            "calibration": np.full(n, calib), "spatial": support, "lead": lead}, age


def combine_confidence(comps: Dict[str, np.ndarray]) -> np.ndarray:
    return np.min(np.stack(list(comps.values()), axis=0), axis=0)


def decide(cfg: Config, wet, in_range, state2, state3, pai, pai_cls, conf, bmd_verified: bool, mask: np.ndarray,
           bmd_block=("S", "C")):
    """Vectorised priority decision. Returns (class_idx array, pre_bmd class idx, mask)."""
    n = len(wet)
    bit = lambda *c: mask_of(cfg, *c)  # noqa: E731
    wd = cfg.pipeline["confidence"]["withdraw_below"]
    cap = cfg.pipeline["confidence"]["caution_cap_below"]
    cls = np.full(n, U_, dtype=np.int8)
    elig = wet & in_range
    nogo = elig & ((state3 == NOGO) | (state2 == NOGO))
    low_conf = elig & ~nogo & (conf < wd)
    env_missing = elig & ~nogo & ~np.isfinite(pai)
    unknown = elig & ~nogo & ((state3 == UNKNOWN) | (state2 == UNKNOWN))
    cau = elig & ~nogo & ((state2 == CAUTION) | (state3 == CAUTION) | (pai_cls == 0) | ((conf >= wd) & (conf < cap)))
    cls[elig] = S_
    cls[cau] = C_
    cls[unknown | low_conf | env_missing] = U_
    cls[nogo] = N_
    cls[~in_range & wet] = R_
    cls[~wet] = L_
    mask = mask.copy()
    mask[low_conf] |= bit("CONF_LOW")
    mask[elig & ~nogo & (conf >= wd) & (conf < cap)] |= bit("CONF_CAP")
    mask[env_missing] |= bit("DATA_ENV_MISSING")
    mask[elig & ~nogo & (pai_cls == 0) & np.isfinite(pai)] |= bit("PAI_LOW")
    mask[~wet] |= bit("NOT_WET")
    pre = cls.copy()
    if not bmd_verified:
        for letter in bmd_block:
            cls[cls == "SCNURL".index(letter)] = U_
    return cls, pre, mask


# ----------------------------------------------------------------------------
def pick_zones(st: Stations, cls: np.ndarray, A: np.ndarray, dist_nm: np.ndarray, rt_h: np.ndarray, pai: np.ndarray,
               S: np.ndarray, U: np.ndarray, mask: np.ndarray, ground_names: List[List[str]], n: int = 3,
               sep_km: float = 25.0, pre: Optional[np.ndarray] = None) -> List[dict]:
    """Top zones among SAFE cells, then CAUTION cells, with spatial de-duplication.

    When the BMD gate blocks SAFE (cls == U but pre == S) the zones are still listed, flagged
    ``pending_official_check`` so a human can see where advice would point once BMD is verified.
    """
    out: List[dict] = []
    src = pre if pre is not None else cls
    for want, kind in ((S_, "safe"), (C_, "caution")):
        if len(out) >= n:
            break
        idx = np.where(src == want)[0]
        idx = idx[np.argsort(-A[idx])]
        for i in idx:
            if len(out) >= n:
                break
            if any(geo.haversine_km(st.lat[i], st.lon[i], z["lat"], z["lon"]) < sep_km for z in out):
                continue
            out.append({"i": int(i), "id": int(st.id[i]), "lat": round(float(st.lat[i]), 3), "lon": round(float(st.lon[i]), 3),
                        "kind": kind if cls[i] == want else "pending_official_check", "class": str(LETTERS[cls[i]]),
                        "pai": int(round(100 * pai[i])), "S": int(round(100 * S[i])), "U": int(round(100 * U[i])),
                        "dist_nm": int(round(dist_nm[i])), "trip_h": int(round(rt_h[i])), "depth_m": int(round(st.depth[i])),
                        "ground": ground_names[i], "reasons": int(mask[i])})
    return out
