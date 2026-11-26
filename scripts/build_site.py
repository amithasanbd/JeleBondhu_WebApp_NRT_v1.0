#!/usr/bin/env python3
"""Assemble the static site: app shell + static geodata + advisory bundle(s).

    python scripts/build_site.py --live dist/live --out dist/site [--demo data/demo]

The ``live/`` folder is whatever bundle the NRT run produced. ``demo/`` is the synthetic demo bundle and is always
labelled DEMO inside its manifest. The browser tries ``live/`` first and only falls back to ``demo/`` if ``live/`` is absent.
"""
import argparse, hashlib, json, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = [("data/spatial/eez.geojson", "static/eez.geojson"), ("data/spatial/ifa.geojson", "static/ifa.geojson"),
          ("data/spatial/bd_mpas.geojson", "static/bd_mpas.geojson"), ("data/spatial/fishing_grounds.geojson", "static/fishing_grounds.geojson"),
          ("data/static/stations.json", "static/stations.json"), ("data/static/species_context.json", "static/species_context.json"),
          ("data/static/climate_context.json", "static/climate_context.json"), ("data/static/archive_inventory.json", "static/archive_inventory.json"),
          ("data/static/validation_summary.json", "static/validation_summary.json")]
APP = ["index.html", "fisher.html", "manifest.webmanifest", "sw.js", "assets/css/app.css", "assets/js/icons.js", "assets/js/i18n.js",
       "assets/js/core.js", "assets/js/map.js", "assets/js/app.js", "assets/js/fisher.js", "assets/img/bathy_bg.png", "assets/img/bathy_bg.json",
       "assets/img/favicon.png", "assets/img/icon-192.png", "assets/img/icon-512.png", "assets/img/icon-96.png", "assets/img/icon-light.png", "assets/img/icon-dark.png",
       "assets/img/logo-full.png", "assets/img/m-fisherman.png", "assets/img/m-fish.png", "assets/img/m-waves.png", "assets/img/m-network.png",
       "assets/img/m-compass.png", "assets/img/m-together.png"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--live")
    ap.add_argument("--demo", default=str(ROOT / "data/demo"))
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shell = []
    for rel in APP:
        src = ROOT / rel
        if not src.exists():
            print("WARN missing", rel)
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out / rel)
        if rel != "sw.js":
            shell.append(rel)
    for s, d in STATIC:
        src = ROOT / s
        if src.exists():
            (out / d).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out / d)
            shell.append(d)
    for name, src in (("live", a.live), ("demo", a.demo)):
        if src and Path(src).exists() and (Path(src) / "manifest.json").exists():
            shutil.copytree(src, out / name)
        else:
            print(f"note: no {name} bundle")
    build = hashlib.sha256(("".join(sorted(shell)) + str(time.time())).encode()).hexdigest()[:10]
    sw = (out / "sw.js").read_text().replace("__BUILD__", build).replace("__SHELL__", json.dumps(["./"] + sorted(set(shell))))
    (out / "sw.js").write_text(sw)
    (out / ".nojekyll").write_text("")
    (out / "404.html").write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=fisher.html">')
    print("site built:", out, "build", build)


if __name__ == "__main__":
    main()
