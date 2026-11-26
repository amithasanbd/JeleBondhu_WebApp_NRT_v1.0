"""Open-Meteo Marine + Weather ingestion (hourly hazard forecasts at representative points).

Open-Meteo accepts comma-separated coordinate lists and returns a JSON list with one
object per location. We request at a moderate number of representative offshore
points (batched), then interpolate (IDW) to the analysis stations and route samples.

Limits respected: free API is non-commercial, <10,000 calls/day, no uptime guarantee.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

try:  # requests is a hard dependency of the live pipeline only
    import requests
except Exception:  # pragma: no cover
    requests = None

HAZARD_KEYS = ["wave_height", "wave_period", "wave_direction", "swell_wave_height", "wind_wave_height",
               "current_speed", "sst", "wind_speed", "wind_gust", "visibility", "weather_code"]


@dataclass
class HazardSet:
    """Hourly hazard series for ``npts`` representative points.

    ``t_utc``: array of datetime64[h] (UTC). ``data[key]``: (npts, nt) float arrays (NaN = missing).
    """

    lat: np.ndarray
    lon: np.ndarray
    t_utc: np.ndarray
    data: Dict[str, np.ndarray]
    fetched_at: dt.datetime
    source: str = "open-meteo"
    errors: List[str] = field(default_factory=list)

    @property
    def npts(self) -> int:
        return len(self.lat)

    def valid_fraction(self) -> float:
        """Fraction of points with finite wave height AND wind speed at the first 24 h."""
        wh = self.data["wave_height"][:, :24]
        ws = self.data["wind_speed"][:, :24]
        ok = np.isfinite(wh).mean(axis=1) > 0.5
        ok &= np.isfinite(ws).mean(axis=1) > 0.5
        return float(ok.mean()) if len(ok) else 0.0


def _get(session, url: str, params: dict, timeout: int, tries: int = 3):
    last = None
    for k in range(tries):
        try:
            r = session.get(url, params=params, timeout=timeout, headers={"User-Agent": "JeleBondhu-NRT/1.0 (research prototype)"})
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            if r.status_code in (400, 401, 403, 404):
                break
        except Exception as e:  # network error
            last = e
        time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"Open-Meteo request failed: {last}")


def _as_list(payload):
    return payload if isinstance(payload, list) else [payload]


def _parse_times(hourly: dict) -> np.ndarray:
    return np.array([np.datetime64(t.replace("T", "T")[:16]) for t in hourly["time"]], dtype="datetime64[h]")


def _nan(a):
    return np.array([np.nan if x is None else x for x in a], dtype=float)


def parse_responses(lats, lons, marine_objs, weather_objs) -> HazardSet:
    """Parse already-fetched (and already concatenated) JSON objects. Pure function, unit-tested."""
    n = len(lats)
    if len(marine_objs) != n or len(weather_objs) != n:
        raise ValueError(f"expected {n} locations, got marine={len(marine_objs)} weather={len(weather_objs)}")
    t_ref = None
    for o in weather_objs + marine_objs:
        if o and o.get("hourly", {}).get("time"):
            t_ref = _parse_times(o["hourly"])
            break
    if t_ref is None:
        raise ValueError("no hourly time axis in responses")
    nt = len(t_ref)
    data = {k: np.full((n, nt), np.nan) for k in HAZARD_KEYS}
    mapping_m = {"wave_height": "wave_height", "wave_period": "wave_period", "wave_direction": "wave_direction",
                 "swell_wave_height": "swell_wave_height", "wind_wave_height": "wind_wave_height",
                 "ocean_current_velocity": "current_speed", "sea_surface_temperature": "sst"}
    mapping_w = {"wind_speed_10m": "wind_speed", "wind_gusts_10m": "wind_gust", "visibility": "visibility",
                 "weather_code": "weather_code"}
    errors = []
    for i in range(n):
        for objs, mp in ((marine_objs, mapping_m), (weather_objs, mapping_w)):
            o = objs[i]
            if not o or "hourly" not in o:
                errors.append(f"point {i}: missing response")
                continue
            h = o["hourly"]
            t = _parse_times(h)
            idx = np.searchsorted(t_ref, t)
            good = (idx < nt) & (t_ref[np.clip(idx, 0, nt - 1)] == t)
            for src, dst in mp.items():
                if src in h:
                    arr = _nan(h[src])
                    if dst == "visibility":
                        arr = arr / 1000.0  # m -> km
                    data[dst][i, idx[good]] = arr[good]
    return HazardSet(np.asarray(lats, float), np.asarray(lons, float), t_ref, data, dt.datetime.now(dt.timezone.utc), errors=errors)


def fetch_hazards(cfg_om: dict, lats, lons, session=None, now: Optional[dt.datetime] = None) -> HazardSet:
    """Fetch marine + weather forecasts for all representative points (batched)."""
    if session is None:
        if requests is None:
            raise RuntimeError("requests is not installed")
        session = requests.Session()
    lats = list(map(float, lats))
    lons = list(map(float, lons))
    chunk = int(cfg_om.get("chunk_size", 25))
    marine, weather = [], []
    for i in range(0, len(lats), chunk):
        la = ",".join(f"{v:.4f}" for v in lats[i : i + chunk])
        lo = ",".join(f"{v:.4f}" for v in lons[i : i + chunk])
        base = {"latitude": la, "longitude": lo, "timezone": "GMT"}
        # 168 hours from the current hour, instead of 7 calendar days from midnight.
        # Marine and Weather endpoints both support forecast_hours.
        if cfg_om.get("forecast_hours"):
            base["forecast_hours"] = int(cfg_om["forecast_hours"])
        else:
            base["forecast_days"] = int(cfg_om.get("forecast_days", 6))
        m = _get(session, cfg_om["marine_url"], {**base, "hourly": ",".join(cfg_om["marine_hourly"]), "cell_selection": "sea"},
                 cfg_om.get("timeout_s", 40))
        w = _get(session, cfg_om["weather_url"], {**base, "hourly": ",".join(cfg_om["weather_hourly"]), "wind_speed_unit": "ms"},
                 cfg_om.get("timeout_s", 40))
        marine += _as_list(m)
        weather += _as_list(w)
    hs = parse_responses(lats, lons, marine, weather)
    if now is not None:
        hs.fetched_at = now
    return hs


def idw_weights(src_lat, src_lon, dst_lat, dst_lon, k=4, power=2.0, max_deg=0.9, full_deg=0.35):
    """Inverse-distance weights (dst x src, sparse-as-dense) + spatial support in [0,1].

    Distances use a degree metric with cos(lat) scaling. Points farther than
    ``max_deg`` from every source get NaN weights (no extrapolation). Support is 1 within
    ``full_deg`` of the nearest source and fades linearly to 0.4 at ``max_deg``.
    """
    sl = np.asarray(src_lat, float)[None, :]
    so = np.asarray(src_lon, float)[None, :]
    dl = np.asarray(dst_lat, float)[:, None]
    do = np.asarray(dst_lon, float)[:, None]
    d = np.hypot(dl - sl, (do - so) * np.cos(np.radians(dl)))
    order = np.argsort(d, axis=1)[:, :k]
    dk = np.take_along_axis(d, order, axis=1)
    w = 1.0 / np.maximum(dk, 0.02) ** power
    W = np.zeros_like(d)
    np.put_along_axis(W, order, w, axis=1)
    W /= W.sum(axis=1, keepdims=True)
    dmin = dk[:, 0]
    W[dmin > max_deg, :] = np.nan
    support = np.where(dmin <= full_deg, 1.0, np.clip(1.0 - 0.6 * (dmin - full_deg) / max(max_deg - full_deg, 1e-6), 0.4, 1.0))
    support = np.where(dmin > max_deg, 0.0, support)
    return W, support


def apply_weights(W: np.ndarray, series: np.ndarray, nan_policy: str = "propagate") -> np.ndarray:
    """(ndst, nsrc) @ (nsrc, nt) with NaN-aware renormalisation of the available sources."""
    ok = np.isfinite(series)
    S = np.where(ok, series, 0.0)
    num = np.nan_to_num(W) @ S
    den = np.nan_to_num(W) @ ok.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[np.isnan(W).any(axis=1)] = np.nan
    out[den < 0.5] = np.nan  # less than half of the weight has data
    return out
