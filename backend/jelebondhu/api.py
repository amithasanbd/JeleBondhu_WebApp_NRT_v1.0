"""Optional read-only HTTP API for JeleBondhu snapshots.

GitHub Pages uses the static site published by GitHub Actions, and does NOT run
this service. For institution-hosted deployments, build dist/site first, then:

  PYTHONPATH=backend JB_SITE_DIR=dist/site uvicorn jelebondhu.api:app \
      --host 0.0.0.0 --port 8000

Only verified, precomputed snapshot files are served. No credentials, raw
fisheries observations, arbitrary paths, runtime API queries or public write
operations are exposed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


def create_app(site_dir: str | Path | None = None) -> FastAPI:
    site = Path(site_dir or os.environ.get("JB_SITE_DIR", "dist/site")).resolve()
    app = FastAPI(title="JeleBondhu NRT — Research Snapshot API", version="1.1.0", docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")

    def manifest() -> dict:
        try:
            m = json.loads((site / "live/manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as ex:
            raise HTTPException(503, "No verified live advisory snapshot is available") from ex
        if m.get("mode") != "live" or m.get("qc_passed") is not True:
            raise HTTPException(503, "Snapshot is not a QC-passed live release")
        return m

    def state(m: dict) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            if now >= dt.datetime.fromisoformat(m["expire_after"]):
                return "expired"
            if now >= dt.datetime.fromisoformat(m["stale_after"]):
                return "stale"
            if now > dt.datetime.fromisoformat(m["valid_until"]):
                return "aging"
            return "fresh"
        except (KeyError, ValueError, TypeError):
            return "expired"

    def read_hashed(m: dict, rel: str):
        meta = m.get("files", {}).get(rel)
        if not isinstance(meta, dict):
            raise HTTPException(404, "Advisory not found in manifest")
        # The caller constructs rel using allowlisted manifest keys, not user paths.
        p = site / "live" / rel
        try:
            data = p.read_bytes()
        except OSError as ex:
            raise HTTPException(503, "Snapshot file is unavailable") from ex
        if len(data) != meta.get("bytes") or hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            raise HTTPException(503, "Snapshot integrity verification failed")
        try:
            return json.loads(data)
        except json.JSONDecodeError as ex:
            raise HTTPException(503, "Snapshot JSON invalid") from ex

    def fresh_response(payload: dict, status_code: int = 200) -> JSONResponse:
        return JSONResponse(payload, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    def health():
        try:
            m = manifest()
        except HTTPException:
            return fresh_response({"status": "no_advisory", "mode": None, "message": "No verified live snapshot"}, 503)
        f = state(m)
        return fresh_response({"status": "ready" if f in ("fresh", "aging") else "no_advisory",
                               "freshness": f, "mode": m["mode"], "bundle_id": m.get("bundle_id"),
                               "analysis_time": m.get("analysis_time"), "bmd_verified": m.get("bmd_verified")},
                              200 if f in ("fresh", "aging") else 503)

    @app.get("/api/manifest")
    def get_manifest():
        m = manifest()
        return fresh_response({"manifest": m, "freshness": state(m)})

    @app.get("/api/cells")
    def get_cells():
        m = manifest()
        return fresh_response({"freshness": state(m), "cells": read_hashed(m, "cells.json")})

    @app.get("/api/advisory/{vessel}/{port}")
    def get_advisory(vessel: str, port: str, departure: int = Query(0, ge=0, le=2)):
        m = manifest()
        if vessel not in m.get("vessels", {}) or port not in m.get("ports", {}):
            raise HTTPException(404, "Unknown vessel or landing station")
        adv = read_hashed(m, f"advisory/{vessel}__{port}.json")
        deps = adv.get("departs", [])
        if departure >= len(deps):
            raise HTTPException(404, "Departure option unavailable")
        item = dict(deps[departure])
        f = state(m)
        # Never return a stale positive clearance. Retain original forecast in
        # the hashed static archive for research, but API users receive U.
        if f == "stale":
            item["c"] = "".join("U" if x in "SC" else x for x in item["c"])
        if f == "expired":
            item["c"] = "".join("U" if x in "SCN" else x for x in item["c"])
        if f in ("stale", "expired"):
            item["zones"] = []
            if item.get("overall") in ("S", "C") or (f == "expired" and item.get("overall") == "N"):
                item["overall"] = "U"
            item["headline_en"] = "No current advisory: source data or official warning is stale."
            item["headline_bn"] = "হালনাগাদ পরামর্শ নেই: তথ্য বা সরকারি সতর্কবার্তার মেয়াদ শেষ।"
        return fresh_response({"mode": "live", "freshness": f, "bundle_id": m.get("bundle_id"),
                               "official_bmd_verified_at_generation": bool(m.get("bmd_verified")),
                               "research_only": True, "advisory": item})

    # Static website is served here only for installations using an actual
    # Python host. GitHub Pages hosts the same dist/site folder directly.
    if site.exists():
        app.mount("/", StaticFiles(directory=site, html=True), name="site")
    return app


app = create_app()
