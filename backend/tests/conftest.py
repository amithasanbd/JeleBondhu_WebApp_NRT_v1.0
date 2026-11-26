import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jelebondhu import filter3  # noqa: E402
from jelebondhu.config import load_config  # noqa: E402

DHAKA = dt.timezone(dt.timedelta(hours=6))


@pytest.fixture(scope="session")
def cfg():
    return load_config()


def hours(y, m, d, hh=0, mm=0):
    """Asia/Dhaka wall-clock -> UTC hours since epoch."""
    return dt.datetime(y, m, d, hh, mm, tzinfo=DHAKA).timestamp() / 3600.0


def plain_sp(n=1, **kw):
    sp = {"in_ifa": np.zeros(n, bool), "mpa_state": np.zeros(n, int), "mpa_idx": -np.ones(n, int),
          "dist_mpa_km": np.full(n, np.inf), "ground_mask": np.zeros(n, int)}
    sp.update(kw)
    return sp


def f3(cfg, t0, t1, vessel="mechanized", sp=None, rules=None, status="ok", depth_ok=None,
       target_species="unspecified"):
    n = 1 if sp is None else len(next(iter(sp.values())))
    sp = sp or plain_sp(1)
    return filter3.evaluate(cfg, rules or cfg.rules, status, sp, vessel, np.full(n, t0), np.full(n, t1),
                            np.ones(n, bool) if depth_ok is None else depth_ok, target_species=target_species)


def has(cfg, mask, code):
    from jelebondhu.config import mask_of
    return bool(int(mask) & mask_of(cfg, code))
