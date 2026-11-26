import datetime as dt
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from jelebondhu.api import create_app


def test_no_live_snapshot_fails_closed(tmp_path):
    c = TestClient(create_app(tmp_path))
    assert c.get('/api/health').status_code == 503
    assert c.get('/api/manifest').status_code == 503
    assert c.get('/api/advisory/mechanized/kuakata').status_code == 503


def test_read_only_api_integrity_and_stale_gate(tmp_path):
    d = tmp_path / 'live'
    (d / 'advisory').mkdir(parents=True)
    obj = {'departs': [{'c': 'SCNURL', 'zones': [{'id': 123}], 'overall': 'S'}]}
    raw = json.dumps(obj).encode()
    (d / 'advisory/mechanized__kuakata.json').write_bytes(raw)
    now = dt.datetime.now(dt.timezone.utc)
    m = dict(mode='live', qc_passed=True, bundle_id='unit-test', bmd_verified=True,
             vessels={'mechanized': {}}, ports={'kuakata': {}},
             valid_until=(now-dt.timedelta(hours=15)).isoformat(),
             stale_after=(now-dt.timedelta(hours=12)).isoformat(),
             expire_after=(now+dt.timedelta(hours=15)).isoformat(),
             files={'advisory/mechanized__kuakata.json': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}})
    (d / 'manifest.json').write_text(json.dumps(m))
    c = TestClient(create_app(tmp_path))
    assert c.get('/api/health').status_code == 503
    r = c.get('/api/advisory/mechanized/kuakata?departure=0')
    assert r.status_code == 200 and r.json()['advisory']['c'] == 'UUNURL'
    assert r.json()['advisory']['zones'] == []
    assert r.json()['advisory']['overall'] == 'U' 
    assert c.get('/api/advisory/../kuakata').status_code in (404, 422)
    (d / 'advisory/mechanized__kuakata.json').write_text('{}')
    assert c.get('/api/advisory/mechanized/kuakata').status_code == 503
