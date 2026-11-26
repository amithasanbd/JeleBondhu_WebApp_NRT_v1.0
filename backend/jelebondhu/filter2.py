"""Filter 2 - vessel hazards and return-time feasibility.

    s_k    = clip((h_stop - h)/(h_stop - h_safe), 0, 1)       (reversed for visibility)
    s_phys = min_k s_k                                         (weakest link, no compensation)
    R_T    = d_out/v + T_fish + d_ret/v
    M      = (W - R_T)/R_T
    S      = G_BMD * min(s_phys, clip(M/0.25, 0, 1))

Conditions are evaluated along the sea route and through the whole trip (position-time
schedule), not only at the destination at departure. ``W`` is the forecast safe-weather
window: hours from departure until any point of the planned corridor first reaches a vessel
stop limit. If routing cannot be verified an approximate distance is reported but the trip is
never certified.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from . import geo
from .bmd import BmdState
from .config import Config, mask_of
from .fields import Bathymetry
from .ingest_openmeteo import HazardSet, apply_weights, idw_weights

HAZ = ["wave_height_m", "wind_speed_ms", "wind_gust_ms", "visibility_km", "thunderstorm"]
HAZ_CODE = ["WAVE_HIGH", "WIND_HIGH", "GUST_HIGH", "VIS_LOW", "THUNDER"]
PASS, CAUTION, UNKNOWN, NOGO = 0, 1, 2, 3


# ----------------------------------------------------------------------------
class HazardField:
    """Hazard series (from the current hour onward) interpolated to arbitrary points."""

    def __init__(self, hs: HazardSet, now: "np.datetime64", idw_cfg: dict, thunder_codes):
        self.hs = hs
        t = hs.t_utc
        i0 = int(np.searchsorted(t, np.datetime64(now, "h"), side="right") - 1)
        self.i0 = max(i0, 0)
        self.t = t[self.i0 :]
        self.H = len(self.t)
        self.idw = idw_cfg
        self.thunder_codes = list(thunder_codes)

    def at(self, lat, lon, hours=None):
        """-> (dict name->(n,H) float32 arrays, support (n,))."""
        lat = np.asarray(lat, float).ravel()
        lon = np.asarray(lon, float).ravel()
        W, support = idw_weights(self.hs.lat, self.hs.lon, lat, lon, self.idw["k"], self.idw["power"],
                                 self.idw["max_distance_deg"], self.idw["full_support_deg"])
        sl = slice(self.i0, self.i0 + min(int(hours), self.H) if hours else None)
        d = self.hs.data
        out = {
            "wave_height_m": apply_weights(W, d["wave_height"][:, sl]),
            "wind_speed_ms": apply_weights(W, d["wind_speed"][:, sl]),
            "wind_gust_ms": apply_weights(W, d["wind_gust"][:, sl]),
            "visibility_km": apply_weights(W, d["visibility"][:, sl]),
        }
        code = d["weather_code"][:, sl]
        thunder = np.where(np.isfinite(code), np.isin(code, self.thunder_codes).astype(float), np.nan)
        # thunder anywhere among the 4 nearest sources counts (conservative: max, not average)
        out["thunderstorm"] = _max_nearest(W, thunder)
        return {k: v.astype(np.float32) for k, v in out.items()}, support


def _max_nearest(W, series):
    """Max over each point's nearest sources (conservative for a binary thunderstorm flag)."""
    Wz = np.nan_to_num(W)
    # Different destination points can have different numbers of contributing
    # stations; the first destination row is NOT representative of all rows.
    k = max(1, int((Wz > 0).sum(axis=1).max())) if Wz.size else 1
    idx = np.argsort(-Wz, axis=1)[:, :k]
    active = np.take_along_axis(Wz, idx, axis=1) > 0.0
    sel = series[idx]
    observed = active[:, :, None] & np.isfinite(sel)
    any_thunder = (observed & (sel >= 1.0)).any(axis=1)
    # Missing thunderstorm codes at any contributing point prevent a 'no
    # thunderstorm' clearance unless another point explicitly reports thunder.
    complete = (observed | ~active[:, :, None]).all(axis=1)
    out = np.where(any_thunder, 1.0, np.where(complete, 0.0, np.nan))
    out[np.isnan(W).any(axis=1)] = np.nan
    return out


def hazard_scores(vessel_cfg: dict, h: Dict[str, np.ndarray], lower_is_worse=("visibility_km",)) -> Dict[str, np.ndarray]:
    s = {}
    for k in HAZ[:4]:
        lim = vessel_cfg["hazards"][k]
        x = h[k].astype(np.float32)
        if k in lower_is_worse:
            y = (x - lim["stop"]) / (lim["safe"] - lim["stop"])
        else:
            y = (lim["stop"] - x) / (lim["stop"] - lim["safe"])
        s[k] = np.clip(y, 0, 1)
        s[k] = np.where(np.isfinite(x), s[k], np.nan).astype(np.float32)
    th = h["thunderstorm"].astype(np.float32)
    s["thunderstorm"] = np.where(np.isfinite(th), 1.0 - th, np.nan).astype(np.float32)
    return s


def s_phys(scores: Dict[str, np.ndarray]) -> np.ndarray:
    """Conservative weakest-link score with explicit unknown handling.

    A verified stop condition (score 0) is a hard stop even when another
    provider field is missing. Otherwise ALL five hazards must be available:
    the nanmin-only implementation wrongly marked missing visibility or
    thunderstorm observations as favourable conditions.
    """
    # Keep array memory bounded for ~2,125 cells x 13 route points x 144 hours.
    template = np.asarray(scores[HAZ[0]], dtype=np.float32)
    minimum = np.ones_like(template)
    unknown = np.zeros(template.shape, dtype=bool)
    stop = np.zeros(template.shape, dtype=bool)
    for name in HAZ:
        a = np.asarray(scores[name], dtype=np.float32)
        finite = np.isfinite(a)
        unknown |= ~finite
        stop |= finite & (a <= 0.0)
        np.minimum(minimum, np.where(finite, a, 1.0), out=minimum)
    minimum[unknown] = np.nan
    minimum[stop] = 0.0
    return minimum


# ----------------------------------------------------------------------------
@dataclass
class PortRoutes:
    port_id: str
    lat: np.ndarray           # (n, K+1) route sample latitudes (entry -> station)
    lon: np.ndarray
    dist_nm: np.ndarray       # (n,) one-way distance incl. entry offset
    route_ok: np.ndarray      # (n,) bool
    station_wet: np.ndarray   # (n,) bool


def build_routes(cfg: Config, bathy: Bathymetry, port_id: str, st_lat, st_lon, wet_samples: int = 96) -> PortRoutes:
    p = cfg.ports["ports"][port_id]
    K = cfg.pipeline["route_samples"]
    e_lat, e_lon = p["entry"]["lat"], p["entry"]["lon"]
    la, lo = geo.interpolate_path(e_lat, e_lon, st_lat, st_lon, K)
    fla, flo = geo.interpolate_path(e_lat, e_lon, st_lat, st_lon, wet_samples)
    wet = bathy.is_wet(fla, flo, cfg.pipeline["route_min_depth_m"])
    # the first few samples (inside the 1.4 km entry cell) are not penalised
    wet[:, :2] = True
    route_ok = wet.all(axis=1)
    d_km = geo.haversine_km(e_lat, e_lon, st_lat, st_lon)
    dist_nm = d_km / geo.NM_KM + float(p.get("entry_offset_nm", 0.0))
    st_wet = bathy.is_wet(st_lat, st_lon, cfg.pipeline["station_min_depth_m"])
    return PortRoutes(port_id, la, lo, dist_nm, route_ok, st_wet)


def evaluate_trip(cfg: Config, vessel_id: str, routes: PortRoutes, s_route_phys: np.ndarray, s_route_k: Dict[str, np.ndarray],
                  depart_h: int, H: int, bmd: Optional[BmdState], bmd_cls_route: Optional[np.ndarray]) -> Dict[str, np.ndarray]:
    """Evaluate every station for one (vessel, port, departure offset).

    s_route_phys: (n, K+1, H) float32 weakest-link score along the corridor.
    s_route_k   : per-hazard scores, same shape.
    """
    f2 = cfg.filter2
    v = cfg.vessels["vessels"][vessel_id]
    n, K1, _ = s_route_phys.shape
    K = K1 - 1
    spd = v["speed_kn"]
    T_f = float(v["fishing_hours"])
    d_out = routes.dist_nm
    h_out = d_out / spd
    R_T = 2.0 * h_out + T_f if f2.get("return_to_same_port", True) else h_out + T_f
    in_range = d_out <= v["max_range_nm"]
    H_rem = H - depart_h
    bit = lambda *c: mask_of(cfg, *c)  # noqa: E731

    state = np.zeros(n, dtype=np.int8)
    mask = np.zeros(n, dtype=np.int64)
    S = np.zeros(n)
    s_trip = np.full(n, np.nan)
    W_h = np.full(n, np.nan)
    margin = np.full(n, np.nan)
    horizon_limited = np.zeros(n, dtype=bool)

    if H_rem < 6:  # essentially no forecast left
        state[:] = UNKNOWN
        mask |= bit("HORIZON_SHORT", "DATA_HAZARD_MISSING")
        return dict(state=state, mask=mask, S=S, s_trip=s_trip, W_h=W_h, margin_h=margin, R_T=R_T, dist_nm=d_out,
                    in_range=in_range, horizon_limited=horizon_limited)

    Tmax = int(min(H_rem, np.ceil(np.nanmax(np.where(in_range, R_T, 0))) + 1)) if in_range.any() else 1
    t = np.arange(Tmax)[None, :] + 0.5
    ho = h_out[:, None]
    ret_start = ho + T_f
    k_out = np.rint(t / np.maximum(ho, 1e-6) * K)
    k_ret = np.rint((1.0 - (t - ret_start) / np.maximum(ho, 1e-6)) * K)
    k_idx = np.where(t < ho, k_out, np.where(t < ret_start, K, k_ret))
    k_idx = np.clip(k_idx, 0, K).astype(int)
    valid = t < R_T[:, None]

    sl = s_route_phys[:, :, depart_h : depart_h + Tmax]
    s_pos = np.take_along_axis(sl, k_idx[:, None, :], axis=1)[:, 0, :]
    miss = (np.isnan(s_pos) & valid).any(axis=1)
    s_masked = np.where(valid & np.isfinite(s_pos), s_pos, np.inf)
    s_trip = np.where(np.isfinite(s_masked.min(axis=1)), s_masked.min(axis=1), np.nan)
    t_star = np.argmin(s_masked, axis=1)
    k_star = k_idx[np.arange(n), t_star]
    hz = np.stack([s_route_k[k][np.arange(n), k_star, depart_h + t_star] for k in HAZ], axis=1)  # (n,5)
    hz = np.where(np.isfinite(hz), hz, 2.0)
    lim = np.argmin(hz, axis=1)

    # forecast safe window along the whole corridor
    Tw = int(min(H_rem, np.ceil(1.25 * np.nanmax(np.where(in_range, R_T, 0))) + 2)) if in_range.any() else 1
    corr = s_route_phys[:, :, depart_h : depart_h + Tw]
    bad = (corr <= f2["bad_threshold"]).any(axis=1)  # (n, Tw)
    any_bad = bad.any(axis=1)
    first_bad = np.where(any_bad, np.argmax(bad, axis=1), Tw).astype(float)
    horizon_limited = (~any_bad) & (Tw >= H_rem)
    W_h = np.where(any_bad, first_bad, np.where(horizon_limited, float(H_rem), 1e3))
    margin = (W_h - R_T) / R_T
    f_m = np.clip(margin / f2["margin_reference"], 0, 1)
    short_hz = horizon_limited & (R_T > W_h)
    # Forecast ends before the boat can return: future conditions are unknown,
    # not "caution" and certainly not safe. Explicit severe hazards remain NO-GO.
    horizon_incomplete = R_T >= float(H_rem) - 1.0
    S_core = np.minimum(np.nan_to_num(s_trip, nan=0.0), f_m)
    S_core = np.where(short_hz, np.minimum(np.nan_to_num(s_trip, nan=0.0), 0.4), S_core)

    # ---- BMD gate -------------------------------------------------------------------
    G = np.ones(n)
    if bmd is not None and bmd_cls_route is not None:
        cls = bmd_cls_route.max(axis=1) if bmd_cls_route.ndim > 1 else bmd_cls_route
        G = np.where(cls >= 2, 0.0, 1.0)
    else:
        cls = np.zeros(n, dtype=int)
    S = G * S_core

    cu = f2["caution_below"]
    nogo = (S <= 0.0) & ~miss
    cau = (S > 0) & (S < cu)
    # reasons
    code_bits = np.array([bit(c) for c in HAZ_CODE], dtype=np.int64)
    hazard_bit = code_bits[lim]
    mask |= np.where(nogo & (np.nan_to_num(s_trip, nan=1.0) <= 0.0), hazard_bit, 0)
    mask |= np.where(nogo & (np.nan_to_num(s_trip, nan=1.0) > 0.0) & ~short_hz & (G > 0), bit("WINDOW_SHORT"), 0)
    mask |= np.where(cau & (np.nan_to_num(s_trip, nan=1.0) < cu), hazard_bit, 0)
    mask |= np.where(cau & (f_m < cu) & ~short_hz, bit("WINDOW_MARGINAL"), 0)
    mask |= np.where(short_hz, bit("HORIZON_SHORT"), 0)
    state = np.where(nogo, NOGO, np.where(cau | short_hz, CAUTION, PASS)).astype(np.int8)

    # BMD classes
    mask |= np.where(cls >= 2, bit("BMD_WARNING"), 0)
    caut_b = cls == 1
    state = np.where(caut_b & (state < CAUTION), CAUTION, state).astype(np.int8)
    mask |= np.where(caut_b, bit("BMD_CAUTION"), 0)
    state = np.where(cls >= 2, NOGO, state).astype(np.int8)
    if bmd is None or not bmd.verified:
        mask |= bit("BMD_UNVERIFIED")

    # data / route problems -> UNKNOWN (never NO-GO from missing data, never SAFE)
    unk = (miss | horizon_incomplete) & (state < NOGO)
    state = np.where(unk, UNKNOWN, state).astype(np.int8)
    mask |= np.where(miss, bit("DATA_HAZARD_MISSING"), 0)
    mask |= np.where(horizon_incomplete, bit("HORIZON_SHORT"), 0)
    rf = ~routes.route_ok & in_range & routes.station_wet
    state = np.where(rf & (state < NOGO), UNKNOWN, state).astype(np.int8)
    mask |= np.where(rf, bit("ROUTE_FAILED"), 0)
    mask |= np.where(~in_range, bit("VESSEL_RANGE"), 0)
    return dict(state=state, mask=mask, S=S, s_trip=s_trip, W_h=np.where(W_h > 900, np.nan, W_h), margin_h=W_h - R_T,
                R_T=R_T, dist_nm=d_out, in_range=in_range, horizon_limited=horizon_limited, bmd_class=cls)
