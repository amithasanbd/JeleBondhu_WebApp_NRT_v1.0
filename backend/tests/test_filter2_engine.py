import datetime as dt

import numpy as np
import pytest

from jelebondhu import bmd as bmdmod, filter2
from jelebondhu.config import mask_of
from jelebondhu.engine import C_, L_, N_, R_, S_, U_, combine_confidence, decide
from jelebondhu.ingest_openmeteo import idw_weights, parse_responses

VESSEL = {"hazards": {"wave_height_m": {"safe": 1.2, "stop": 2.0}, "wind_speed_ms": {"safe": 10, "stop": 15},
                      "wind_gust_ms": {"safe": 14, "stop": 20}, "visibility_km": {"safe": 5, "stop": 1}}}


def test_hazard_score_orientation_and_clip():
    h = {"wave_height_m": np.array([0.5, 1.2, 1.6, 2.0, 3.0]), "wind_speed_ms": np.full(5, 5.0), "wind_gust_ms": np.full(5, 8.0),
         "visibility_km": np.array([10, 5, 3, 1, 0.2]), "thunderstorm": np.zeros(5)}
    sc = filter2.hazard_scores(VESSEL, h, ("visibility_km",))
    assert np.allclose(sc["wave_height_m"], [1, 1, 0.5, 0, 0])
    assert np.allclose(sc["visibility_km"], [1, 1, 0.5, 0, 0])          # lower visibility is worse


def test_weakest_link_and_thunderstorm():
    h = {"wave_height_m": np.array([0.5, 0.5]), "wind_speed_ms": np.array([5.0, 5.0]), "wind_gust_ms": np.array([8.0, 8.0]),
         "visibility_km": np.array([10.0, 10.0]), "thunderstorm": np.array([0.0, 1.0])}
    sc = filter2.hazard_scores(VESSEL, h, ("visibility_km",))
    sp = filter2.s_phys({k: v.reshape(2, 1, 1) for k, v in sc.items()})
    assert sp.ravel()[0] == 1.0 and sp.ravel()[1] == 0.0                 # thunderstorm = hard stop


def test_nan_hazard_is_not_zero_or_safe():
    h = {"wave_height_m": np.array([np.nan]), "wind_speed_ms": np.array([5.0]), "wind_gust_ms": np.array([8.0]),
         "visibility_km": np.array([10.0]), "thunderstorm": np.array([0.0])}
    sc = filter2.hazard_scores(VESSEL, h, ("visibility_km",))
    assert np.isnan(sc["wave_height_m"][0])
    assert np.isnan(filter2.s_phys({k: a.reshape(1, 1) for k, a in sc.items()})[0, 0])


def test_missing_hazard_not_favourable_but_observed_stop_overrides():
    base = {k: np.ones((2, 3), dtype=np.float32) for k in filter2.HAZ}
    base["visibility_km"][:, 1] = np.nan
    base["wave_height_m"][1, 1] = 0.0
    out = filter2.s_phys(base)
    assert np.isnan(out[0, 1])  # one unobserved variable = no clearance
    assert out[1, 1] == 0.0      # observed critical wave remains a No-Go
    assert out[0, 0] == 1.0


def _decide(cfg, **kw):
    n = 1
    d = dict(wet=np.ones(n, bool), in_range=np.ones(n, bool), state2=np.zeros(n, np.int8), state3=np.zeros(n, np.int8),
             pai=np.full(n, 0.7), pai_cls=np.full(n, 2), conf=np.full(n, 0.9), bmd_verified=True, mask=np.zeros(n, np.int64))
    d.update(kw)
    return decide(cfg, d["wet"], d["in_range"], d["state2"], d["state3"], d["pai"], d["pai_cls"], d["conf"], d["bmd_verified"], d["mask"])


@pytest.mark.parametrize("kw,expect", [
    ({}, S_),
    ({"state2": np.array([3], np.int8)}, N_),
    ({"state3": np.array([3], np.int8)}, N_),
    ({"state3": np.array([2], np.int8)}, U_),
    ({"state2": np.array([1], np.int8)}, C_),
    ({"pai_cls": np.array([0])}, C_),
    ({"conf": np.array([0.4])}, C_),            # 0.3 <= C < 0.5 capped at caution
    ({"conf": np.array([0.2])}, U_),            # C < 0.3 withdrawn
    ({"pai": np.array([np.nan])}, U_),
    ({"in_range": np.array([False])}, R_),
    ({"wet": np.array([False])}, L_),
])
def test_decision_priority(cfg, kw, expect):
    cls, pre, mask = _decide(cfg, **kw)
    assert cls[0] == expect


def test_nogo_beats_low_confidence_and_unverified_bmd(cfg):
    cls, _, _ = _decide(cfg, state2=np.array([3], np.int8), conf=np.array([0.1]), bmd_verified=False)
    assert cls[0] == N_


def test_unverified_bmd_blocks_safe_and_caution_only(cfg):
    cls, pre, mask = _decide(cfg, bmd_verified=False)
    assert cls[0] == U_ and pre[0] == S_
    cls, pre, _ = _decide(cfg, bmd_verified=False, state2=np.array([1], np.int8))
    assert cls[0] == U_ and pre[0] == C_
    cls, _, _ = _decide(cfg, bmd_verified=False, state3=np.array([3], np.int8))
    assert cls[0] == N_


def test_confidence_is_min_of_components():
    c = combine_confidence({"a": np.array([0.9, 0.2]), "b": np.array([0.5, 0.8])})
    assert np.allclose(c, [0.5, 0.2])


# ---- BMD human gate ---------------------------------------------------------------------
def _rec(tmp_path, **kw):
    import json
    now = dt.datetime(2026, 11, 26, 6, tzinfo=dt.timezone.utc)
    rec = {"record_status": "VERIFIED", "verified_by": "A. Officer", "verified_at": now.isoformat(),
           "issued_at": (now - dt.timedelta(hours=2)).isoformat(),
           "source_url": "https://www.bmd.gov.bd/web/en/p/Marine-Warning",
           "valid_from": (now - dt.timedelta(hours=1)).isoformat(), "valid_to": (now + dt.timedelta(hours=11)).isoformat(),
           "default_classification": "none", "areas": []}
    rec.update(kw)
    p = tmp_path / "b.json"
    json.dump(rec, open(p, "w"))
    return p, now


def test_bmd_verified_ok(tmp_path):
    p, now = _rec(tmp_path)
    assert bmdmod.load_state(p, now).verified


@pytest.mark.parametrize("kw", [{"record_status": "UNVERIFIED"}, {"verified_by": ""}, {"default_classification": "bogus"},
                                {"areas": [{"classification": "warning"}]},
                                {"source_url": "https://untrusted.example/bmd"},
                                {"issued_at": None}])
def test_bmd_rejected(tmp_path, kw):
    p, now = _rec(tmp_path, **kw)
    assert not bmdmod.load_state(p, now).verified


def test_bmd_future_issue_or_verification_rejected(tmp_path):
    p, now = _rec(tmp_path, issued_at=(dt.datetime(2026, 11, 27, tzinfo=dt.timezone.utc)).isoformat())
    assert not bmdmod.load_state(p, now).verified


def test_bmd_expired_and_old_verification(tmp_path):
    p, now = _rec(tmp_path)
    assert not bmdmod.load_state(p, now + dt.timedelta(hours=12)).verified
    assert not bmdmod.load_state(p, now + dt.timedelta(hours=25), max_age_h=24).verified


def test_bmd_area_classes(tmp_path):
    p, now = _rec(tmp_path, areas=[{"bbox": [90, 20, 92, 21], "classification": "great_danger", "label": "x"}])
    s = bmdmod.load_state(p, now)
    assert s.verified and list(s.class_at(np.array([20.5, 22.5]), np.array([91.0, 91.0]))) == [3, 0]


def test_template_record_is_unverified(cfg):
    s = bmdmod.load_state(cfg.root / "data/manual/bmd_bulletin.json", dt.datetime.now(dt.timezone.utc))
    assert not s.verified


# ---- Open-Meteo parser fixture -------------------------------------------------------------
def _om(vals_wave, vals_vis):
    t = ["2026-11-26T00:00", "2026-11-26T01:00", "2026-11-26T02:00"]
    marine = {"hourly": {"time": t, "wave_height": vals_wave, "wave_period": [5, 5, 5], "wave_direction": [200, 200, 200]}}
    weather = {"hourly": {"time": t, "wind_speed_10m": [4.0, 5.0, 6.0], "wind_gusts_10m": [8.0, 9.0, 10.0],
                          "visibility": vals_vis, "weather_code": [1, 95, 3]}}
    return marine, weather


def test_openmeteo_parser_units_and_nulls():
    m, w = _om([0.5, None, 0.7], [20000, 10000, None])
    hs = parse_responses([20.0], [90.0], [m], [w])
    assert hs.data["visibility"][0, 0] == 20.0                     # m -> km
    assert np.isnan(hs.data["wave_height"][0, 1]) and np.isnan(hs.data["visibility"][0, 2])
    assert hs.data["weather_code"][0, 1] == 95
    with pytest.raises(ValueError):
        parse_responses([20.0, 21.0], [90.0, 90.0], [m], [w])


def test_idw_weights_support_and_exact_hit():
    W, support = idw_weights(np.array([20.0, 21.0]), np.array([90.0, 91.0]), np.array([20.0, 25.0]), np.array([90.0, 80.0]))
    assert np.isclose(W[0].sum(), 1.0, atol=1e-6) and W[0].max() > 0.99
    assert support[1] == 0 or np.all(W[1] == 0) or support[1] < support[0]    # far point has no support


def test_thunder_missing_at_neighbour_stays_unknown():
    W = np.array([[0.75, 0.25], [0.5, 0.5]], dtype=np.float32)
    thunder = np.array([[0., 1.], [np.nan, np.nan]], dtype=np.float32)
    out = filter2._max_nearest(W, thunder)
    assert np.isnan(out[0, 0]) and out[0, 1] == 1.0
    assert np.isnan(out[1, 0]) and out[1, 1] == 1.0
