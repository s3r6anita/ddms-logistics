"""Exact decomposition: fixed-site monthly transport LP, then binary site choice."""
from pathlib import Path
import math
import pulp


def periods(snapshot,site,scenario,request,finance,target_months,*,closed=False):
    design=next(d for d in snapshot.designs if d.project_id==site.project_id)
    routes={r.zone_id:r for r in snapshot.routes if r.site_id==site.site_id and r.period=='peak'}
    result=[]
    for y in range(5):
        for t in range(12):
            calendar_month=int(target_months[t][5:7])-1
            capacity=min(design.throughput_pallets_month[calendar_month],design.storage_pallets*30/finance.dwell_days)
            rows=[]
            for zone in snapshot.zones:
                r=routes[zone]
                demand=scenario['demand_paths'][zone][t]*scenario['demand_growth_factors'][y]*request.demand_scale
                reachable=r.reachable is True and not closed
                minutes=(r.minutes or 0)*(1.15 if scenario['route_state']=='restricted' else 1)
                rows.append(dict(zone=zone,demand=demand,reachable=reachable,timely=reachable and minutes<=request.max_delivery_minutes,cost_rub=(r.variable_cost_rub_pallet or 0)*scenario['tariff_factors'][y]))
            total=sum(r['demand'] for r in rows)
            served=min(capacity,sum(r['demand'] for r in rows if r['reachable']))
            target=min(request.sla_target*total,served,sum(r['demand'] for r in rows if r['timely']))
            result.append(dict(year=y,month=t,capacity=capacity,rows=rows,served_optimum=served,timely_target=target))
    return result


def analytical_flows(blocks):
    """Exact specialized allocator used as independent witness, not a general LP solver.

    One site, divisible pallets, one arc per zone, one capacity and one timely floor.
    Fill the timely floor with cheapest timely arcs, then cheapest remaining arcs.
    """
    flows=[]
    for b in blocks:
        rows=b['rows'];f=[0.]*len(rows);need=b['timely_target']
        for j in sorted(range(len(rows)),key=lambda j:(rows[j]['cost_rub'],j)):
            if rows[j]['timely']:
                take=min(need,rows[j]['demand']);f[j]+=take;need-=take
        remaining=b['served_optimum']-sum(f)
        for j in sorted(range(len(rows)),key=lambda j:(rows[j]['cost_rub'],j)):
            if rows[j]['reachable']:
                take=min(remaining,rows[j]['demand']-f[j]);f[j]+=take;remaining-=take
        flows.append(f)
    return flows


def solve_flows(blocks,*,time_limit=10,export_prefix=None):
    if time_limit<=0:return dict(status='UNKNOWN',flows=None,gap=None,reason='time limit exhausted')
    model=pulp.LpProblem('fixed_site_transport',pulp.LpMinimize)
    f={};r={}
    for k,b in enumerate(blocks):
        for j,row in enumerate(b['rows']):
            f[k,j]=model.add_variable(f'f_{k}_{j}',lowBound=0,upBound=row['demand'] if row['reachable'] else 0)
            r[k,j]=model.add_variable(f'r_{k}_{j}',lowBound=0,upBound=row['demand'])
            model+=f[k,j]+r[k,j]==row['demand'],f'balance_{k}_{j}'
        # Closed-form first-stage optimum: all pallets have the same resource use.
        model+=pulp.lpSum(f[k,j] for j in range(len(b['rows'])))==b['served_optimum'],f'max_service_{k}'
        model+=pulp.lpSum(f[k,j] for j in range(len(b['rows'])))<=b['capacity'],f'capacity_{k}'
        model+=pulp.lpSum(f[k,j] for j,row in enumerate(b['rows']) if row['timely'])>=b['timely_target'],f'timely_floor_{k}'
    model+=pulp.lpSum(f[k,j]*row['cost_rub'] for k,b in enumerate(blocks) for j,row in enumerate(b['rows']))
    log=None
    if export_prefix:
        prefix=Path(export_prefix);prefix.parent.mkdir(parents=True,exist_ok=True)
        model.writeLP(str(prefix)+'.lp');model.writeMPS(str(prefix)+'.mps');log=str(prefix)+'.log'
    solver=pulp.COIN_CMD(msg=False,timeLimit=time_limit,threads=1,randomSeed=1,logPath=log)
    try:stats=model.solve(solver)
    except pulp.PulpSolverError as e:
        import subprocess
        probe=subprocess.run([solver.path,'-stop'],capture_output=True,text=True)
        return dict(status='UNKNOWN',flows=None,gap=None,reason=str(e)+f'; probe exit={probe.returncode}; '+probe.stderr[:300])
    if stats.status==pulp.LpSolveStatus.Infeasible:return dict(status='INFEASIBLE',flows=None,gap=None,reason='CBC proved infeasible')
    if not stats.has_solution:return dict(status='UNKNOWN',flows=None,gap=None,reason=stats.status_str)
    status='OPTIMAL' if stats.status==pulp.LpSolveStatus.Optimal and stats.has_solution else 'FEASIBLE'
    values=[[f[k,j].value() for j in range(len(b['rows']))] for k,b in enumerate(blocks)]
    if any(v is None or not math.isfinite(v) for row in values for v in row):return dict(status='UNKNOWN',flows=None,gap=None,reason='no incumbent')
    return dict(status=status,flows=values,gap=0. if status=='OPTIMAL' else None,reason=None)


def select_site(scores,export_prefix=None,time_limit=10):
    if not scores:return dict(site_id=None,status='INFEASIBLE',gap=None)
    model=pulp.LpProblem('select_one_site',pulp.LpMaximize)
    x={i:model.add_variable('choose_'+i,cat='Binary') for i in scores}
    model+=pulp.lpSum(x.values())==1
    model+=pulp.lpSum(scores[i]*x[i] for i in scores)
    if export_prefix:
        model.writeLP(str(export_prefix)+'.lp');model.writeMPS(str(export_prefix)+'.mps')
    stats=model.solve(pulp.COIN_CMD(msg=False,timeLimit=time_limit,threads=1,randomSeed=1))
    if stats.status!=pulp.LpSolveStatus.Optimal:return dict(site_id=None,status='UNKNOWN',gap=None)
    return dict(site_id=next(i for i in scores if x[i].value()>.5),status='OPTIMAL',gap=0.)
