import copy,json
from pathlib import Path
import numpy as np
import pytest
from rdflib import Graph,Namespace,RDF
from owlrl import DeductiveClosure,OWLRL_Semantics
from site_dss.data import load_snapshot,save_snapshot,import_demand_csv,import_sites_geojson
from site_dss.ahp import ahp,pairwise,aggregate
from site_dss.utility import utilities,compare,cost_weight_switch
from site_dss.knowledge import infer,export_ontology
from site_dss.forecast import predict,metrics,train
from site_dss.scenarios import build_scenarios
ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def snapshot():return load_snapshot(ROOT/'data/mock/snapshot.json',allow_demo=True)[0]

def test_demo_opt_in():
    with pytest.raises(ValueError,match='allow_demo'):load_snapshot(ROOT/'data/mock/snapshot.json')

@pytest.mark.parametrize('case',['unit','polygon','future','duplicate','area','matrix','demand_balance','unknown_zone','unknown_evidence','gap','nonfinite'])
def test_bad_data(tmp_path,case):
    d=json.loads((ROOT/'data/mock/snapshot.json').read_text())
    if case=='unit':d['demand'][0]['unit']='ton'
    if case=='polygon':d['sites'][0]['geometry']['coordinates']=[[[0,0],[1,1],[1,0],[0,1],[0,0]]]
    if case=='future':d['evidence'][0]['observed_at']='2027-01-01'
    if case=='duplicate':d['demand'].append(d['demand'][0])
    if case=='area':d['sites'][0]['document_area_m2']=1
    if case=='matrix':d['routes'].pop()
    if case=='demand_balance':d['demand'][0]['shipped_pallets']=0
    if case=='unknown_zone':d['demand'][0]['zone_id']='Q'
    if case=='unknown_evidence':d['routes'][0]['evidence_id']='Q'
    if case=='gap':d['demand'].pop(1)
    if case=='nonfinite':d['sites'][0]['capex_rub']=float('nan')
    p=tmp_path/'bad.json';p.write_text(json.dumps(d))
    with pytest.raises(ValueError):load_snapshot(p,allow_demo=True)

def test_import_and_idempotence(snapshot,tmp_path):
    assert len(import_demand_csv(ROOT/'data/mock/demand.csv'))==180
    assert len(import_sites_geojson(ROOT/'data/mock/sites.geojson'))==5
    assert save_snapshot(snapshot,tmp_path)==save_snapshot(snapshot,tmp_path)
    assert len(list(tmp_path.iterdir()))==1

def test_ahp():
    a=pairwise([4/3,2,4,1.5,3,2]);r=ahp(a)
    assert np.allclose(r['weights'],[.4,.3,.2,.1]);assert r['CR']<1e-10
    assert np.allclose(aggregate([a,a],[1,2]),a)
    with pytest.raises(ValueError):ahp(pairwise([9,1/9,9,9,1/9,9]))
    with pytest.raises(ValueError):ahp(np.zeros((4,4)))
    with pytest.raises(ValueError):ahp(np.ones((3,3)))

def test_utilities():
    a=utilities(1009.216875399718,.922,14,.2);b=utilities(1046.2763782901068,.961,12,.4)
    r=compare(a,b,[.4,.3,.2,.1]);assert r['score_a']==pytest.approx(.6050688389);assert r['score_b']==pytest.approx(.7315807646)
    assert sum(r['contributions'])==pytest.approx(r['delta']);assert cost_weight_switch(a,b)==pytest.approx(.7463538916)
    assert np.allclose(utilities(0,1,0,1),1)
    assert np.allclose(utilities(2000,0,30,0),0)
    # Adding any candidate does not change anchor-based utilities.
    utilities(1200,.9,18,.1);assert np.allclose(a,utilities(1009.216875399718,.922,14,.2))

def test_rules(snapshot):
    out=[infer(s,synthetic=True) for s in snapshot.sites]
    assert [r['status'] for r in out]==['eligible_for_calculation','eligible_for_calculation','excluded','needs_confirmation','eligible_for_calculation']
    assert all(r['demo_only'] for r in out)
    assert infer(snapshot.sites[0],unknown=['expired'])['status']=='needs_confirmation'
    assert infer(snapshot.sites[0],success=.9,alpha=.95)['status']=='risk_rejected'
    bad=snapshot.sites[0].model_copy(update={'power_available_kw':1})
    with pytest.raises(ValueError,match='contradictory'):infer(bad)

def test_owl(snapshot,tmp_path):
    p=tmp_path/'x.owl';export_ontology(snapshot.sites,p);g=Graph().parse(p);ns=Namespace('https://example.org/site-dss#')
    assert not list(g.subjects(RDF.type,ns.NeedsConfirmationSite))
    DeductiveClosure(OWLRL_Semantics).expand(g)
    assert set(g.subjects(RDF.type,ns.NeedsConfirmationSite))=={ns.site_D}

def test_baseline_and_zero():
    assert np.allclose(predict(np.arange(24),'seasonal_naive',25),np.tile(np.arange(12,24),3)[:25])
    assert metrics(np.zeros(12),np.zeros(12))['WAPE'] is None
    with pytest.raises(ValueError):predict(np.zeros(20),'ets')

@pytest.fixture(scope='module')
def forecast():
    s,_=load_snapshot(ROOT/'data/mock/snapshot.json',allow_demo=True);return train(s)

def test_forecast_protocol(forecast):
    r=forecast['metrics'];split=r['split']
    assert split['validation_target'][1]<split['calibration_target'][0]<split['test_target'][0]
    assert len(forecast['points'])==36
    for p in forecast['points']:
        assert p['target_month']>p['training_cutoff'];assert 0<=p['p025']<=p['p10']<=p['point']<=p['p90']<=p['p975']
    assert r['selection'] in r['validation']

def test_no_test_leakage(snapshot,forecast):
    # Perturb only held-out test: model selection and calibration must be identical.
    changed=snapshot.model_copy(deep=True)
    cutoff=forecast['metrics']['split']['test_target'][0]
    for d in changed.demand:
        if str(d.month)>=cutoff:
            d.ordered_pallets*=2;d.shipped_pallets*=2;d.unfulfilled_pallets*=2
    other=train(changed)
    assert other['metrics']['selection']==forecast['metrics']['selection']
    assert other['metrics']['validation']==forecast['metrics']['validation']
    assert other['calibration_errors']==forecast['calibration_errors']
    assert other['metrics']['test']!=forecast['metrics']['test']

def test_scenarios(forecast):
    a=build_scenarios(forecast,20);b=build_scenarios(forecast,20)
    assert a==b;assert a!=build_scenarios(forecast,20,seed=22)
    assert sum(s['probability'] for s in a['scenarios'])==pytest.approx(1)
    assert all(min(v)>=0 for s in a['scenarios'] for v in s['demand_paths'].values())
    # Identical zone errors and point values remain identical under shared block selection.
    fc=copy.deepcopy(forecast)
    for row in fc['calibration_errors']:row[1]=row[0]
    points=[p for p in fc['points'] if p['zone_id']=='Z1']
    for i,p in enumerate(p for p in fc['points'] if p['zone_id']=='Z2'):p['point']=points[i]['point']
    for s in build_scenarios(fc,5)['scenarios']:assert s['demand_paths']['Z1']==s['demand_paths']['Z2']

def test_spatial_intersection(snapshot):
    from site_dss.data.spatial import screen
    a=snapshot.sites[0]
    r=screen(a,[dict(restriction_id='test',evidence_id='site',geometry=a.geometry)])
    assert r['area_m2']>0 and r['intersections'][0]['requires_expert_review']
    assert not screen(snapshot.sites[1],[dict(restriction_id='test',evidence_id='site',geometry=a.geometry)])['intersections']

def test_stale_evidence_and_power(tmp_path):
    raw=json.loads((ROOT/'data/mock/snapshot.json').read_text());raw['evidence'][0]['valid_until']='2026-11-02'
    p=tmp_path/'s.json';p.write_text(json.dumps(raw));s,q=load_snapshot(p,allow_demo=True)
    assert infer(s.sites[0],unknown=q['missing_critical']['A'])['status']=='needs_confirmation'
    raw['sites'][0]['power_available_kw']=10;p.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='contradictory power'):load_snapshot(p,allow_demo=True)

def test_unknown_route_blocks_site(tmp_path):
    raw=json.loads((ROOT/'data/mock/snapshot.json').read_text());raw['routes'][0]['reachable']=None
    p=tmp_path/'s.json';p.write_text(json.dumps(raw));s,q=load_snapshot(p,allow_demo=True)
    assert infer(s.sites[0],unknown=q['missing_critical']['A'])['status']=='needs_confirmation'

def test_capex_mismatch(tmp_path):
    raw=json.loads((ROOT/'data/mock/snapshot.json').read_text());raw['costs'][0]['amount']=1
    p=tmp_path/'s.json';p.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='CAPEX mismatch'):load_snapshot(p,allow_demo=True)
