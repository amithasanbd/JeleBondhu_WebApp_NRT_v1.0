"""Acceptance checks taken from the Sustainability Filter Manual (v4.1)."""
import copy
import datetime as dt

import numpy as np

from jelebondhu import filter3
from jelebondhu.filter3 import CAUTION, NOGO, UNKNOWN

from conftest import f3, has, hours, plain_sp


def test_bob_ban_boundaries(cfg):
    # 2026-04-15 .. 2026-06-11 inclusive
    r = f3(cfg, hours(2026, 4, 14, 8), hours(2026, 4, 14, 20))
    assert r["state"][0] == 0                                   # day before: pass
    r = f3(cfg, hours(2026, 4, 15, 0), hours(2026, 4, 15, 10))
    assert r["state"][0] == NOGO and has(cfg, r["mask"][0], "BAN_BOB_58D")
    r = f3(cfg, hours(2026, 6, 11, 12), hours(2026, 6, 11, 20))
    assert r["state"][0] == NOGO                                # last day inclusive
    r = f3(cfg, hours(2026, 6, 12, 0), hours(2026, 6, 12, 8))
    assert r["state"][0] == 0                                   # day after


def test_trip_crossing_midnight_into_ban(cfg):
    r = f3(cfg, hours(2026, 4, 14, 20), hours(2026, 4, 15, 6))
    assert r["state"][0] == NOGO                                # ends inside the ban -> blocked
    r = f3(cfg, hours(2026, 6, 11, 20), hours(2026, 6, 12, 6))
    assert r["state"][0] == NOGO                                # starts inside the ban -> blocked


def test_hilsa_ban_boundaries(cfg):
    assert f3(cfg, hours(2026, 10, 7, 6), hours(2026, 10, 7, 18))["state"][0] == 0
    assert f3(cfg, hours(2026, 10, 8, 6), hours(2026, 10, 8, 18))["state"][0] == UNKNOWN
    assert f3(cfg, hours(2026, 10, 29, 6), hours(2026, 10, 29, 18))["state"][0] == UNKNOWN
    assert f3(cfg, hours(2026, 10, 8, 6), hours(2026, 10, 8, 18), target_species="hilsa")["state"][0] == NOGO
    assert f3(cfg, hours(2026, 10, 30, 6), hours(2026, 10, 30, 18))["state"][0] == 0


def test_missing_year_approval_is_unknown_not_pass(cfg):
    # 2027: no approved rule for BAN_BOB_58D; the trip touches the indicative window -> UNKNOWN
    r = f3(cfg, hours(2027, 4, 20, 6), hours(2027, 4, 20, 18))
    assert r["state"][0] == UNKNOWN and has(cfg, r["mask"][0], "RULES_YEAR_UNAPPROVED")
    # same season, outside the window -> pass
    r = f3(cfg, hours(2027, 8, 1, 6), hours(2027, 8, 1, 18))
    assert r["state"][0] == 0


def test_last_year_dates_are_never_reused(cfg):
    # 2025 window dates must not block 2026 and 2026 dates must not block 2027
    r = f3(cfg, hours(2027, 5, 10, 6), hours(2027, 5, 10, 18))
    assert not has(cfg, r["mask"][0], "BAN_BOB_58D")


def test_stale_ruleset_blocks_advice(cfg):
    status, problems = filter3.validate_ruleset(cfg.rules, dt.date(2028, 1, 1))
    assert status == "stale"
    r = f3(cfg, hours(2026, 11, 26, 6), hours(2026, 11, 26, 18), status=status)
    assert r["state"][0] == UNKNOWN and has(cfg, r["mask"][0], "RULES_STALE")


def test_invalid_ruleset_does_not_crash(cfg):
    bad = copy.deepcopy(cfg.rules)
    bad["rules"][0]["start_date"], bad["rules"][0]["end_date"] = "2026-06-11", "2026-04-15"   # reversed
    status, problems = filter3.validate_ruleset(bad, dt.date(2026, 11, 26))
    assert status == "invalid" and problems
    r = f3(cfg, hours(2026, 11, 26, 6), hours(2026, 11, 26, 18), rules=bad, status=status)
    assert r["state"][0] == UNKNOWN


def test_overlapping_closures_nogo_wins(cfg):
    sp = plain_sp(1, mpa_state=np.array([CAUTION]))
    r = f3(cfg, hours(2026, 4, 20, 6), hours(2026, 4, 20, 18), sp=sp)
    assert r["state"][0] == NOGO


def test_jatka_is_flag_only(cfg):
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18))
    assert r["state"][0] == 0 and r["jatka_active"][0] and has(cfg, r["mask"][0], "JATKA_RISK")
    r = f3(cfg, hours(2026, 7, 10, 6), hours(2026, 7, 10, 18))
    assert not r["jatka_active"][0]


def test_trawler_in_ifa_is_unknown_until_verified(cfg):
    sp = plain_sp(1, in_ifa=np.array([True]))
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18), vessel="trawler", sp=sp)
    assert r["state"][0] == UNKNOWN and has(cfg, r["mask"][0], "VZ_UNRESOLVED")
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18), vessel="small", sp=sp)
    assert r["state"][0] == 0                                   # rule applies only to trawlers
    assert has(cfg, r["mask"][0], "IFA_TAG")


def test_ifa_outside_closure_is_not_a_closure(cfg):
    sp = plain_sp(1, in_ifa=np.array([True]))
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18), vessel="mechanized", sp=sp)
    assert r["state"][0] == 0


def test_mpa_gates_and_buffer(cfg):
    sp = plain_sp(3, mpa_state=np.array([NOGO, UNKNOWN, 0]), dist_mpa_km=np.array([0.0, 0.0, 3.0]))
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18), sp=sp)
    assert list(r["state"]) == [NOGO, UNKNOWN, CAUTION]
    assert has(cfg, r["mask"][0], "MPA_VERIFIED") and has(cfg, r["mask"][1], "MPA_UNVERIFIED") and has(cfg, r["mask"][2], "MPA_BUFFER")
    assert r["U"][0] == 0 and r["U"][1] == 0 and 0 < r["U"][2] < 1


def test_absent_depth_is_unknown(cfg):
    r = f3(cfg, hours(2026, 12, 10, 6), hours(2026, 12, 10, 18), depth_ok=np.array([False]))
    assert r["state"][0] == UNKNOWN


def test_season_check_uses_dhaka_calendar_day(cfg):
    # 2026-10-07 20:00 UTC = 2026-10-08 02:00 Dhaka -> inside the hilsa ban
    t = dt.datetime(2026, 10, 7, 20, tzinfo=dt.timezone.utc).timestamp() / 3600
    r = f3(cfg, t, t + 6)
    assert r["state"][0] == UNKNOWN
    assert f3(cfg, t, t + 6, target_species="hilsa")["state"][0] == NOGO
