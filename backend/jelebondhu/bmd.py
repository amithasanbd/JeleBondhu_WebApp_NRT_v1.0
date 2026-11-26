"""Bangladesh Meteorological Department (BMD) - official warning gate.

BMD has no stable, documented machine-readable API. Therefore:
  * the decision gate reads ONLY the human-verified record data/manual/bmd_bulletin.json;
  * the automatic probe merely records whether the official pages are reachable and whether
    their content changed since the last human verification (a reviewer hint, never a clearance).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

CLASSES = ("none", "cautionary", "warning", "great_danger")


@dataclass
class BmdState:
    verified: bool
    reason: str                      # why not verified (or "ok")
    record: Dict[str, Any]
    default_class: str = "none"
    areas: List[Dict[str, Any]] = field(default_factory=list)

    def class_at(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Per-point warning class index (0 none, 1 cautionary, 2 warning, 3 great_danger)."""
        lat = np.asarray(lat, float)
        lon = np.asarray(lon, float)
        out = np.full(lat.shape, CLASSES.index(self.default_class), dtype=int)
        for a in self.areas:
            x0, y0, x1, y1 = a["bbox"]
            m = (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
            out[m] = np.maximum(out[m], CLASSES.index(a["classification"]))
        return out


def _parse(ts) -> Optional[dt.datetime]:
    if not ts:
        return None
    d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=6)))  # Asia/Dhaka
    return d.astimezone(dt.timezone.utc)


def _official_bmd_url(raw: str) -> bool:
    try:
        parsed = urlparse(str(raw))
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == "bmd.gov.bd" or host.endswith(".bmd.gov.bd"))
    except (ValueError, TypeError):
        return False


def load_state(record_path: Path | str, now: dt.datetime, max_age_h: float = 24.0, demo: bool = False) -> BmdState:
    try:
        rec = json.load(open(record_path, encoding="utf8"))
    except Exception as e:
        return BmdState(False, f"record unreadable: {e}", {})
    reason = "ok"
    verified = True
    if rec.get("record_status") != "VERIFIED":
        verified, reason = False, "record_status is not VERIFIED"
    elif not rec.get("verified_by"):
        verified, reason = False, "verified_by is empty"
    else:
        try:
            va, vf, vt = _parse(rec.get("verified_at")), _parse(rec.get("valid_from")), _parse(rec.get("valid_to"))
            issued = _parse(rec.get("issued_at"))
        except Exception as e:
            return BmdState(False, f"bad timestamp: {e}", rec)
        if va is None or vf is None or vt is None or issued is None:
            verified, reason = False, "verified_at / issued_at / valid_from / valid_to missing"
        elif not _official_bmd_url(rec.get("source_url", "")):
            verified, reason = False, "a source_url on an official BMD domain is required"
        elif issued > now + dt.timedelta(minutes=15) or va > now + dt.timedelta(minutes=15):
            verified, reason = False, "bulletin or verification timestamp lies in the future"
        elif issued > va + dt.timedelta(minutes=15):
            verified, reason = False, "cannot verify a bulletin before it was issued"
        elif vt <= vf:
            verified, reason = False, "invalid bulletin validity interval"
        elif (now - issued).total_seconds() / 3600.0 > max_age_h:
            verified, reason = False, "BMD bulletin issue time too old"
        elif now < vf:
            verified, reason = False, "record not yet valid"
        elif now > vt:
            verified, reason = False, "record expired (past valid_to)"
        elif (now - va).total_seconds() / 3600.0 > max_age_h:
            verified, reason = False, f"verification older than {max_age_h:g} h"
    dc = rec.get("default_classification", "none")
    if dc not in CLASSES:
        verified, reason, dc = False, f"unknown classification '{dc}'", "none"
    areas = []
    for a in rec.get("areas", []):
        if a.get("classification") in CLASSES and a.get("bbox") and len(a["bbox"]) == 4:
            areas.append({"bbox": [float(v) for v in a["bbox"]], "classification": a["classification"], "label": a.get("label", "")})
        else:
            verified, reason = False, "malformed area entry"
    return BmdState(verified, reason, rec, dc, areas)


def probe(urls: Dict[str, str], prev_hashes: Optional[Dict[str, str]] = None, session=None, timeout: int = 25) -> Dict[str, Any]:
    """Fetch the official pages and fingerprint their visible text. Informational only."""
    out: Dict[str, Any] = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "pages": {}}
    if session is None:
        try:
            import requests
            session = requests.Session()
        except Exception as e:  # pragma: no cover
            out["error"] = str(e)
            return out
    for name, url in urls.items():
        entry: Dict[str, Any] = {"url": url, "ok": False}
        try:
            r = session.get(url, timeout=timeout, headers={"User-Agent": "JeleBondhu-NRT/1.0 (research prototype)"})
            entry["http_status"] = r.status_code
            if r.status_code == 200:
                text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S | re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                h = hashlib.sha256(text.encode("utf8")).hexdigest()[:16]
                entry.update(ok=True, content_hash=h, chars=len(text))
                if prev_hashes and prev_hashes.get(name):
                    entry["changed_since_last_probe"] = prev_hashes[name] != h
        except Exception as e:
            entry["error"] = str(e)[:160]
        out["pages"][name] = entry
    return out
