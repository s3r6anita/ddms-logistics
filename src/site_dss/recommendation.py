"""Integrated stages 1–8; all final gates use independent numerical validation."""
import json,time,uuid,hashlib,platform
from datetime import datetime,timezone
from pathlib import Path
import importlib.metadata
import numpy as np
from site_dss.domain import DecisionRequest,FinanceConfig,SiteResult,DecisionRun
from site_dss.data import load_snapshot,digest,write_json
from site_dss.ahp import ahp,pairwise
from site_dss.knowledge import infer,RULES
from site_dss.forecast import train
from site_dss.scenarios import build_scenarios
from site_dss.fast_transport import assess_batch
from site_dss.optimization import periods,solve_flows,analytical_flows,select_site
from site_dss.validation import evaluate
from site_dss.risk import summarize
from site_dss.utility import utilities
from site_dss.explanation import explain
from site_dss.decision_tree import build_tree,tree_svg


def pareto(sites):
    kept=[]
    for s in sites:
        if not any(np.all(np.array(o.utilities)>=s.utilities) and np.any(np.array(o.utilities)>s.utilities) for o in sites if o.site_id!=s.site_id):kept.append(s)
    return kept


def recommend(snapshot_path='data/mock/snapshot.json',finance_path='data/mock/finance.json',request=None,output_root='reports/runs',progress=None):
    started=time.perf_counter();req=DecisionRequest.model_validate(request or {})
    snapshot,quality=load_snapshot(snapshot_path,allow_demo=req.allow_demo)
    fin=FinanceConfig.model_validate_json(Path(finance_path).read_text())
    if fin.synthetic and not req.allow_demo:raise ValueError('synthetic finances require allow_demo')
    if fin.price_date>snapshot.as_of:raise ValueError('future financial price date')
    if set(fin.sites)!={s.site_id for s in snapshot.sites}:raise ValueError('finance/site mismatch')
    weights=ahp(pairwise(req.comparisons))['weights']
    source=Path(__file__).parent
    code_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.rglob('*.py')))).hexdigest()
    provenance=dict(snapshot_hash=digest(snapshot.model_dump(mode='json')),finance_hash=digest(fin.model_dump(mode='json')),rules_hash=digest(RULES),code_hash=code_hash,python=platform.python_version(),dependencies={n:importlib.metadata.version(n) for n in ['pulp','cbcbox','numpy','scipy','statsmodels','streamlit']})
    input_hash=digest(dict(**provenance,request=req.model_dump(mode='json')))
    run_id=input_hash[:12]+'-'+uuid.uuid4().hex[:8]
    root=Path(output_root)/run_id;root.mkdir(parents=True,exist_ok=False)
    write_json(root/'snapshot.json',snapshot.model_dump(mode='json'));write_json(root/'finance.json',fin.model_dump(mode='json'));write_json(root/'rules.json',RULES)
    if progress:progress('Прогноз и общие сценарии',.05)
    fc=train(snapshot);plan=build_scenarios(fc,req.planning_scenarios,req.seed);check=build_scenarios(fc,req.validation_scenarios,req.seed+1)
    write_json(root/'planning_scenarios.json',plan);write_json(root/'validation_scenarios.json',check)
    base=dict(plan['scenarios'][0],scenario_id='base',probability=1.,demand_paths={z:[p['point'] for p in fc['points'] if p['zone_id']==z] for z in snapshot.zones},demand_growth_factors=[1.]*5,tariff_factors=[1.]*5,capex_factors=[1.]*5,route_state='normal',connection_delay=0)
    results=[];all_rows=[];witnesses=[]
    for index,site in enumerate(snapshot.sites):
        if progress:progress(f'Площадка {site.site_id}: оптимизация и проверка риска',.1+.75*index/len(snapshot.sites))
        design=next(d for d in snapshot.designs if d.project_id==site.project_id)
        knowledge=infer(site,unknown=quality['missing_critical'][site.site_id],budget=req.budget_rub,synthetic=snapshot.synthetic or fin.synthetic,power_required_kw=design.power_required_kw)
        result=SiteResult(site_id=site.site_id,status=knowledge['status'],knowledge=knowledge)
        if result.status!='eligible_for_calculation':
            result.diagnostics=[t['reason'] for t in knowledge['trace'] if t['conclusion'] in ['excluded','needs_confirmation']];results.append(result);continue
        finance=fin.sites[site.site_id]
        base_blocks=periods(snapshot,site,base,req,finance,plan['target_months'])
        base_solution=solve_flows(base_blocks,time_limit=req.solver_time_limit,export_prefix=root/f'base_{site.site_id}')
        result.solver_status=base_solution['status']
        if base_solution['flows'] is None:
            result.status='solver_unresolved';result.diagnostics=[base_solution['reason']];results.append(result);continue
        base_row=evaluate(base_blocks,base_solution['flows'],site,base,req,finance)
        witnesses.append(dict(site_id=site.site_id,scenario_id='base',flows=base_solution['flows']))
        if req.transport_backend=='hybrid':
            plan_rows,plan_flows=assess_batch(snapshot,site,plan['scenarios'],req,finance,plan['target_months'])
            independent,_=assess_batch(snapshot,site,check['scenarios'],req,finance,check['target_months'])
            # Certify representative planning LPs using CBC and independent evaluator.
            audits=sorted({0,max(range(len(plan_rows)),key=lambda j:plan_rows[j]['cost_rub'])})
            for j in audits:
                sc=plan['scenarios'][j];blocks=periods(snapshot,site,sc,req,finance,plan['target_months'])
                sol=solve_flows(blocks,time_limit=req.solver_time_limit,export_prefix=root/f'audit_{site.site_id}_{j}')
                if sol['flows'] is None:raise RuntimeError('CBC audit unresolved: '+str(sol['reason']))
                row=evaluate(blocks,sol['flows'],site,sc,req,finance)
                if abs(row['cost_rub']-plan_rows[j]['cost_rub'])>max(10,row['cost_rub']*1e-7) or row['success']!=plan_rows[j]['success']:raise ValueError('batch/CBC audit mismatch')
            np.save(root/f'planning_flows_{site.site_id}.npy',plan_flows,allow_pickle=False)
            result.solver_status='OPTIMAL'
        else:
            plan_rows=[];unresolved=False;statuses=[base_solution['status']]
            for number,sc in enumerate(plan['scenarios']):
                blocks=periods(snapshot,site,sc,req,finance,plan['target_months'])
                sol=solve_flows(blocks,time_limit=req.solver_time_limit)
                statuses.append(sol['status'])
                if sol['flows'] is None:unresolved=True;break
                row=evaluate(blocks,sol['flows'],site,sc,req,finance);plan_rows.append(row)
                witnesses.append(dict(site_id=site.site_id,scenario_id=sc['scenario_id'],flows=sol['flows']))
            if unresolved:
                result.status='solver_unresolved';result.solver_status='UNKNOWN';result.diagnostics=['Не все плановые сценарии решены; рекомендация блокируется.'];results.append(result);continue
            result.solver_status='OPTIMAL' if all(s=='OPTIMAL' for s in statuses) else 'FEASIBLE'
            independent=[]
            for sc in check['scenarios']:
                blocks=periods(snapshot,site,sc,req,finance,check['target_months'])
                row=evaluate(blocks,analytical_flows(blocks),site,sc,req,finance);independent.append(row)
        result.planning=summarize(plan_rows);result.validation=summarize(independent,independent=True)
        result.planning['base_success']=base_row['success'];result.planning['base_violations']=base_row['violations']
        result.utilities=utilities(result.validation['expected_cost_rub']/1e6,result.validation['expected_sla'],result.validation['expected_launch_months'],site.expandable_fraction).tolist()
        result.score=float(np.dot(result.utilities,weights))
        risk_gate=result.validation['wilson95'][0] if req.risk_policy=='wilson_lower' else result.validation['success_rate']
        result.knowledge=infer(site,unknown=quality['missing_critical'][site.site_id],budget=req.budget_rub,synthetic=snapshot.synthetic or fin.synthetic,power_required_kw=design.power_required_kw,success=risk_gate,alpha=req.alpha)
        result.status='eligible' if base_row['success'] and result.planning['success_rate']+1e-12>=req.alpha and risk_gate+1e-12>=req.alpha else 'risk_rejected'
        if not base_row['success']:result.diagnostics.append('Базовый сценарий: '+', '.join(base_row['violations']))
        if result.planning['success_rate']+1e-12<req.alpha:result.diagnostics.append(f"Плановая совместная успешность {result.planning['success_rate']:.1%} ниже {req.alpha:.1%}")
        if risk_gate+1e-12<req.alpha:result.diagnostics.append(f'Проверочный риск ({req.risk_policy}): {risk_gate:.1%} ниже {req.alpha:.1%}')
        for sample,rows in [('planning',plan_rows),('validation',independent)]:
            all_rows.extend(dict(**row,site_id=site.site_id,sample=sample) for row in rows)
        results.append(result)
    eligible=[s for s in results if s.status=='eligible']
    selection=select_site({s.site_id:s.score for s in eligible},root/'selection',req.solver_time_limit)
    winner=selection['site_id'];front=pareto(eligible)
    others=[s for s in front if s.site_id!=winner]
    alternatives=[]
    for key in [lambda s:s.validation['expected_cost_rub'],lambda s:s.validation['cvar90_rub']]:
        if others:
            pick=min(others,key=key)
            if pick not in alternatives:alternatives.append(pick)
    for s in sorted(others,key=lambda s:s.score,reverse=True):
        if len(alternatives)<2 and s not in alternatives:alternatives.append(s)
    sensitivity=[]
    for k in np.linspace(0,1,21):
        w=[k,(1-k)*.5,(1-k)/3,(1-k)/6]
        best=max(eligible,key=lambda s:np.dot(w,s.utilities),default=None)
        sensitivity.append(dict(cost_weight=float(k),winner=best.site_id if best else None,scores={s.site_id:float(np.dot(w,s.utilities)) for s in eligible}))
    stresses=[]
    for s in eligible:
        site=next(i for i in snapshot.sites if i.site_id==s.site_id);finance=fin.sites[site.site_id]
        for name in ['road_closed','connection_delay']:
            sc=dict(base,connection_delay=12 if name=='connection_delay' else 0)
            blocks=periods(snapshot,site,sc,req,finance,plan['target_months'],closed=name=='road_closed')
            row=evaluate(blocks,analytical_flows(blocks),site,sc,req,finance)
            stresses.append({**row,'site_id':s.site_id,'stress':name,'probability':None})
    explanation=explain(results,winner,weights);explanation['selection_solver']=selection
    run=DecisionRun(run_id=run_id,created_at=datetime.now(timezone.utc).isoformat(),version='0.3.0',synthetic=snapshot.synthetic or fin.synthetic,request=req,provenance=dict(**provenance,input_hash=input_hash),forecast=fc,sites=results,recommendation=winner,alternatives=[s.site_id for s in alternatives],explanation=explanation,sensitivity=sensitivity,stresses=stresses,scenario_metrics=all_rows,decision_tree=build_tree(results,all_rows),elapsed_seconds=time.perf_counter()-started)
    write_json(root/'flows.json',witnesses);write_json(root/'run.json',run.model_dump(mode='json'))
    from site_dss.export import html_report
    (root/'report.html').write_text(html_report(run))
    (root/'decision_tree.svg').write_text(tree_svg(run.decision_tree))
    if progress:progress('Расчет сохранен',1.)
    return run,root
