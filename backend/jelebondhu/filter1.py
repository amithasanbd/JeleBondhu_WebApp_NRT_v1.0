"""Filter 1 - environmental fishing suitability (PAI).

PAI = sum_k W_k * S_k with S_VI entering as (1 - VI). Each sub-index S_k is a weighted mean of
component scores in [0,1] produced by transparent membership functions defined in
config/filter1_environment.json. Components lacking input data are dropped and the
remaining weights renormalised *per cell*; a sub-index is valid only if at least
``min_component_weight_fraction`` of its weight is available.

Output is *environmental suitability* - never a probability of catching fish.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


def membership(fn: dict, x: np.ndarray) -> np.ndarray:
    t, p = fn["type"], fn["p"]
    x = np.asarray(x, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        if t == "linear":
            y = (x - p[0]) / (p[1] - p[0])
        elif t == "inv_linear":
            y = (p[1] - x) / (p[1] - p[0])
        elif t == "log_linear":
            y = (np.log10(np.clip(x, 1e-9, None)) - np.log10(p[0])) / (np.log10(p[1]) - np.log10(p[0]))
        elif t == "trapezoid":
            a, b, c, d = p
            up = (x - a) / (b - a)
            dn = (d - x) / (d - c)
            y = np.minimum(up, dn)
            y = np.where((x >= b) & (x <= c), 1.0, y)
        else:
            raise ValueError(f"unknown membership type {t}")
    y = np.clip(y, 0.0, 1.0)
    return np.where(np.isfinite(x), y, np.nan)


def compute(cfg_f1: dict, variables: Dict[str, np.ndarray], wet: np.ndarray, have_reference: bool = False) -> dict:
    """Compute sub-indices, PAI, completeness and per-component contributions.

    ``variables``: station-sampled arrays keyed by variable name (NaN = missing).
    Returns dict of arrays (length n) + metadata.
    """
    n = len(wet)
    comps = cfg_f1["components"]
    subs = cfg_f1["subindices"]
    S: Dict[str, np.ndarray] = {}
    avail: Dict[str, np.ndarray] = {}
    score = {}
    used_vars = set()
    for c in comps:
        if c.get("needs_reference") and not have_reference:
            score[c["id"]] = np.full(n, np.nan)
            continue
        x = variables.get(c["var"])
        if x is None:
            score[c["id"]] = np.full(n, np.nan)
            continue
        score[c["id"]] = membership(c["fn"], x)
        if np.isfinite(score[c["id"]]).any():
            used_vars.add(c["var"])
    min_frac = cfg_f1.get("min_component_weight_fraction", 0.5)
    for sid in subs:
        cs = [c for c in comps if c["sub"] == sid]
        W = np.array([c["w"] for c in cs])
        M = np.stack([score[c["id"]] for c in cs], axis=0)  # (nc, n)
        ok = np.isfinite(M)
        wsum = (ok * W[:, None]).sum(axis=0)
        val = np.where(wsum > 0, (np.nan_to_num(M) * W[:, None]).sum(axis=0) / np.where(wsum > 0, wsum, 1), np.nan)
        frac = wsum / W.sum()
        val = np.where(frac >= min_frac, val, np.nan)
        S[sid], avail[sid] = val, frac
    wts = {k: v["weight"] for k, v in subs.items()}
    tot = sum(wts.values())
    pai = np.zeros(n)
    for sid, v in subs.items():
        s = S[sid]
        s = 1.0 - s if v["invert"] else s
        pai = pai + wts[sid] / tot * s  # NaN propagates: all four sub-indices are required
    pai = np.where(wet, pai, np.nan)
    completeness = np.nanmean(np.stack([avail[k] for k in subs]), axis=0)

    # per-component contribution to PAI (for explainability)
    contrib = {}
    for sid, v in subs.items():
        cs = [c for c in comps if c["sub"] == sid]
        W = np.array([c["w"] for c in cs])
        wsum = np.stack([np.isfinite(score[c["id"]]) * c["w"] for c in cs]).sum(axis=0)
        for c in cs:
            sc = score[c["id"]]
            sc = 1.0 - sc if v["invert"] else sc
            with np.errstate(invalid="ignore", divide="ignore"):
                contrib[c["id"]] = wts[sid] / tot * (c["w"] / np.where(wsum > 0, wsum, np.nan)) * sc
    return {"PAI": pai, "S": S, "avail": avail, "score": score, "contrib": contrib, "completeness": completeness,
            "used_vars": sorted(used_vars)}


def classify(cfg_f1: dict, pai: np.ndarray, mode: str) -> dict:
    """Class 0 = lower, 1 = good, 2 = high. Experimental mode ranks within today's EEZ."""
    ok = np.isfinite(pai)
    cls = np.zeros(pai.shape, dtype=np.int8)
    if mode == "frozen":
        p60, p80 = cfg_f1["classes"]["frozen"]["p60"], cfg_f1["classes"]["frozen"]["p80"]
    else:
        pc = cfg_f1["classes"]["experimental_percentiles"]
        if ok.sum() < 20:
            return {"cls": cls, "p60": None, "p80": None}
        p60, p80 = np.nanpercentile(pai[ok], [pc["good"], pc["high"]])
    cls[ok & (pai >= p60)] = 1
    cls[ok & (pai >= p80)] = 2
    return {"cls": cls, "p60": float(p60), "p80": float(p80)}


def drivers(cfg_f1: dict, contrib: Dict[str, np.ndarray], wet: np.ndarray, top_pos: int = 3, top_neg: int = 2):
    """Top positive / negative component deviations from the EEZ mean (indices into component list)."""
    ids = [c["id"] for c in cfg_f1["components"] if c["id"] in contrib]
    M = np.stack([contrib[i] for i in ids], axis=1)  # (n, nc)
    MW = M[wet]
    if len(MW):
        ct = np.isfinite(MW).sum(axis=0)
        base = np.divide(np.nansum(MW, axis=0), ct, out=np.zeros(MW.shape[1]), where=ct > 0)
    else:
        base = np.zeros(M.shape[1])
    D = np.nan_to_num(M - base[None, :], nan=0.0)
    order = np.argsort(-D, axis=1)
    pos = order[:, :top_pos].astype(np.int8)
    neg = order[:, ::-1][:, :top_neg].astype(np.int8)
    # drop non-informative entries
    posd = np.take_along_axis(D, pos.astype(int), axis=1)
    negd = np.take_along_axis(D, neg.astype(int), axis=1)
    pos = np.where(posd > 1e-4, pos, -1)
    neg = np.where(negd < -1e-4, neg, -1)
    return ids, pos, neg


def spearman(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return None
    ra = np.argsort(np.argsort(a[m])).astype(float)
    rb = np.argsort(np.argsort(b[m])).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])
