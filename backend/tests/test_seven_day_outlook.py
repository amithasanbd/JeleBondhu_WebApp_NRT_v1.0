import json
import datetime as dt
import numpy as np
from jelebondhu.config import load_config
from jelebondhu.fields import Bathymetry
from jelebondhu.engine import load_stations, choose_rep_points
from jelebondhu.synthetic import synthetic_cmems, synthetic_hazards, demo_bmd
from jelebondhu.pipeline import run_pipeline

NOW = dt.datetime(2026,11,26,6,tzinfo=dt.timezone.utc)

def _bundle(cfg,bmd):
    bathy=Bathymetry(cfg.root/'data/spatial/bathy_grid.npz')
    st=load_stations(cfg)
    rep=choose_rep_points(cfg,st,bathy)
    return run_pipeline(cfg,NOW,synthetic_cmems(cfg,NOW,bathy),synthetic_hazards(cfg,NOW,rep),bmd,mode='demo',log=lambda *args:None)

def test_full_168h_weather_outlook_with_no_fake_catch_claims():
    cfg=load_config()
    assert cfg.pipeline['openmeteo']['forecast_hours']==168
    bundle=_bundle(cfg,demo_bmd(NOW))
    lite=json.loads(bundle.files['lite/mechanized__cox_bazar.json'])
    assert len(lite['outlook7'])==7
    assert [d['day'] for d in lite['outlook7']]==[1,2,3,4,5,6,7]
    assert all(d['type']=='weather_outlook_only' and d['official_clearance'] is False for d in lite['outlook7'])
    assert all(d['hours_covered']==24 for d in lite['outlook7'])
    assert len(lite['departs'])==3  # existing short-range trip advice retained


def test_expired_bmd_must_not_clear_trips():
    cfg=load_config()
    bmd=demo_bmd(NOW)
    bmd.record['valid_to']=(NOW+dt.timedelta(hours=1)).isoformat()
    bundle=_bundle(cfg,bmd)
    for rel,raw in bundle.files.items():
        if rel.startswith('advisory/'):
            for dep in json.loads(raw)['departs']:
                assert 'S' not in dep['c'] and 'C' not in dep['c'], (rel,dep['offset_h'])
