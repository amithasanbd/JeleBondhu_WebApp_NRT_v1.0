"""Small, dependency-light geospatial helpers (numpy only).

The pipeline deliberately avoids GeoPandas/Shapely at run time so that the
scheduled GitHub Action installs quickly and the maths stays auditable.
Polygons are lists of rings (lon, lat); the first ring is the exterior and
the others are holes (even-odd rule is used, so ring order is not critical).
"""
from __future__ import annotations

import math
import struct
from typing import Iterable, List, Sequence, Tuple

import numpy as np

EARTH_R_KM = 6371.0088
NM_KM = 1.852


# ----------------------------------------------------------------------------
# distances
# ----------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.asarray, (lat1, lon1, lat2, lon2))
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def interpolate_path(lat1: float, lon1: float, lat2, lon2, n: int):
    """Great-circle sample points (n+1 incl. both ends) for arrays of endpoints.

    ``lat2``/``lon2`` may be arrays; returns arrays shaped (len, n+1).
    """
    lat2 = np.atleast_1d(np.asarray(lat2, dtype=float))
    lon2 = np.atleast_1d(np.asarray(lon2, dtype=float))
    f = np.linspace(0.0, 1.0, n + 1)[None, :]
    p1, l1 = math.radians(lat1), math.radians(lon1)
    p2, l2 = np.radians(lat2)[:, None], np.radians(lon2)[:, None]
    # angular distance
    d = np.arccos(
        np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(l2 - l1), -1, 1)
    )
    d = np.where(d < 1e-9, 1e-9, d)
    a = np.sin((1 - f) * d) / np.sin(d)
    b = np.sin(f * d) / np.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * np.cos(p2) * np.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * np.cos(p2) * np.sin(l2)
    z = a * math.sin(p1) + b * np.sin(p2)
    lat = np.degrees(np.arctan2(z, np.sqrt(x * x + y * y)))
    lon = np.degrees(np.arctan2(y, x))
    return lat, lon


# ----------------------------------------------------------------------------
# polygon tests
# ----------------------------------------------------------------------------
def _ring_array(r) -> np.ndarray:
    a = np.asarray(r, dtype=float)
    if a.ndim != 2 or a.shape[1] < 2:
        raise ValueError("ring must be an (n,2) array of lon/lat")
    a = a[:, :2]
    if len(a) and not np.allclose(a[0], a[-1]):
        a = np.vstack([a, a[:1]])
    return a


def points_in_rings(lon, lat, rings: Sequence, chunk: int = 512) -> np.ndarray:
    """Even-odd point-in-polygon for one polygon given as list of rings.

    Boundary points are treated as inside (``covers`` semantics) via a small
    tolerance test against all edges.
    """
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    inside = np.zeros(lon.shape, dtype=bool)
    for ring in rings:
        r = _ring_array(ring)
        x1, y1 = r[:-1, 0], r[:-1, 1]
        x2, y2 = r[1:, 0], r[1:, 1]
        for i in range(0, len(lon), chunk):
            px = lon[i : i + chunk, None]
            py = lat[i : i + chunk, None]
            cond = (y1 > py) != (y2 > py)
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            cross = cond & (px < xint)
            inside[i : i + chunk] ^= (cross.sum(axis=1) % 2 == 1)
    return inside


def covers(lon, lat, rings: Sequence, tol_deg: float = 1e-9) -> np.ndarray:
    """Inside OR on the boundary of the polygon."""
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    ins = points_in_rings(lon, lat, rings)
    if ins.all():
        return ins
    d = distance_to_rings_km(lon, lat, rings)
    return ins | (d <= tol_deg * 111.0)


def distance_to_rings_km(lon, lat, rings: Sequence) -> np.ndarray:
    """Minimum distance (km) from points to any edge of the rings.

    Uses a local equirectangular projection around each point's latitude,
    accurate to well under 1% for the sub-100 km distances used here.
    """
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    best = np.full(lon.shape, np.inf)
    for ring in rings:
        r = _ring_array(ring)
        ax, ay = r[:-1, 0], r[:-1, 1]
        bx, by = r[1:, 0], r[1:, 1]
        for i in range(0, len(lon), 512):
            px = lon[i : i + 512, None]
            py = lat[i : i + 512, None]
            k = np.cos(np.radians(py))
            ux = (bx - ax) * k * 111.32
            uy = (by - ay) * 110.57
            wx = (px - ax) * k * 111.32
            wy = (py - ay) * 110.57
            L2 = ux * ux + uy * uy
            with np.errstate(divide="ignore", invalid="ignore"):
                t = np.where(L2 > 0, (wx * ux + wy * uy) / L2, 0.0)
            t = np.clip(t, 0, 1)
            dx = wx - t * ux
            dy = wy - t * uy
            d = np.sqrt(dx * dx + dy * dy).min(axis=1)
            best[i : i + 512] = np.minimum(best[i : i + 512], d)
    return best


def polygon_area_km2(ring) -> float:
    """Ellipsoid-free (spherical) polygon area for sanity checks."""
    r = _ring_array(ring)
    lat0 = np.radians(r[:, 1].mean())
    x = np.radians(r[:, 0]) * math.cos(lat0) * EARTH_R_KM
    y = np.radians(r[:, 1]) * EARTH_R_KM
    return abs(0.5 * np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def ring_self_intersects(ring) -> bool:
    """O(n^2) self-intersection test (adequate for the small rings used here)."""
    r = _ring_array(ring)
    n = len(r) - 1
    a = r[:-1]
    b = r[1:]

    def ccw(p, q, s):
        return (s[..., 1] - p[..., 1]) * (q[..., 0] - p[..., 0]) - (q[..., 1] - p[..., 1]) * (
            s[..., 0] - p[..., 0]
        )

    for i in range(n):
        p, q = a[i], b[i]
        d1 = ccw(p, q, a)
        d2 = ccw(p, q, b)
        d3 = ccw(a, b, p[None, :])
        d4 = ccw(a, b, q[None, :])
        hit = (d1 * d2 < 0) & (d3 * d4 < 0)
        hit[max(i - 1, 0) : i + 2] = False
        if i == 0:
            hit[-1] = False
        if hit.any():
            return True
    return False


def order_ring_ccw_hull(points: Iterable[Tuple[float, float]]):
    """Return points ordered around their centroid (for 4-corner rectangles)."""
    p = np.asarray(list(points), dtype=float)
    c = p.mean(axis=0)
    ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
    return p[np.argsort(ang)].tolist()


# ----------------------------------------------------------------------------
# minimal shapefile reader (polygons only; used by scripts/prepare_static_data.py)
# ----------------------------------------------------------------------------
def read_polygon_shapefile(path: str) -> List[List[np.ndarray]]:
    """Return list of polygons (each a list of rings as (n,2) arrays)."""
    with open(path, "rb") as fh:
        b = fh.read()
    (code,) = struct.unpack(">i", b[:4])
    if code != 9994:
        raise ValueError("not a shapefile")
    pos = 100
    out = []
    while pos + 8 <= len(b):
        _, clen = struct.unpack(">2i", b[pos : pos + 8])
        pos += 8
        data = b[pos : pos + clen * 2]
        pos += clen * 2
        (stype,) = struct.unpack("<i", data[:4])
        if stype not in (5, 15, 25):  # polygon, polygonZ, polygonM
            continue
        nparts, npts = struct.unpack("<2i", data[36:44])
        parts = list(struct.unpack("<%di" % nparts, data[44 : 44 + 4 * nparts])) + [npts]
        off = 44 + 4 * nparts
        pts = np.frombuffer(data[off : off + 16 * npts], dtype="<f8").reshape(-1, 2)
        out.append([pts[parts[i] : parts[i + 1]].copy() for i in range(nparts)])
    return out


def douglas_peucker(pts: np.ndarray, tol: float) -> np.ndarray:
    """Iterative Douglas-Peucker simplification (degrees)."""
    n = len(pts)
    if n < 4:
        return pts
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        a, b = pts[s], pts[e]
        seg = pts[s + 1 : e]
        ab = b - a
        L = np.hypot(*ab)
        if L == 0:
            d = np.hypot(*(seg - a).T)
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / L
        i = int(np.argmax(d))
        if d[i] > tol:
            idx = s + 1 + i
            keep[idx] = True
            stack.append((s, idx))
            stack.append((idx, e))
    return pts[keep]
