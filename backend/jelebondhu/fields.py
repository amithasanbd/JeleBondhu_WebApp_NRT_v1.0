"""Gridded fields and bathymetry helpers (numpy/scipy only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from . import geo


@dataclass
class GriddedField:
    """A regular lat/lon field. ``values`` shape (ny, nx); NaN over land/missing."""

    lat: np.ndarray
    lon: np.ndarray
    values: np.ndarray
    name: str = ""
    units: str = ""

    def __post_init__(self):
        self.lat = np.asarray(self.lat, dtype=float)
        self.lon = np.asarray(self.lon, dtype=float)
        self.values = np.asarray(self.values, dtype=float)
        if self.values.shape != (len(self.lat), len(self.lon)):
            raise ValueError(f"{self.name}: values shape {self.values.shape} != ({len(self.lat)},{len(self.lon)})")
        if len(self.lat) > 1 and self.lat[0] > self.lat[-1]:
            self.lat = self.lat[::-1]
            self.values = self.values[::-1]

    # ------------------------------------------------------------------
    def sample(self, lat, lon, fill_radius_cells: int = 3) -> np.ndarray:
        """Bilinear sample at points. NaN corners are filled from the nearest valid
        cells inside ``fill_radius_cells`` (coastal strip), else NaN is returned."""
        lat = np.atleast_1d(np.asarray(lat, dtype=float))
        lon = np.atleast_1d(np.asarray(lon, dtype=float))
        v = self.values
        dy = self.lat[1] - self.lat[0]
        dx = self.lon[1] - self.lon[0]
        fy = (lat - self.lat[0]) / dy
        fx = (lon - self.lon[0]) / dx
        inb = (fy >= 0) & (fy <= len(self.lat) - 1) & (fx >= 0) & (fx <= len(self.lon) - 1)
        y0 = np.clip(np.floor(fy).astype(int), 0, len(self.lat) - 2)
        x0 = np.clip(np.floor(fx).astype(int), 0, len(self.lon) - 2)
        wy = np.clip(fy - y0, 0, 1)
        wx = np.clip(fx - x0, 0, 1)
        c00, c01 = v[y0, x0], v[y0, x0 + 1]
        c10, c11 = v[y0 + 1, x0], v[y0 + 1, x0 + 1]
        w = np.stack([(1 - wy) * (1 - wx), (1 - wy) * wx, wy * (1 - wx), wy * wx])
        c = np.stack([c00, c01, c10, c11])
        ok = np.isfinite(c)
        ws = np.where(ok, w, 0.0)
        tot = ws.sum(axis=0)
        out = np.where(tot > 1e-9, (np.where(ok, c, 0.0) * ws).sum(axis=0) / np.where(tot > 1e-9, tot, 1), np.nan)
        # nearest-valid fill for coastal points whose 4 corners are all NaN
        miss = np.isnan(out) & inb
        if miss.any() and fill_radius_cells > 0:
            for i in np.where(miss)[0]:
                yy, xx = int(round(fy[i])), int(round(fx[i]))
                r = fill_radius_cells
                sub = v[max(yy - r, 0) : yy + r + 1, max(xx - r, 0) : xx + r + 1]
                if np.isfinite(sub).any():
                    jj, kk = np.where(np.isfinite(sub))
                    cy = jj + max(yy - r, 0)
                    cx = kk + max(xx - r, 0)
                    d = (cy - fy[i]) ** 2 + (cx - fx[i]) ** 2
                    out[i] = sub[jj[np.argmin(d)], kk[np.argmin(d)]]
        out[~inb] = np.nan
        return out

    def gradient_per_km(self, log10: bool = False) -> "GriddedField":
        """Horizontal gradient magnitude per km on the native grid."""
        v = np.log10(np.clip(self.values, 1e-6, None)) if log10 else self.values
        lat_r = np.radians(self.lat)[:, None]
        dy_km = np.radians(self.lat[1] - self.lat[0]) * geo.EARTH_R_KM
        dx_km = np.radians(self.lon[1] - self.lon[0]) * geo.EARTH_R_KM * np.cos(lat_r)
        gy = np.gradient(v, axis=0) / dy_km
        gx = np.gradient(v, axis=1) / dx_km
        return GriddedField(self.lat, self.lon, np.hypot(gx, gy), name=self.name + "_front")


def convergence(u: GriddedField, v: GriddedField) -> GriddedField:
    """Positive convergence max(0, -(du/dx + dv/dy)) in s^-1 (native grid)."""
    lat_r = np.radians(u.lat)[:, None]
    dy_m = np.radians(u.lat[1] - u.lat[0]) * geo.EARTH_R_KM * 1000.0
    dx_m = np.radians(u.lon[1] - u.lon[0]) * geo.EARTH_R_KM * 1000.0 * np.cos(lat_r)
    div = np.gradient(u.values, axis=1) / dx_m + np.gradient(v.values, axis=0) / dy_m
    return GriddedField(u.lat, u.lon, np.clip(-div, 0, None), name="convergence", units="s-1")


# ----------------------------------------------------------------------------
class Bathymetry:
    """GEBCO-derived grid shipped in data/spatial/bathy_grid.npz (0.0125 deg)."""

    def __init__(self, path: Path | str):
        z = np.load(path, allow_pickle=False)
        self.lat = z["lat"].astype(float)
        self.lon = z["lon"].astype(float)
        self.elev_mean = z["elev_mean"].astype(float)
        self.elev_max = z["elev_max"].astype(float)
        self.dlat = self.lat[1] - self.lat[0]
        self.dlon = self.lon[1] - self.lon[0]

    def _idx(self, lat, lon):
        iy = np.rint((np.asarray(lat) - self.lat[0]) / self.dlat).astype(int)
        ix = np.rint((np.asarray(lon) - self.lon[0]) / self.dlon).astype(int)
        ok = (iy >= 0) & (iy < len(self.lat)) & (ix >= 0) & (ix < len(self.lon))
        return np.clip(iy, 0, len(self.lat) - 1), np.clip(ix, 0, len(self.lon) - 1), ok

    def depth_m(self, lat, lon) -> np.ndarray:
        """Positive water depth (m); <=0 on land; NaN outside the grid."""
        iy, ix, ok = self._idx(lat, lon)
        d = -self.elev_mean[iy, ix]
        return np.where(ok, d, np.nan)

    def is_wet(self, lat, lon, min_depth_m: float = 1.0) -> np.ndarray:
        """Conservative wetness: the whole 3x3 native block must be below sea level."""
        iy, ix, ok = self._idx(lat, lon)
        return ok & (-self.elev_max[iy, ix] >= min_depth_m)
