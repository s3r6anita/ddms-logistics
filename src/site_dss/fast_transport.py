"""Vectorized exact solution for one-site, uncoupled, divisible-pallet transport LPs.

A common positive scenario tariff multiplier preserves arc cost order. First fill
required timely volume on cheapest timely arcs, then cheapest residual arcs.
This solves the same bounded continuous LP as optimization.solve_flows.
"""
import numpy as np
from site_dss.validation import validate_batch


def assess_batch(snapshot,site,scenarios,req,finance,target_months):
    zones=snapshot.zones;design=next(d for d in snapshot.designs if d.project_id==site.project_id)
    routes={r.zone_id:r for r in snapshot.routes if r.site_id==site.site_id and r.period=='peak'}
    months=[int(m[5:7])-1 for m in target_months]
    capacity=np.minimum([design.throughput_pallets_month[m] for m in months],design.storage_pallets*30/finance.dwell_days)[None,None,:]
    base_demand=np.array([[[s['demand_paths'][z][t] for z in zones] for t in range(12)] for s in scenarios])
    growth=np.array([s['demand_growth_factors'] for s in scenarios])
    demand=base_demand[:,None,:,:]*growth[:,:,None,None]*req.demand_scale
    reachable=np.array([routes[z].reachable is True for z in zones])[None,None,None,:]
    minutes=np.array([routes[z].minutes or 0 for z in zones])
    factor=np.array([1.15 if s['route_state']=='restricted' else 1 for s in scenarios])
    timely=(factor[:,None]*minutes[None,:]<=req.max_delivery_minutes)[:,None,None,:]&reachable
    costs=np.array([routes[z].variable_cost_rub_pallet or 0 for z in zones]);order=np.argsort(costs,kind='stable')
    demands=demand[...,order];available=demands*reachable[...,order];fast=available*timely[...,order]
    total=demands.sum(axis=-1);served=np.minimum(capacity,available.sum(axis=-1))
    floor=np.minimum(np.minimum(req.sla_target*total,served),fast.sum(axis=-1))
    before=np.cumsum(fast,axis=-1)-fast
    first=np.maximum(0,np.minimum(fast,floor[...,None]-before))
    residual=available-first;remaining=served-first.sum(axis=-1)
    before=np.cumsum(residual,axis=-1)-residual
    flows=first+np.maximum(0,np.minimum(residual,remaining[...,None]-before))
    inv=np.argsort(order);flows=flows[...,inv]
    validate_batch(demand,flows,capacity,reachable,timely,req.sla_target)
    delivered=flows.sum(axis=-1);on_time=(flows*timely).sum(axis=-1);missing=np.maximum(0,total-delivered)
    launch=np.array([site.launch_months+s['connection_delay'] for s in scenarios])
    capex=np.array([site.capex_rub*s['capex_factors'][0] for s in scenarios])
    tariff=np.array([s['tariff_factors'] for s in scenarios])[:,:,None]
    years=np.arange(5)[None,:,None];month_end=np.arange(1,13)[None,None,:]/12
    discount=(1+req.discount_rate)**(launch[:,None,None]/12+years+month_end)
    transport=((flows*costs[None,None,None,:]).sum(axis=-1)*tariff/discount).sum(axis=(1,2))
    losses=(missing*finance.unserved_loss_rub_pallet/discount).sum(axis=(1,2))
    operating=(np.ones_like(total)*finance.fixed_opex_rub_year/12*tariff/discount).sum(axis=(1,2))
    waiting=finance.waiting_cost_rub_month*launch
    residual_pv=finance.residual_value_rub/(1+req.discount_rate)**(launch/12+5)
    full_cost=capex+transport+losses+operating+waiting-residual_pv
    row_sla=np.divide(on_time,total,out=np.ones_like(total),where=total>0)
    all_sla=np.divide(on_time.sum(axis=(1,2)),total.sum(axis=(1,2)),out=np.ones(len(scenarios)),where=total.sum(axis=(1,2))>0)
    cap_failure=(missing>np.maximum(.001,total*1e-7)).any(axis=(1,2))
    sla_failure=(row_sla+1e-7<req.sla_target).any(axis=(1,2))
    peak=(delivered/capacity).max(axis=(1,2))
    rows=[]
    for k,s in enumerate(scenarios):
        violations=[]
        if capex[k]>req.budget_rub+1e-3:violations.append('budget')
        if launch[k]>req.max_launch_months:violations.append('launch')
        if cap_failure[k]:violations.append('capacity_or_access')
        if sla_failure[k]:violations.append('sla')
        rows.append(dict(scenario_id=s['scenario_id'],probability=s['probability'],cost_rub=float(full_cost[k]),capex_rub=float(capex[k]),operating_pv_rub=float(operating[k]),transport_pv_rub=float(transport[k]),unserved_loss_pv_rub=float(losses[k]),waiting_rub=float(waiting[k]),residual_pv_rub=float(residual_pv[k]),sla=float(all_sla[k]),unserved_pallets=float(missing[k].sum()),peak_utilization=float(peak[k]),launch_months=float(launch[k]),success=not violations,violations=sorted(violations)))
    return rows,flows
