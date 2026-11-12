"""Independent numerical validation; does not trust the solver's status."""
import math

def validate_flows(blocks,flows):
    if len(blocks)!=len(flows):raise ValueError('flow length mismatch')
    for b,values in zip(blocks,flows):
        if len(values)!=len(b['rows']):raise ValueError('zone count mismatch')
        # CBC writes decimal incumbents; tolerance in pallets, never a service waiver.
        tol=max(1e-3,sum(row['demand'] for row in b['rows'])*1e-7)
        for row,v in zip(b['rows'],values):
            if not math.isfinite(v) or v < -tol or v>row['demand']+tol:raise ValueError('flow outside demand bounds')
            if not row['reachable'] and abs(v)>tol:raise ValueError('closed route used')
        if sum(values)>b['capacity']+tol:raise ValueError('physical capacity exceeded')
        if abs(sum(values)-b['served_optimum'])>tol:raise ValueError('service optimum not attained')
        timely=sum(v for row,v in zip(b['rows'],values) if row['timely'])
        if timely+tol<b['timely_target']:raise ValueError('timely floor violated')
    return True


def evaluate(blocks,flows,site,scenario,request,finance):
    validate_flows(blocks,flows)
    total=timely=unserved=0.;transport=loss=operating=0.;violations=set();peak_util=0.
    launch=site.launch_months+scenario['connection_delay']
    capex=site.capex_rub*scenario['capex_factors'][0]
    if capex>request.budget_rub+1e-3:violations.add('budget')
    if launch>request.max_launch_months:violations.add('launch')
    for b,values in zip(blocks,flows):
        demand=sum(row['demand'] for row in b['rows']);served=sum(values)
        ontime=sum(v for row,v in zip(b['rows'],values) if row['timely'])
        missing=max(0,demand-served);sla=ontime/demand if demand else 1.
        total+=demand;timely+=ontime;unserved+=missing
        if missing>max(.001,demand*1e-7):violations.add('capacity_or_access')
        if sla+1e-7<request.sla_target:violations.add('sla')
        peak_util=max(peak_util,served/b['capacity'] if b['capacity'] else (1 if served else 0))
        # Monthly cashflows start at launch; all candidates share decision-date t=0.
        discount=(1+request.discount_rate)**(launch/12+b['year']+(b['month']+1)/12)
        transport+=sum(v*row['cost_rub'] for row,v in zip(b['rows'],values))/discount
        loss+=missing*finance.unserved_loss_rub_pallet/discount
        operating+=finance.fixed_opex_rub_year/12*scenario['tariff_factors'][b['year']]/discount
    waiting=finance.waiting_cost_rub_month*launch
    residual=finance.residual_value_rub/(1+request.discount_rate)**(launch/12+5)
    cost=capex+operating+transport+loss+waiting-residual
    return dict(scenario_id=scenario['scenario_id'],probability=scenario['probability'],cost_rub=cost,capex_rub=capex,operating_pv_rub=operating,transport_pv_rub=transport,unserved_loss_pv_rub=loss,waiting_rub=waiting,residual_pv_rub=residual,sla=timely/total if total else 1.,unserved_pallets=unserved,peak_utilization=peak_util,launch_months=launch,success=not violations,violations=sorted(violations))


def validate_batch(demand,flows,capacity,reachable,timely,sla_target):
    """Independent vector checks of original bounds and lexicographic optima."""
    import numpy as np
    if flows.shape!=demand.shape or not np.isfinite(flows).all():raise ValueError('invalid batch shape/values')
    tolerance=np.maximum(.001,demand.sum(axis=-1)*1e-7)
    if (flows<-.001).any() or (flows-demand>.001).any():raise ValueError('batch demand bounds')
    if (np.abs(flows*(~reachable))>.001).any():raise ValueError('batch closed routes')
    total_served=flows.sum(axis=-1)
    if (total_served-capacity>tolerance).any():raise ValueError('batch capacity exceeded')
    max_served=np.minimum(capacity,(demand*reachable).sum(axis=-1))
    if (np.abs(total_served-max_served)>tolerance).any():raise ValueError('batch service optimum')
    timely_required=np.minimum(np.minimum(sla_target*demand.sum(axis=-1),max_served),(demand*timely).sum(axis=-1))
    if (timely_required-(flows*timely).sum(axis=-1)>tolerance).any():raise ValueError('batch timely floor')
    return True
