"""Deterministic synthetic inputs for DEMO mode and tests.

DEMO output is NOT ocean or weather data. It exists so the frontend, the QC gate and the
decision logic can be exercised without network access or credentials. Every bundle built
from these inputs carries ``mode: "demo"`` and the frontend shows a permanent DEMO banner.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np

from .bmd import BmdState
from .fields import Bathymetry, GriddedField
from .ingest_cmems import CmemsResult
from .ingest_openmeteo import HAZARD_KEYS, HazardSet


def synthetic_cmems(cfg, now: dt.datetime, bathy: Bathymetry, seed: int = 7) -> CmemsResult:
    rng = np.random.default_rng(seed + now.timetuple().tm_yday)
    bb = cfg.pipeline["bbox"]
    res = CmemsResult(mode="demo")
    for tag, step, keys in (("phy", 1 / 12, ["sst", "sss", "u", "v", "mlotst", "zos"]),
                            ("bgc", 0.25, ["chl", "o2", "nppv", "no3", "po4", "ph"])):
        lat = np.arange(bb["lat_min"], bb["lat_max"] + 1e-9, step)
        lon = np.arange(bb["lon_min"], bb["lon_max"] + 1e-9, step)
        LA, LO = np.meshgrid(lat, lon, indexing="ij")
        depth = bathy.depth_m(LA, LO)
        wet = np.isfinite(depth) & (depth > 0)
        D = np.where(wet, depth, np.nan)
        front = np.tanh((LA - (20.3 + 0.35 * np.sin(1.9 * LO))) / 0.12)
        coast = np.exp(-np.clip(D, 0, None) / 45.0)
        noise = lambda s: s * rng.standard_normal(LA.shape)  # noqa: E731
        f = {}
        f["sst"] = 29.2 - 0.9 * (LA - 17.6) / 5.4 + 0.5 * front - 0.6 * coast + noise(0.05)
        f["sss"] = 34.0 - 11.0 * np.exp(-np.hypot(LA - 22.0, (LO - 90.9) * 0.95) / 0.9) - 2 * coast + noise(0.1)
        f["u"] = 0.18 * np.sin(2.3 * LA) * np.cos(1.7 * LO) + noise(0.01)
        f["v"] = 0.15 * np.cos(2.1 * LA + 0.4) * np.sin(2.0 * LO) + noise(0.01)
        f["mlotst"] = 12 + 40 * (1 - coast) + noise(1.0)
        f["zos"] = 0.35 * np.sin(1.3 * LA + 0.7 * LO) + noise(0.01)
        f["chl"] = 0.25 + 3.2 * coast + 0.5 * np.exp(-np.abs(LA - 20.3) / 0.15) + np.abs(noise(0.05))
        f["nppv"] = 6.0 * f["chl"] ** 0.9
        f["no3"] = 0.15 + 2.2 * coast + np.abs(noise(0.03))
        f["po4"] = 0.04 + 0.30 * coast + np.abs(noise(0.01))
        f["o2"] = 195 - 60 * coast + 20 * front + noise(1.5)
        f["ph"] = 8.1 - 0.16 * coast + noise(0.004)
        for k in keys:
            res.fields[k] = GriddedField(lat, lon, np.where(wet, f[k], np.nan), name=k)
    res.valid_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    res.status = {"demo": {"ok": True, "note": "synthetic fields - not CMEMS data"}}
    return res


def synthetic_hazards(cfg, now: dt.datetime, rep: np.ndarray, seed: int = 11) -> HazardSet:
    rng = np.random.default_rng(seed + now.timetuple().tm_yday)
    days = cfg.pipeline["openmeteo"]["forecast_days"]
    t0 = np.datetime64(now.replace(minute=0, second=0, microsecond=0, tzinfo=None), "h")
    nt = int(cfg.pipeline["openmeteo"].get("forecast_hours", 24 * days))
    t = t0 + np.arange(nt).astype("timedelta64[h]")
    hrs = np.arange(nt, dtype=float)
    now_i = 0.0
    n = len(rep)
    lat = rep[:, 0:1]
    lon = rep[:, 1:2]
    base = 0.55 + 0.30 * np.clip((21.8 - lat) / 3.0, 0, 1.4)
    diurnal = 0.18 * np.sin(2 * np.pi * (hrs[None, :] - 6) / 24)
    # distant disturbance in the south arriving ~66 h after now
    storm = 2.4 * np.exp(-((hrs[None, :] - (now_i + 66)) ** 2) / (2 * 9.0 ** 2)) * np.exp(-np.hypot(lat - 19.2, (lon - 90.2) * 0.95) / 1.8)
    # shorter squall near the south-east coast ~ 28 h after now
    squall = np.exp(-((hrs[None, :] - (now_i + 28)) ** 2) / (2 * 3.0 ** 2)) * ((lon > 91.4) & (lat < 21.9) & (lat > 20.3))
    wave = np.clip(base + diurnal + storm + 0.5 * squall + 0.05 * rng.standard_normal((n, nt)), 0.15, None)
    wind = np.clip(3.0 + 3.2 * wave + 4.0 * squall + 0.4 * rng.standard_normal((n, nt)), 0.5, None)
    gust = wind * (1.35 + 0.25 * squall) + 0.5
    vis = np.clip(14.0 - 9.0 * squall - 3.0 * storm + 0.8 * rng.standard_normal((n, nt)), 0.3, 20.0)
    code = np.where(squall > 0.6, 95.0, np.where(storm > 0.8, 65.0, np.where(squall > 0.2, 61.0, 1.0)))
    data = {k: np.full((n, nt), np.nan) for k in HAZARD_KEYS}
    data.update({"wave_height": wave, "wave_period": 5.0 + 1.5 * wave, "wave_direction": np.full((n, nt), 200.0) + 10 * rng.standard_normal((n, nt)),
                 "swell_wave_height": 0.7 * wave, "wind_wave_height": 0.5 * wave, "current_speed": 0.1 + 0.05 * wave,
                 "sst": np.full((n, nt), 28.0), "wind_speed": wind, "wind_gust": gust, "visibility": vis, "weather_code": code})
    return HazardSet(rep[:, 0].copy(), rep[:, 1].copy(), t, data, now, source="synthetic-demo")


def demo_bmd(now: dt.datetime) -> BmdState:
    rec = {"demo": True, "record_status": "VERIFIED", "verified_by": "DEMO (synthetic)", "verified_at": now.isoformat(),
           "issued_at": now.isoformat(), "valid_from": now.isoformat(),
           "valid_to": (now + dt.timedelta(hours=12)).isoformat(), "default_classification": "none", "areas": [],
           "headline_en": "DEMO record - not an official BMD bulletin", "source_url": ""}
    return BmdState(True, "ok (DEMO record)", rec, "none", [])
