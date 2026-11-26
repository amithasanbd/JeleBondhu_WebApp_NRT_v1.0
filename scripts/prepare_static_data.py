#!/usr/bin/env python3
"""Build the small, versioned static data products from the raw thesis files.

Raw inputs (NOT committed - too large / third-party licences) are read from
``--raw`` (default ``data/raw``):

    gebco.nc                                       GEBCO 2025 (classic NetCDF, 15 arc-sec)
    BD_EEZ_Shape_File.zip                          EEZ polygon (WGS84)
    IFA_Shape_FileFinal.zip                        Inshore Fishing Area polygon
    PFZs_Thesis_EEZ_Point_Coordinate_Values.xlsx   2,125 PFZ analysis stations
    JeleBondhu_Commercial_Fisheries_PlotReady_EEZ_*.xlsx
    Ocean_Nino_Index_ONI_Data_1950-Present.xlsx
    IOD_INDEX_1950-Present.xlsx
    all_archived_dataset_metadata.csv
    stations-2025.json                             (optional) thesis 2025 seasonal PAI

Outputs: data/spatial/*, data/static/*, assets/img/bathy_bg.png

Usage:  python scripts/prepare_static_data.py --raw data/raw
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from jelebondhu import geo  # noqa: E402

# map extent used by the frontend background raster
BBOX = dict(lon0=88.2, lon1=92.9, lat0=17.5, lat1=23.0)

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon",
           6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Post-monsoon", 11: "Post-monsoon"}


def jdump(obj, path, indent=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":") if indent is None else None, indent=indent)
    print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size/1024:.1f} KB)")


# ----------------------------------------------------------------------------
# bathymetry
# ----------------------------------------------------------------------------
def build_bathymetry(raw: Path):
    from scipy.io import netcdf_file

    f = netcdf_file(str(raw / "gebco.nc"), mmap=False)
    lat = np.array(f.variables["lat"][:], dtype=float)
    lon = np.array(f.variables["lon"][:], dtype=float)
    z = np.array(f.variables["elevation"][:])
    fill = -32767
    z = np.where(z == fill, 0, z).astype(np.int16)
    i0, i1 = np.searchsorted(lat, [BBOX["lat0"], BBOX["lat1"]])
    j0, j1 = np.searchsorted(lon, [BBOX["lon0"], BBOX["lon1"]])
    sub = z[i0:i1, j0:j1]
    la, lo = lat[i0:i1], lon[j0:j1]
    k = 3  # 15 arc-sec -> 45 arc-sec (0.0125 deg)
    ny, nx = (sub.shape[0] // k) * k, (sub.shape[1] // k) * k
    blk = sub[:ny, :nx].reshape(ny // k, k, nx // k, k)
    elev_mean = blk.mean(axis=(1, 3)).round().astype(np.int16)
    elev_max = blk.max(axis=(1, 3)).astype(np.int16)  # conservative land mask
    lat_c = la[:ny].reshape(-1, k).mean(axis=1)
    lon_c = lo[:nx].reshape(-1, k).mean(axis=1)
    out = ROOT / "data/spatial/bathy_grid.npz"
    np.savez_compressed(out, lat=lat_c.astype("f4"), lon=lon_c.astype("f4"), elev_mean=elev_mean, elev_max=elev_max,
                        meta=np.array(json.dumps({"source": "GEBCO 2025 grid (supplied gebco.nc)", "block": k,
                                                  "note": "elev_max = max elevation in 3x3 block (land mask)"})))
    print(f"  wrote {out.relative_to(ROOT)} ({out.stat().st_size/1024:.1f} KB) shape={elev_mean.shape}")
    return (la, lo, sub)


def render_background(la, lo, sub):
    """Offline bathymetry/land raster used behind the canvas map."""
    from PIL import Image

    step = 2
    z = sub[::step, ::step].astype(float)
    lat = la[::step]
    lon = lo[::step]
    ny, nx = z.shape
    # hillshade
    dzdy, dzdx = np.gradient(z)
    shade = np.clip(0.5 + (dzdx - dzdy) / 60.0, 0, 1)
    img = np.zeros((ny, nx, 3), dtype=float)
    depth = np.clip(-z, 0, 4500)
    t = np.sqrt(depth / 4500.0)
    # shallow = pale cyan, deep = navy
    c0 = np.array([190, 232, 240]); c1 = np.array([8, 40, 84])
    ocean = c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]
    ocean *= (0.88 + 0.18 * shade[..., None])
    h = np.clip(z, 0, 300) / 300.0
    land = np.array([226, 222, 205])[None, None, :] * (1 - h[..., None]) + np.array([170, 190, 150])[None, None, :] * h[..., None]
    land *= (0.92 + 0.12 * shade[..., None])
    img = np.where((z > 0)[..., None], land, ocean)
    img = np.clip(img, 0, 255).astype(np.uint8)[::-1]  # north up
    im = Image.fromarray(img, "RGB")
    im = im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = ROOT / "assets/img/bathy_bg.png"
    im.save(out, optimize=True)
    meta = {"lon0": float(lon[0]), "lon1": float(lon[-1]), "lat0": float(lat[0]), "lat1": float(lat[-1]),
            "width": int(nx), "height": int(ny)}
    jdump(meta, ROOT / "assets/img/bathy_bg.json")
    print(f"  wrote {out.relative_to(ROOT)} ({out.stat().st_size/1024:.1f} KB) {nx}x{ny}")


def depth_at(la, lo, z, lat, lon):
    """Bilinear sample of the native GEBCO grid (positive = depth m)."""
    fy = (np.asarray(lat) - la[0]) / (la[1] - la[0])
    fx = (np.asarray(lon) - lo[0]) / (lo[1] - lo[0])
    y0 = np.clip(np.floor(fy).astype(int), 0, len(la) - 2)
    x0 = np.clip(np.floor(fx).astype(int), 0, len(lo) - 2)
    wy, wx = fy - y0, fx - x0
    v = (z[y0, x0] * (1 - wy) * (1 - wx) + z[y0 + 1, x0] * wy * (1 - wx) + z[y0, x0 + 1] * (1 - wy) * wx
         + z[y0 + 1, x0 + 1] * wy * wx)
    return -v


# ----------------------------------------------------------------------------
# polygons
# ----------------------------------------------------------------------------
def read_zip_shp(zpath: Path):
    with zipfile.ZipFile(zpath) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".shp")][0]
        tmp = ROOT / ".tmp_shp"
        tmp.mkdir(exist_ok=True)
        z.extract(name, tmp)
        p = tmp / name
        polys = geo.read_polygon_shapefile(str(p))
    return polys


def _signed_area(r):
    r = np.asarray(r)
    return 0.5 * np.sum(r[:-1, 0] * r[1:, 1] - r[1:, 0] * r[:-1, 1])


def to_geojson_multipolygon(rings, props, tol=0.0, min_hole_deg2=0.0):
    """Group shapefile rings into polygons (clockwise = exterior, ccw = hole)."""
    exteriors, holes = [], []
    for r in rings:
        r = np.asarray(r)
        if len(r) < 4:
            continue
        (exteriors if _signed_area(r) < 0 else holes).append(r)
    polys = [[e] for e in exteriors]
    for h in holes:
        if min_hole_deg2 and abs(_signed_area(h)) < min_hole_deg2:
            continue
        for p in polys:
            if geo.points_in_rings(h[:1, 0], h[:1, 1], [p[0]])[0]:
                p.append(h)
                break
    coords = []
    for p in polys:
        rr = []
        for r in p:
            if tol:
                r = geo.douglas_peucker(r, tol)
            if len(r) >= 4:
                rr.append([[round(float(x), 5), round(float(y), 5)] for x, y in r])
        if rr:
            coords.append(rr)
    return {"type": "Feature", "properties": props, "geometry": {"type": "MultiPolygon", "coordinates": coords}}


# --- MPAs (supplied coordinate inventory, Filter-3 manual v4.1) -----------------
MPAS = [
    dict(id="MPA_SONG", name="Swatch of No Ground (SoNG) MPA", short="SoNG", reported_km2=1738,
         legal_status="approximate_extent",
         note="Approximate extent only (bounding rectangle) - authoritative polygon required. UNKNOWN until resolved.",
         pts=[(89.3, 21.0), (90.0, 21.0), (90.0, 21.7), (89.3, 21.7)], source="R11"),
    dict(id="MPA_STMARTIN", name="Saint Martin's Island MPA", short="Saint Martin", reported_km2=1743,
         legal_status="gazette_candidate", note="12 supplied vertices; verify gazette and area before release.",
         pts=[(91.818878, 20.569414), (92.219133, 20.78215), (92.330861, 20.742883), (92.349161, 20.710347),
              (92.320008, 20.666692), (92.337083, 20.607919), (92.413583, 20.552467), (92.396717, 20.475044),
              (92.337053, 20.396156), (92.313969, 20.408344), (92.164219, 20.470006), (91.996819, 20.391122)],
         source="R11"),
    dict(id="MPA_NIJHUM", name="Nijhum Dwip MPA / Marine Reserve", short="Nijhum Dwip", reported_km2=3188,
         legal_status="gazette_candidate", note="10 supplied vertices; verify gazette and area before release.",
         pts=[(90.404803, 21.813628), (90.599089, 21.813628), (90.784011, 22.053947), (90.924308, 22.053947),
              (90.956106, 22.113492), (91.002008, 22.11355), (91.102769, 22.074408), (91.281522, 22.074408),
              (91.281522, 21.659042), (90.404803, 21.659042)], source="R11"),
    dict(id="MPA_NAF", name="Naf Marine Protected Area", short="Naf MPA", reported_km2=734.17,
         legal_status="gazette_candidate", note="10 supplied vertices; verify gazette and area before release.",
         pts=[(92.209539, 20.95), (92.074997, 20.95), (91.95, 20.75), (91.95, 20.637656), (92.219133, 20.78215),
              (92.330861, 20.742883), (92.349161, 20.710347), (92.356889, 20.6935), (92.368667, 20.704389),
              (92.364031, 20.746297)], source="R11"),
    dict(id="MPA_RESERVE_MG_SP", name="Marine Reserve: Middle Ground & South Patches", short="Middle/South Reserve",
         reported_km2=698, legal_status="candidate_geometry",
         note="Four supplied corners form a self-crossing ring in the original order; re-ordered rectangle is ~65 km2, not 698 km2. Original gazette required.",
         pts=[(91.533333, 21.133333), (91.333333, 21.133333), (91.333333, 20.85), (91.533333, 20.85)],
         reorder=True, source="R11"),
    dict(id="MPA_KUAKATA", name="Kuakata Marine Protected Area (2026)", short="Kuakata MPA", reported_km2=4240,
         legal_status="gazette_candidate", note="14 supplied vertices; verify gazette and area before release.",
         pts=[(90.408056, 21.822778), (90.407778, 21.294167), (90.25, 21.233333), (89.680556, 21.390556),
              (89.680556, 21.632778), (89.939444, 21.835556), (89.939722, 21.943889), (90.022222, 21.943889),
              (90.022222, 21.896389), (90.069444, 21.867778), (90.084722, 21.855556), (90.265556, 21.852222),
              (90.326111, 21.853611), (90.358056, 21.858889)], source="R11"),
    dict(id="MPA_SALIMPUR", name="Salimpur Marine Protected Area (2026)", short="Salimpur MPA", reported_km2=185,
         legal_status="gazette_provisional",
         note="10 vertices from the 2 Nov 2026 Gazette (supersedes the 24 May notice). Decimal-degree column used provisionally; decimal-minute column disagrees - request authority confirmation [R10].",
         pts=[(91.586749, 22.567731), (91.72333, 22.305038), (91.762901, 22.317701), (91.7621, 22.326424),
              (91.766192, 22.326634), (91.74708, 22.399693), (91.730132, 22.389455), (91.680259, 22.485548),
              (91.702388, 22.497611), (91.620105, 22.590816)], source="R10"),
]

FISHING_GROUNDS = [
    dict(id="FG_SP", name="South Patches", name_bn="সাউথ প্যাচেস", box=(91.30, 91.83, 20.83, 21.67)),
    dict(id="FG_SSP", name="South of South Patches", name_bn="সাউথ অব সাউথ প্যাচেস", box=(91.30, 92.33, 20.25, 20.83)),
    dict(id="FG_MG", name="Middle Ground", name_bn="মিডল গ্রাউন্ড", box=(90.33, 91.50, 20.42, 21.33)),
    dict(id="FG_SONG", name="Swatch of No Ground", name_bn="সোয়াচ অব নো গ্রাউন্ড", box=(89.58, 90.17, 20.92, 21.92)),
]


def build_polygons(raw: Path):
    eez_polys = read_zip_shp(next(raw.glob("*EEZ*Shape*.zip")))
    ifa_polys = read_zip_shp(next(raw.glob("*IFA*.zip")))
    eez_rings = eez_polys[0]
    # EEZ display geometry: exterior + larger islands only, simplified
    feat = to_geojson_multipolygon(eez_rings, {"id": "BD_EEZ", "name": "Bangladesh EEZ", "crs": "EPSG:4326",
                                           "note": "display-simplified; analytical masking uses the full polygon"},
                              tol=0.004, min_hole_deg2=2e-4)
    jdump({"type": "FeatureCollection", "features": [feat]}, ROOT / "data/spatial/eez.geojson")

    ifa_rings = ifa_polys[0]
    bad = [geo.ring_self_intersects(r) for r in ifa_rings]
    feat = to_geojson_multipolygon(ifa_rings, {
        "id": "BD_IFA", "name": "Inshore Fishing Area (project layer, ~40 m)", "crs": "EPSG:4326",
        "topology_status": ("ring self-intersection found - repair before regulatory use" if any(bad) else
                            "simple-ring self-intersection test passed; full OGC validity (GEOS) NOT run - review in GIS before regulatory use"),
        "legal_note": "Project layer. Not a legal boundary and not an automatic permission."}, tol=0.0005)
    jdump({"type": "FeatureCollection", "features": [feat]}, ROOT / "data/spatial/ifa.geojson")
    print("  IFA ring self-intersection flags:", bad)

    feats = []
    for m in MPAS:
        pts = geo.order_ring_ccw_hull(m["pts"]) if m.get("reorder") else m["pts"]
        ring = [[x, y] for x, y in pts]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        arr = np.array(ring)
        orig = np.array(list(m["pts"]) + [m["pts"][0]])
        props = {k: v for k, v in m.items() if k not in ("pts", "reorder")}
        props["computed_km2"] = round(geo.polygon_area_km2(arr), 1)
        props["self_intersecting_as_supplied"] = bool(geo.ring_self_intersects(orig))
        props["verification_required"] = True
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    jdump({"type": "FeatureCollection", "spatial_version": "SP-2026-11-26.1",
           "features": feats}, ROOT / "data/spatial/bd_mpas.geojson", indent=1)

    gfeats = []
    for g in FISHING_GROUNDS:
        x0, x1, y0, y1 = g["box"]
        gfeats.append({"type": "Feature", "properties": {"id": g["id"], "name": g["name"], "name_bn": g["name_bn"],
                                                         "standalone_ban": False,
                                                         "note": "Traditional ground extent (manual v4.1). Metadata only - no blanket ban, no permission."},
                       "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}})
    jdump({"type": "FeatureCollection", "features": gfeats}, ROOT / "data/spatial/fishing_grounds.geojson")
    return eez_rings


# ----------------------------------------------------------------------------
# stations
# ----------------------------------------------------------------------------
def build_stations(raw: Path, eez_rings, gebco):
    import openpyxl
    from openpyxl.reader.excel import ExcelReader

    ExcelReader.read_chartsheet = lambda self, *a, **k: None
    wb = openpyxl.load_workbook(next(raw.glob("PFZs_Thesis*.xlsx")), read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))[1:]
    ids = [int(r[0]) for r in rows if r[0] is not None]
    lon = np.array([float(r[1]) for r in rows if r[0] is not None])
    lat = np.array([float(r[2]) for r in rows if r[0] is not None])
    la, lo, z = gebco
    depth = depth_at(la, lo, z, lat, lon)
    in_eez = geo.points_in_rings(lon, lat, eez_rings)
    print(f"  stations: {len(ids)}; inside EEZ polygon: {int(in_eez.sum())}; wet (depth>0): {int((depth>0).sum())}")
    jdump({"n": len(ids), "id": ids, "lat": [round(float(v), 6) for v in lat], "lon": [round(float(v), 6) for v in lon],
           "depth_m": [round(float(v), 1) for v in depth], "in_eez": [int(v) for v in in_eez],
           "source": "PFZs_Thesis_EEZ_Point_Coordinate_Values.xlsx; depth from GEBCO bilinear"},
          ROOT / "data/static/stations.json")
    return ids, lat, lon


def build_thesis_pai(raw: Path, ids, lat, lon):
    p = raw / "stations-2025.json"
    if not p.exists():
        print("  (skip thesis PAI 2025: stations-2025.json not found)")
        return
    S = json.load(open(p, encoding="utf8"))
    by = {s["id"]: s for s in S}
    out = {}
    for season in ("Pre-monsoon", "Monsoon", "Post-monsoon", "Winter"):
        arr = []
        for sid in ids:
            s = by.get(sid)
            try:
                arr.append(int(round(float(s["seasons"][season]["pai"]) * 1000)))
            except Exception:
                arr.append(-1)
        out[season] = arr
    mism = sum(1 for sid, a, b in zip(ids, lat, lon) if sid in by and (abs(by[sid]["lat"] - a) > 1e-4 or abs(by[sid]["lon"] - b) > 1e-4))
    jdump({"unit": "PAI x1000 (thesis 2025 station-season state, R2 release); -1 = missing", "station_mismatches": mism,
           "pai": out}, ROOT / "data/static/thesis_pai_2025.json")


# ----------------------------------------------------------------------------
# fisheries context, climate indices, archive inventory
# ----------------------------------------------------------------------------
def build_fisheries_context(raw: Path):
    import pandas as pd

    p = next(raw.glob("*Commercial_Fisheries_PlotReady*.xlsx"))
    df = pd.read_excel(p, engine="openpyxl")
    df["Season3"] = df["Month"].map(SEASONS)
    species = []
    for sp, g in df.groupby("Scientific_Name"):
        row = {"scientific": sp, "n_records": int(len(g)), "n_events": int(g["DLC_ID"].nunique()),
               "mean_cpue": round(float(g["CPUE"].mean()), 3),
               "season_cpue": {k: round(float(v), 3) for k, v in g.groupby("Season3")["CPUE"].mean().items()}}
        species.append(row)
    species.sort(key=lambda r: -r["mean_cpue"])
    obs_months = sorted(int(m) for m in df["Month"].unique())
    ev = df.drop_duplicates("DLC_ID")
    flags = {
        "records": int(len(df)), "species": int(df["Scientific_Name"].nunique()), "distinct_events": int(ev.shape[0]),
        "years": f"{int(df['Calendar_Year'].min())}-{int(df['Calendar_Year'].max())}",
        "months_with_records": obs_months,
        "months_without_records": [m for m in range(1, 13) if m not in obs_months],
        "bbox": [round(float(ev["Longitude_dd"].min()), 3), round(float(ev["Latitude_dd"].min()), 3),
                 round(float(ev["Longitude_dd"].max()), 3), round(float(ev["Latitude_dd"].max()), 3)],
    }
    jdump({"context_only": True, "note": "Observed CPUE context. Not a catch forecast. 26 species rows share each event; "
           "never split these rows randomly for model testing (group by event).", "summary": flags,
           "species": species}, ROOT / "data/static/species_context.json")
    return df


def build_climate(raw: Path):
    import openpyxl

    def read(fn):
        wb = openpyxl.load_workbook(next(raw.glob(fn)), data_only=True)
        return list(wb.active.iter_rows(values_only=True))

    oni = read("Ocean_Nino_Index*.xlsx")
    iod = read("IOD_INDEX*.xlsx")
    seas = [c for c in oni[0][1:]]

    def num(v):
        try:
            return float(v)
        except Exception:
            return None

    oni_series = []
    for r in oni[1:]:
        for i, name in enumerate(seas):
            v = num(r[i + 1])
            if v is not None:
                oni_series.append([int(r[0]), name, v])
    iod_series = []
    for r in iod[1:]:
        for m in range(12):
            v = num(r[m + 1])
            if v is not None:
                iod_series.append([int(r[0]), m + 1, v])
    last_oni, last_iod = oni_series[-1], iod_series[-1]

    def phase_oni(v):
        return "El Nino" if v >= 0.5 else "La Nina" if v <= -0.5 else "Neutral"

    def phase_iod(v):
        return "Positive IOD" if v >= 0.4 else "Negative IOD" if v <= -0.4 else "Neutral IOD"

    jdump({"oni_last": {"year": last_oni[0], "season": last_oni[1], "value": last_oni[2], "phase": phase_oni(last_oni[2])},
           "iod_last": {"year": last_iod[0], "month": last_iod[1], "value": last_iod[2], "phase": phase_iod(last_iod[2])},
           "oni_recent": oni_series[-24:], "iod_recent": iod_series[-24:],
           "note": "Context only; phase thresholds ONI +/-0.5, IOD(DMI) +/-0.4. Not used in the advisory decision."},
          ROOT / "data/static/climate_context.json")


def build_inventory(raw: Path):
    p = raw / "all_archived_dataset_metadata.csv"
    if not p.exists():
        return
    agg = defaultdict(lambda: {"files": 0, "mb": 0.0, "years": set(), "vars": set()})
    with open(p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            top = r["folder_name"].split("/")[0]
            a = agg[top]
            a["files"] += 1
            try:
                a["mb"] += float(r["file_size_MB"])
            except Exception:
                pass
            try:
                a["years"].add(int(float(r["year_from_filename"])))
            except Exception:
                pass
            for v in (r.get("variables") or "").split(","):
                v = v.strip()
                if v and v not in ("time", "lon", "lat", "latitude", "longitude", "valid_time"):
                    a["vars"].add(v)
    rows = []
    for k, a in sorted(agg.items(), key=lambda kv: -kv[1]["files"]):
        yrs = sorted(a["years"])
        rows.append({"folder": k, "files": a["files"], "size_gb": round(a["mb"] / 1024, 2),
                     "years": f"{yrs[0]}-{yrs[-1]}" if yrs else "", "variables": sorted(a["vars"])[:12]})
    jdump({"total_files": sum(r["files"] for r in rows), "total_gb": round(sum(r["size_gb"] for r in rows), 1),
           "note": "Registry of the archived historical dataset (metadata only; the master archive stays private on Google Drive).",
           "folders": rows}, ROOT / "data/static/archive_inventory.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data/raw"))
    args = ap.parse_args()
    raw = Path(args.raw)
    print("== bathymetry"); gebco = build_bathymetry(raw); render_background(*gebco)
    print("== polygons"); eez = build_polygons(raw)
    print("== stations"); ids, lat, lon = build_stations(raw, eez, gebco)
    print("== thesis PAI 2025"); build_thesis_pai(raw, ids, lat, lon)
    print("== fisheries context"); build_fisheries_context(raw)
    print("== climate indices"); build_climate(raw)
    print("== archive inventory"); build_inventory(raw)
    import shutil
    shutil.rmtree(ROOT / ".tmp_shp", ignore_errors=True)


if __name__ == "__main__":
    main()
