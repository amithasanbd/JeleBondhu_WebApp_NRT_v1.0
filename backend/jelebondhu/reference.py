"""Optional calibrated reference (built in Colab Pro from the 1995-2025 archive).

``data/reference/climatology.npz`` holds monthly station climatologies so that anomaly
components can be scored and the PAI can be switched from 'experimental' to 'frozen'.
Absent file => the pipeline runs in experimental mode and says so everywhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np

VARS = ("sst", "zos")


def load_reference(root: Path, n_stations: int) -> Optional[Dict[str, np.ndarray]]:
    p = Path(root) / "data/reference/climatology.npz"
    if not p.exists():
        return None
    z = np.load(p, allow_pickle=False)
    ref = {}
    for v in VARS:
        if f"{v}_mean" in z:
            a = z[f"{v}_mean"]
            if a.shape != (12, n_stations):
                raise ValueError(f"reference {v}_mean has shape {a.shape}, expected (12,{n_stations})")
            ref[v] = a.astype(float)
    return ref or None


def anomalies(ref: Optional[Dict[str, np.ndarray]], month: int, variables: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    out = {}
    if not ref:
        return out
    for v in VARS:
        if v in ref and v in variables:
            out[f"{v}_anom"] = variables[v] - ref[v][month - 1]
    return out


def build_reference(df, n_stations: int, out_path: Path | str):
    """Build climatology.npz from a long table (pandas DataFrame).

    Required columns: ``station_idx`` (0..n-1 in data/static/stations.json order), ``month`` (1-12),
    and any of ``sst`` / ``zos`` (reference-period daily or monthly values).
    """
    arrays = {}
    for v in VARS:
        if v in df.columns:
            g = df.groupby(["month", "station_idx"])[v].mean().unstack("station_idx").reindex(index=range(1, 13), columns=range(n_stations))
            arrays[f"{v}_mean"] = g.to_numpy(dtype="float32")
    if not arrays:
        raise ValueError("no usable columns")
    np.savez_compressed(out_path, **arrays)
    return {k: v.shape for k, v in arrays.items()}
