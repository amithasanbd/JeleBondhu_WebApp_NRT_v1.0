"""Configuration loading. Every threshold, weight and rule lives in versioned JSON."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(os.environ.get("JB_REPO_ROOT", Path(__file__).resolve().parents[2]))

CONFIG_FILES = [
    "config/pipeline.json",
    "config/vessels.json",
    "config/ports.json",
    "config/filter1_environment.json",
    "config/filter2_safety.json",
    "config/filter3_sustainability.json",
    "config/reasons.json",
    "data/regulatory/ban_rules_bd.json",
]


def load_json(path: Path | str) -> Any:
    with open(path, "r", encoding="utf8") as fh:
        return json.load(fh)


@dataclass
class Config:
    root: Path
    pipeline: Dict[str, Any]
    vessels: Dict[str, Any]
    ports: Dict[str, Any]
    filter1: Dict[str, Any]
    filter2: Dict[str, Any]
    filter3: Dict[str, Any]
    reasons: Dict[str, Any]
    rules: Dict[str, Any]
    config_hash: str = ""
    reason_bit: Dict[str, int] = field(default_factory=dict)

    @property
    def tz(self) -> str:
        return self.pipeline.get("timezone", "Asia/Dhaka")


def load_config(root: Path | str | None = None) -> Config:
    root = Path(root) if root else REPO_ROOT
    h = hashlib.sha256()
    raw = {}
    for rel in CONFIG_FILES:
        p = root / rel
        b = p.read_bytes()
        h.update(rel.encode())
        h.update(b)
        raw[rel] = json.loads(b.decode("utf8"))
    cfg = Config(
        root=root,
        pipeline=raw["config/pipeline.json"],
        vessels=raw["config/vessels.json"],
        ports=raw["config/ports.json"],
        filter1=raw["config/filter1_environment.json"],
        filter2=raw["config/filter2_safety.json"],
        filter3=raw["config/filter3_sustainability.json"],
        reasons=raw["config/reasons.json"],
        rules=raw["data/regulatory/ban_rules_bd.json"],
        config_hash=h.hexdigest()[:16],
    )
    cfg.reason_bit = {r["code"]: r["bit"] for r in cfg.reasons["codes"]}
    return cfg


def mask_of(cfg: Config, *codes: str) -> int:
    m = 0
    for c in codes:
        m |= 1 << cfg.reason_bit[c]
    return m
