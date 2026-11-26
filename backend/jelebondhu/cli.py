"""Command-line entry points used by the GitHub Actions workflows.

    python -m jelebondhu.cli run --mode live --out dist/live --prev prev_live --cache cache
    python -m jelebondhu.cli run --mode demo --out dist/live
    python -m jelebondhu.cli validate dist/live
    python -m jelebondhu.cli bmd-record --classification none --verified-by "A. Name" --valid-hours 12
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import SCHEMA_VERSION, bmd as bmdmod
from .config import REPO_ROOT, load_config
from .engine import choose_rep_points, load_stations
from .fields import Bathymetry, GriddedField
from .ingest_cmems import CmemsResult, fetch_cmems
from .ingest_openmeteo import fetch_hazards
from .pipeline import run_pipeline
from .synthetic import demo_bmd, synthetic_cmems, synthetic_hazards


def _now(arg):
    if arg:
        d = dt.datetime.fromisoformat(arg.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


# ---- tiny cache so CMEMS is not re-downloaded on every 3-hourly run ---------------------
def save_env_cache(res: CmemsResult, path: Path, fetched_at: dt.datetime):
    path.parent.mkdir(parents=True, exist_ok=True)
    arrs = {}
    for k, f in res.fields.items():
        arrs[f"{k}__lat"], arrs[f"{k}__lon"], arrs[f"{k}__v"] = f.lat, f.lon, f.values.astype("float32")
    np.savez_compressed(path / "env_cache.npz", **arrs)
    json.dump({"fetched_at": fetched_at.isoformat(), "valid_time": res.valid_time.isoformat() if res.valid_time else None,
               "status": res.status}, open(path / "env_cache.json", "w"))


def load_env_cache(path: Path):
    try:
        meta = json.load(open(path / "env_cache.json"))
        z = np.load(path / "env_cache.npz")
        res = CmemsResult(status=meta["status"], valid_time=dt.datetime.fromisoformat(meta["valid_time"]) if meta["valid_time"] else None)
        for k in {n.split("__")[0] for n in z.files}:
            res.fields[k] = GriddedField(z[f"{k}__lat"], z[f"{k}__lon"], z[f"{k}__v"].astype(float), name=k)
        return res, dt.datetime.fromisoformat(meta["fetched_at"])
    except Exception:
        return None, None


def cmd_run(a) -> int:
    cfg = load_config(a.root)
    now = _now(a.now)
    out = Path(a.out)
    rep = None
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    st = load_stations(cfg)
    rep = choose_rep_points(cfg, st, bathy)
    print(f"representative hazard points: {len(rep)}")
    probe = None
    if a.mode == "demo":
        cmems = synthetic_cmems(cfg, now, bathy)
        hz = synthetic_hazards(cfg, now, rep)
        bmd = demo_bmd(now)
    else:
        hz = None
        if cfg.pipeline["openmeteo"]["enabled"]:
            try:
                hz = fetch_hazards(cfg.pipeline["openmeteo"], rep[:, 0], rep[:, 1], now=now)
                print(f"Open-Meteo: {hz.npts} points, valid fraction {hz.valid_fraction():.2f}")
            except Exception as e:
                print(f"Open-Meteo FAILED: {e}", file=sys.stderr)
        cmems = None
        cache = Path(a.cache) if a.cache else None
        if cfg.pipeline["cmems"]["enabled"]:
            if cache:
                c, fetched = load_env_cache(cache)
                if c is not None and (now - fetched).total_seconds() < a.cmems_reuse_h * 3600 and c.fields:
                    print(f"reusing cached CMEMS fetched {fetched.isoformat()}")
                    cmems = c
            if cmems is None:
                with tempfile.TemporaryDirectory() as td:
                    cmems = fetch_cmems(cfg.pipeline["cmems"], cfg.pipeline["bbox"], now, Path(td))
                if cmems.fields and cache:
                    save_env_cache(cmems, cache, now)
        bmd = bmdmod.load_state(cfg.root / cfg.pipeline["bmd"]["record_path"], now, cfg.pipeline["bmd"]["max_verification_age_h"])
        print(f"BMD verified={bmd.verified} ({bmd.reason})")
        if a.probe:
            prev_hashes = {}
            if a.prev and (Path(a.prev) / "warnings.json").exists():
                try:
                    pw = json.load(open(Path(a.prev) / "warnings.json"))
                    prev_hashes = {k: v.get("content_hash") for k, v in (pw["bmd"].get("probe") or {}).get("pages", {}).items()}
                except Exception:
                    pass
            probe = bmdmod.probe({"marine_warning": cfg.pipeline["bmd"]["marine_warning_url"],
                                  "fishermen_forecast": cfg.pipeline["bmd"]["fishermen_forecast_url"]}, prev_hashes,
                                 timeout=cfg.pipeline["bmd"]["probe_timeout_s"])
    bundle = run_pipeline(cfg, now, cmems, hz, bmd, mode=a.mode, probe=probe)
    print("QC:", json.dumps(bundle.qc))
    if not bundle.qc["passed"]:
        print("QC FAILED - not publishing a new bundle", file=sys.stderr)
        return 3
    if out.exists():
        shutil.rmtree(out)
    for rel, b in bundle.files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    tot = sum(len(b) for b in bundle.files.values())
    print(f"wrote {len(bundle.files)} files, {tot/1024:.0f} KB -> {out}  bundle={bundle.meta['bundle_id']}")
    return 0


def validate_dir(d: Path, now: dt.datetime | None = None) -> list:
    """Return a list of problems (empty = valid). Mirrors the checks done in the browser."""
    problems = []
    try:
        m = json.load(open(d / "manifest.json", encoding="utf8"))
    except Exception as e:
        return [f"manifest unreadable: {e}"]
    if m.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version {m.get('schema_version')} != {SCHEMA_VERSION}")
    for rel, meta in m.get("files", {}).items():
        p = d / rel
        if not p.exists():
            problems.append(f"missing {rel}")
            continue
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != meta["sha256"]:
            problems.append(f"hash mismatch {rel}")
        if len(b) != meta["bytes"]:
            problems.append(f"size mismatch {rel}")
        try:
            json.loads(b.decode("utf8"))
        except Exception as e:
            problems.append(f"invalid JSON {rel}: {e}")
    n = m.get("n_cells")
    for rel in m.get("files", {}):
        if rel.startswith("advisory/") and (d / rel).exists():
            adv = json.load(open(d / rel, encoding="utf8"))
            for dep in adv["departs"]:
                if len(dep["c"]) != n or len(dep["rb"]) != n or len(dep["s"]) != n:
                    problems.append(f"{rel}: array length != n_cells")
                if set(dep["c"]) - set("SCNURL"):
                    problems.append(f"{rel}: invalid class letter")
                if m.get("bmd_verified") is False and ("S" in dep["c"] or "C" in dep["c"]):
                    problems.append(f"{rel}: S/C issued although BMD record is unverified")
    try:
        gen = dt.datetime.fromisoformat(m["generated_at"])
        if dt.datetime.fromisoformat(m["valid_until"]) < dt.datetime.fromisoformat(m["analysis_time"]):
            problems.append("valid_until before analysis_time")
    except Exception as e:
        problems.append(f"bad timestamps: {e}")
    return problems


def cmd_validate(a) -> int:
    pr = validate_dir(Path(a.dir))
    if pr:
        print("INVALID BUNDLE:\n - " + "\n - ".join(pr))
        return 2
    print("bundle OK")
    return 0


def cmd_bmd_record(a) -> int:
    """Write data/manual/bmd_bulletin.json from verified human input (used by the BMD workflow)."""
    now = dt.datetime.now(dt.timezone.utc)
    areas = json.loads(a.areas) if a.areas else []
    rec = {"schema_version": "1.0", "record_status": "VERIFIED", "verified_by": a.verified_by, "verified_at": now.isoformat(),
           "issued_at": a.issued_at, "valid_from": a.valid_from or now.isoformat(),
           "valid_to": a.valid_to or (now + dt.timedelta(hours=a.valid_hours)).isoformat(),
           "default_classification": a.classification, "areas": areas, "signal": a.signal, "headline_en": a.headline_en,
           "headline_bn": a.headline_bn, "source_url": a.source_url, "notes": a.notes}
    path = Path(a.root or REPO_ROOT) / "data/manual/bmd_bulletin.json"
    json.dump(rec, open(path, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    chk = bmdmod.load_state(path, now, 24.0)
    print(f"wrote {path}; verified={chk.verified} ({chk.reason})")
    return 0 if chk.verified else 4


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jelebondhu")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--mode", choices=["live", "demo"], default="live")
    r.add_argument("--out", required=True)
    r.add_argument("--prev")
    r.add_argument("--cache")
    r.add_argument("--now")
    r.add_argument("--root")
    r.add_argument("--probe", action="store_true")
    r.add_argument("--cmems-reuse-h", type=float, default=10.0)
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("validate")
    v.add_argument("dir")
    v.set_defaults(fn=cmd_validate)
    b = sub.add_parser("bmd-record")
    b.add_argument("--classification", choices=list(bmdmod.CLASSES), required=True)
    b.add_argument("--verified-by", required=True)
    b.add_argument("--valid-hours", type=float, default=12)
    b.add_argument("--valid-from"); b.add_argument("--valid-to"); b.add_argument("--issued-at", required=True)
    b.add_argument("--areas", default="[]")
    b.add_argument("--signal", default=""); b.add_argument("--headline-en", default=""); b.add_argument("--headline-bn", default="")
    b.add_argument("--source-url", required=True); b.add_argument("--notes", default="")
    b.add_argument("--root")
    b.set_defaults(fn=cmd_bmd_record)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
