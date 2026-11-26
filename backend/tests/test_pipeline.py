import datetime as dt
import json

import numpy as np
import pytest

from jelebondhu import cli, geo
from jelebondhu.engine import choose_rep_points, load_stations
from jelebondhu.fields import Bathymetry
from jelebondhu import filter2
from jelebondhu.pipeline import run_pipeline
from jelebondhu.synthetic import demo_bmd, synthetic_cmems, synthetic_hazards
from jelebondhu.bmd import BmdState

NOW = dt.datetime(2026, 11, 26, 6, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def built(cfg, tmp_path_factory):
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    st = load_stations(cfg)
    rep = choose_rep_points(cfg, st, bathy)
    bundle = run_pipeline(cfg, NOW, synthetic_cmems(cfg, NOW, bathy), synthetic_hazards(cfg, NOW, rep), demo_bmd(NOW), mode="demo")
    d = tmp_path_factory.mktemp("bundle")
    for rel, b in bundle.files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(b)
    return bundle, d


def test_bundle_validates_and_is_deterministic(cfg, built):
    bundle, d = built
    assert cli.validate_dir(d) == []
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    st = load_stations(cfg)
    rep = choose_rep_points(cfg, st, bathy)
    b2 = run_pipeline(cfg, NOW, synthetic_cmems(cfg, NOW, bathy), synthetic_hazards(cfg, NOW, rep), demo_bmd(NOW), mode="demo")
    for rel in ("cells.json", "advisory/small__cox_bazar.json", "advisory/trawler__kuakata.json"):
        assert b2.files[rel] == bundle.files[rel]


def test_demo_bundle_is_labelled_demo(built):
    bundle, d = built
    assert bundle.meta["manifest"]["mode"] == "demo"
    assert json.load(open(d / "provenance.json"))["mode"] == "demo"


def test_tampering_is_detected(built):
    bundle, d = built
    p = d / "cells.json"
    orig = p.read_bytes()
    try:
        p.write_bytes(orig.replace(b"0", b"1", 1))
        assert any("hash mismatch" in x for x in cli.validate_dir(d))
    finally:
        p.write_bytes(orig)


def test_unverified_bmd_never_yields_safe_or_caution(cfg, tmp_path):
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    st = load_stations(cfg)
    rep = choose_rep_points(cfg, st, bathy)
    unv = BmdState(False, "record_status is not VERIFIED", {})
    b = run_pipeline(cfg, NOW, synthetic_cmems(cfg, NOW, bathy), synthetic_hazards(cfg, NOW, rep), unv, mode="demo")
    letters = set()
    for rel, raw in b.files.items():
        if rel.startswith("advisory/"):
            for dep in json.loads(raw)["departs"]:
                letters |= set(dep["c"])
                assert dep["overall"] != "S" and dep["overall"] != "C"
    assert "S" not in letters and "C" not in letters
    assert "N" in letters or "U" in letters            # hazards / unknown states still surface


def test_missing_hazards_never_yield_safe(cfg):
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    b = run_pipeline(cfg, NOW, synthetic_cmems(cfg, NOW, bathy), None, demo_bmd(NOW), mode="demo")
    for rel, raw in b.files.items():
        if rel.startswith("advisory/"):
            for dep in json.loads(raw)["departs"]:
                assert "S" not in dep["c"] and "C" not in dep["c"]


def test_lite_excludes_pending_zones_and_has_bilingual_text(built):
    bundle, d = built
    for p in (d / "lite").glob("*.json"):
        j = json.load(open(p))
        for dep in j["departs"]:
            assert all(z["kind"] in ("safe", "caution") for z in dep["zones"])
            assert dep["headline_bn"] and dep["headline_en"]


def test_port_entry_points_are_wet(cfg):
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    for pid, p in cfg.ports["ports"].items():
        e = p["entry"]
        assert bool(bathy.is_wet(np.array([e["lat"]]), np.array([e["lon"]]), 3)[0]), pid


def test_failed_route_is_never_certified(cfg):
    bathy = Bathymetry(cfg.root / "data/spatial/bathy_grid.npz")
    st = load_stations(cfg)
    r = filter2.build_routes(cfg, bathy, "patharghata", st.lat, st.lon)
    assert (~r.route_ok & r.station_wet).any()          # shoals/islands really block some straight routes


def test_geo_helpers():
    assert abs(geo.haversine_km(20, 90, 21, 90) - 111.19) < 0.5
    ring = [(0, 0), (0, 10), (10, 10), (10, 0)]
    assert geo.points_in_rings(np.array([5.0]), np.array([5.0]), [ring])[0]
    assert not geo.points_in_rings(np.array([15.0]), np.array([5.0]), [ring])[0]
    assert geo.ring_self_intersects([(0, 0), (10, 10), (0, 10), (10, 0)])


def test_no_hardcoded_credentials_in_repo(cfg):
    """Credentials must only come from environment / GitHub secrets, never literals."""
    import re
    pats = [re.compile(rb"(?i)(password|passwd|pwd|secret|token)\s*[:=]\s*[\"'][^\"'\s$]{4,}[\"']"),
            re.compile(rb"(?i)cmems[_ ]?(user(name)?)\s*[:=]\s*[\"'][A-Za-z0-9_.-]{3,}[\"']")]
    allowed = (b"os.environ", b"secrets.", b"getpass", b"${{")
    for p in cfg.root.rglob("*"):
        if p.is_file() and ".git/" not in str(p) and "data/raw" not in str(p) and "tests/" not in str(p) \
                and p.suffix in (".py", ".json", ".md", ".yml", ".yaml", ".html", ".js", ".txt", ".ipynb"):
            for line in p.read_bytes().splitlines():
                if any(r.search(line) for r in pats) and not any(a in line for a in allowed):
                    raise AssertionError(f"possible hard-coded credential in {p}: {line[:80]!r}")


def test_bmd_record_cli_roundtrip(tmp_path):
    (tmp_path / "data/manual").mkdir(parents=True)
    rc = cli.main(["bmd-record", "--root", str(tmp_path), "--classification", "cautionary", "--verified-by", "T. Officer",
                   "--issued-at", dt.datetime.now(dt.timezone.utc).isoformat(),
                   "--source-url", "https://www.bmd.gov.bd/web/en/p/Marine-Warning", "--valid-hours", "6"])
    assert rc == 0
    from jelebondhu import bmd as bm
    s = bm.load_state(tmp_path / "data/manual/bmd_bulletin.json", dt.datetime.now(dt.timezone.utc))
    assert s.verified and s.default_class == "cautionary"


def test_official_warning_expiry_caps_publication_window(cfg):
    from jelebondhu.pipeline import publication_times
    bmd = demo_bmd(NOW)
    bmd.record['valid_to'] = (NOW + dt.timedelta(hours=2)).isoformat()
    valid, stale, expired = publication_times(NOW, bmd, cfg.pipeline)
    assert valid <= NOW + dt.timedelta(hours=2)
    assert stale <= NOW + dt.timedelta(hours=2)  # positive classes withdrawn by browser
    assert expired > stale
