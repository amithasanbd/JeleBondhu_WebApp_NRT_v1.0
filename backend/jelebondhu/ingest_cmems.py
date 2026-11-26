"""Copernicus Marine (CMEMS) ingestion.

Uses the official ``copernicusmarine`` toolbox. Credentials are read ONLY from the
environment (``CMEMS_USERNAME`` / ``CMEMS_PASSWORD``, set as GitHub Actions secrets) -
never from files in the repository.

The dataset IDs live in config/pipeline.json. The pipeline never assumes that every
dataset updates at the same time: each dataset is fetched independently, its actual
valid time is recorded, and a missing dataset only removes the components that need it
(the Filter-1 completeness / confidence fall accordingly).
"""
from __future__ import annotations

import datetime as dt
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .fields import GriddedField, convergence

VAR_MAP = {"thetao": "sst", "so": "sss", "uo": "u", "vo": "v", "mlotst": "mlotst", "zos": "zos", "chl": "chl",
           "phyc": "phyc", "o2": "o2", "nppv": "nppv", "no3": "no3", "po4": "po4", "si": "si", "ph": "ph"}


@dataclass
class CmemsResult:
    fields: Dict[str, GriddedField] = field(default_factory=dict)      # raw (internal names)
    valid_time: Optional[dt.datetime] = None                            # oldest valid time across datasets used
    status: Dict[str, Dict[str, Any]] = field(default_factory=dict)     # per dataset key
    mode: str = "live"

    def complete_variables(self):
        return sorted(self.fields)


def _subset_kwargs(fn, kw: dict) -> dict:
    """Drop keyword arguments that the installed toolbox version does not know."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover
        return kw
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kw
    return {k: v for k, v in kw.items() if k in params}


def _read_nc(path: Path, wanted, now: dt.datetime):
    import xarray as xr  # imported lazily: only the live pipeline needs it

    ds = xr.open_dataset(path)
    lat_n = "latitude" if "latitude" in ds.coords else "lat"
    lon_n = "longitude" if "longitude" in ds.coords else "lon"
    out, vt = {}, None
    t = None
    if "time" in ds.coords and ds["time"].size:
        tv = ds["time"].values
        now64 = np.datetime64(now.astimezone(dt.timezone.utc).replace(tzinfo=None))
        i = int(np.argmin(np.abs(tv - now64)))
        t = tv[i]
        vt = dt.datetime.utcfromtimestamp(t.astype("datetime64[s]").astype(int)).replace(tzinfo=dt.timezone.utc)
    for v in wanted:
        if v not in ds:
            continue
        da = ds[v]
        if "time" in da.dims:
            da = da.isel(time=i)
        for d in da.dims:
            if d.startswith("depth") or d == "elevation":
                da = da.isel({d: 0})
        arr = np.asarray(da.values, dtype=float)
        out[VAR_MAP.get(v, v)] = GriddedField(ds[lat_n].values, ds[lon_n].values, arr, name=VAR_MAP.get(v, v),
                                              units=str(da.attrs.get("units", "")))
    ds.close()
    return out, vt


def fetch_cmems(cfg: dict, bbox: dict, now: dt.datetime, workdir: Path, log=print) -> CmemsResult:
    res = CmemsResult()
    user, pwd = os.environ.get("CMEMS_USERNAME"), os.environ.get("CMEMS_PASSWORD")
    if not (user and pwd):
        for k in cfg["datasets"]:
            res.status[k] = {"ok": False, "error": "CMEMS_USERNAME/CMEMS_PASSWORD not set"}
        log("CMEMS credentials not set - ocean fields unavailable")
        return res
    try:
        import copernicusmarine as cm
    except Exception as e:  # pragma: no cover
        for k in cfg["datasets"]:
            res.status[k] = {"ok": False, "error": f"copernicusmarine import failed: {e}"}
        return res
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = (now - dt.timedelta(days=2)).strftime("%Y-%m-%dT00:00:00")
    t1 = (now + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    times = []
    for key, d in cfg["datasets"].items():
        fn = f"{key}.nc"
        kw = dict(dataset_id=d["dataset_id"], variables=d["variables"], minimum_longitude=bbox["lon_min"],
                  maximum_longitude=bbox["lon_max"], minimum_latitude=bbox["lat_min"], maximum_latitude=bbox["lat_max"],
                  start_datetime=t0, end_datetime=t1, output_filename=fn, output_directory=str(workdir),
                  username=user, password=pwd, overwrite=True, force_download=True, disable_progress_bar=True)
        if d.get("depth"):
            kw["minimum_depth"], kw["maximum_depth"] = d["depth"]
        try:
            cm.subset(**_subset_kwargs(cm.subset, kw))
            got, vt = _read_nc(workdir / fn, d["variables"], now)
            res.fields.update(got)
            if vt:
                times.append(vt)
            res.status[key] = {"ok": bool(got), "dataset_id": d["dataset_id"], "variables": sorted(got),
                               "valid_time": vt.isoformat() if vt else None}
            log(f"CMEMS {key}: {sorted(got)} @ {vt}")
        except Exception as e:
            msg = str(e).replace(pwd, "***")[:240]
            res.status[key] = {"ok": False, "dataset_id": d["dataset_id"], "error": msg}
            log(f"CMEMS {key} FAILED: {msg}")
    if times:
        res.valid_time = min(times)
    return res


def derive(res: CmemsResult) -> Dict[str, GriddedField]:
    """Derived fields on their native grids (fronts, convergence, current speed)."""
    f = dict(res.fields)
    if "u" in f and "v" in f and f["u"].values.shape == f["v"].values.shape:
        f["current_speed"] = GriddedField(f["u"].lat, f["u"].lon, np.hypot(f["u"].values, f["v"].values), "current_speed", "m s-1")
        f["convergence"] = convergence(f["u"], f["v"])
    if "sst" in f:
        f["sst_front"] = f["sst"].gradient_per_km()
    if "chl" in f:
        f["chl_front"] = f["chl"].gradient_per_km(log10=True)
    return f
