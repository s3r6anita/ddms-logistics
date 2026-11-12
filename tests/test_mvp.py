import copy,itertools,json
from pathlib import Path
import numpy as np
import pytest
from site_dss.optimization import solve_flows,analytical_flows,select_site
from site_dss.validation import validate_flows,evaluate
from site_dss.risk import cvar,weighted_quantile,wilson,summarize
from site_dss.domain import DecisionRequest,DecisionRun
from site_dss.recommendation import recommend
from site_dss.bi import export_bi

@pytest.mark.parametrize('seed',range(20))
def test_small_exact_transport(seed):
    rng=np.random.default_rng(seed);ds=rng.integers(1,5,size=3).tolist();cap=int(rng.integers(1,10));reach=rng.choice([True,False],3).tolist();timely=[r and bool(rng.integers(0,2)) for r in reach];cost=rng.integers(1,10,size=3).tolist()
    served=min(cap,sum(d for d,r in zip(ds,reach) if r));floor=min(.9*sum(ds),served,sum(d for d,t in zip(ds,timely) if t))
    # Integer timely floor allows independent integer enumeration of all LP vertices.
    floor=int(floor)
    b=dict(capacity=cap,rows=[dict(zone=str(j),demand=ds[j],reachable=reach[j],timely=timely[j],cost_rub=cost[j]) for j in range(3)],served_optimum=served,timely_target=floor)
    candidates=[f for f in itertools.product(*(range(d+1) for d in ds)) if sum(f)==served and all(not v or reach[j] for j,v in enumerate(f)) and sum(v for j,v in enumerate(f) if timely[j])>=floor]
    expected=min(sum(v*c for v,c in zip(f,cost)) for f in candidates)
    result=solve_flows([b]);assert result['status']=='OPTIMAL';validate_flows([b],result['flows'])
    assert sum(v*c for v,c in zip(result['flows'][0],cost))==pytest.approx(expected,abs=1e-4)
    direct=analytical_flows([b]);validate_flows([b],direct)
    assert sum(v*c for v,c in zip(direct[0],cost))==pytest.approx(expected)


def test_solver_timeout_and_validation():
    assert solve_flows([],time_limit=0)['status']=='UNKNOWN'
    b=dict(capacity=1,rows=[dict(demand=2,reachable=False,timely=False,cost_rub=1)],served_optimum=0,timely_target=0)
    with pytest.raises(ValueError,match='closed route'):validate_flows([b],[[1]])
    b['rows'][0]['reachable']=True
    with pytest.raises(ValueError,match='capacity'):validate_flows([b],[[2]])
    assert solve_flows([dict(b,served_optimum=2)])['status']=='INFEASIBLE'


def test_risk_tail_boundary():
    assert cvar([0,10,20],[.8,.15,.05])==pytest.approx(15)
    assert weighted_quantile([0,10,20],[.8,.15,.05],.9)==10
    assert wilson(1000,1000)[0]>.99
    # Joint failure uses union of violations, not independent per-condition rates.
    rows=[dict(probability=p,success=ok,cost_rub=c,sla=1,launch_months=12,peak_utilization=1,violations=[] if ok else ['capacity'],capex_rub=c,operating_pv_rub=0,transport_pv_rub=0,unserved_loss_pv_rub=0,waiting_rub=0,residual_pv_rub=0) for p,ok,c in [(.7,True,100),(.2,True,120),(.1,False,150)]]
    assert summarize(rows)['success_rate']==pytest.approx(.9)
    assert summarize(rows)['cvar90_rub']==150


def test_select_and_empty():
    assert select_site({'A':.6,'B':.73})['site_id']=='B'
    assert select_site({})['site_id'] is None

@pytest.fixture(scope='module')
def mvp(tmp_path_factory):
    out=tmp_path_factory.mktemp('runs')
    return recommend(request=dict(allow_demo=True,demand_scale=.75,planning_scenarios=10,validation_scenarios=100),output_root=out)


def test_pipeline(mvp):
    run,folder=mvp;assert folder.joinpath('run.json').is_file()
    assert run.run_id==DecisionRun.model_validate_json((folder/'run.json').read_text()).run_id
    assert run.recommendation not in ['C','D']
    for s in run.sites:
        if s.status=='eligible':
            assert s.validation['wilson95'][0]>=run.request.alpha
            assert s.planning['base_success']
        if s.validation:
            v=s.validation;b=v['expected_breakdown']
            total=b['capex_rub']+b['operating_pv_rub']+b['transport_pv_rub']+b['unserved_loss_pv_rub']+b['waiting_rub']-b['residual_pv_rub']
            assert total==pytest.approx(v['expected_cost_rub'])
    if run.recommendation:
        for c in run.explanation['comparisons']:assert sum(c['contributions'])==pytest.approx(c['delta'])
        assert len(run.stresses)>=2


def test_bi_run_consistency(mvp,tmp_path):
    import sqlite3
    run,_=mvp;path=tmp_path/'bi.sqlite';export_bi(run,path);export_bi(run,path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('select count(*) from run_sites').fetchone()[0]==5
        for table in ['run_sites','scenario_metrics','forecast_points','forecast_quality','rule_trace']:
            assert conn.execute(f'select distinct run_id from active_{table}').fetchall()==[(run.run_id,)]
    changed=run.model_copy(update={'run_id':'second'});export_bi(changed,path)
    with sqlite3.connect(path) as conn:
        assert conn.execute('select distinct run_id from active_run_sites').fetchall()==[('second',)]
        assert conn.execute('select count(*) from run_sites').fetchone()[0]==10
    with pytest.raises(ValueError,match='overwrite'):export_bi(run.model_copy(update={'recommendation':'OTHER'}),path)


def test_no_solution(tmp_path):
    run,_=recommend(request=dict(allow_demo=True,budget_rub=1,planning_scenarios=1,validation_scenarios=100),output_root=tmp_path)
    assert run.recommendation is None and not run.alternatives
    assert run.explanation['reasons']


def test_immutable_new_run(mvp,tmp_path):
    run,folder=mvp;before=(folder/'run.json').read_bytes()
    other,_=recommend(request=dict(allow_demo=True,budget_rub=1,planning_scenarios=1,validation_scenarios=100),output_root=tmp_path)
    assert other.run_id!=run.run_id and (folder/'run.json').read_bytes()==before

@pytest.mark.parametrize('seed',range(10))
def test_fractional_allocator_against_independent_highs(seed):
    from scipy.optimize import linprog
    rng=np.random.default_rng(100+seed);ds=rng.uniform(1,100,5);cap=float(rng.uniform(10,200));cost=rng.uniform(2,500,5);timely=rng.choice([False,True],5)
    served=min(cap,ds.sum());floor=min(.9*ds.sum(),served,ds[timely].sum())
    b=dict(capacity=cap,served_optimum=served,timely_target=floor,rows=[dict(zone=str(j),demand=float(ds[j]),reachable=True,timely=bool(timely[j]),cost_rub=float(cost[j])) for j in range(5)])
    independent=linprog(cost,A_ub=[-timely.astype(float)],b_ub=[-floor],A_eq=[np.ones(5)],b_eq=[served],bounds=list(zip(np.zeros(5),ds)),method='highs')
    assert independent.success
    analytic=analytical_flows([b])[0];cbc=solve_flows([b])['flows'][0]
    assert np.dot(cost,analytic)==pytest.approx(independent.fun,abs=.01)
    assert np.dot(cost,cbc)==pytest.approx(independent.fun,abs=.01)


def test_critical_parameters_change_input_identity():
    from site_dss.data import digest
    from site_dss.knowledge import RULES
    base=digest(RULES);changed=copy.deepcopy(RULES);changed[0]['reason']='new policy'
    assert base!=digest(changed)
    req=DecisionRequest(allow_demo=True)
    assert digest(req.model_dump())==digest(DecisionRequest.model_validate(req.model_dump()).model_dump())


def test_vectorized_batch_matches_cbc_pipeline(tmp_path):
    a,_=recommend(request=dict(allow_demo=True,demand_scale=.75,planning_scenarios=10,validation_scenarios=100,transport_backend='hybrid'),output_root=tmp_path/'fast')
    b,_=recommend(request=dict(allow_demo=True,demand_scale=.75,planning_scenarios=10,validation_scenarios=100,transport_backend='cbc'),output_root=tmp_path/'cbc')
    assert a.recommendation==b.recommendation=='B'
    for x,y in zip(a.sites,b.sites):
        assert x.status==y.status
        if x.validation:
            assert x.validation['expected_cost_rub']==pytest.approx(y.validation['expected_cost_rub'],abs=1)
            assert x.planning['expected_cost_rub']==pytest.approx(y.planning['expected_cost_rub'],abs=10)
            assert x.validation['success_rate']==y.validation['success_rate']
            assert x.score==pytest.approx(y.score)
