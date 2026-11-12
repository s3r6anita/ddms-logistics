"""Synthetic upper-bound integration workload; never alters the demo catalog."""
import argparse,copy,json,os,platform,time
from pathlib import Path
import numpy as np
from site_dss.recommendation import recommend
from site_dss.data import write_json
p=argparse.ArgumentParser();p.add_argument('--repetitions',type=int,default=3);a=p.parse_args()
root=Path('.runtime/benchmark');root.mkdir(parents=True,exist_ok=True)
s=json.loads(Path('data/mock/snapshot.json').read_text());f=json.loads(Path('data/mock/finance.json').read_text())
original=copy.deepcopy(s);finance=copy.deepcopy(f['sites']['B']);s['sites']=[];s['designs']=[];s['routes']=[];s['demand']=[];s['costs']=[];f['sites']={};s['zones']=[f'Z{j:02}' for j in range(50)]
for j,z in enumerate(s['zones']):
    for d in original['demand'][:60]:
        row=copy.deepcopy(d);row['zone_id']=z
        for k in ['ordered_pallets','shipped_pallets','unfulfilled_pallets']:row[k]*=.05
        s['demand'].append(row)
for i in range(20):
    sid=f'X{i:02}';site=copy.deepcopy(original['sites'][1]);site.update(site_id=sid,project_id=sid,name='Benchmark '+sid,capex_rub=(600+i*8)*1e6);s['sites'].append(site)
    design=copy.deepcopy(original['designs'][1]);design.update(project_id=sid,throughput_pallets_month=[(180000+i*2000)/12]*12);s['designs'].append(design)
    cost=copy.deepcopy(original['costs'][1]);cost.update(site_id=sid,amount=site['capex_rub']);s['costs'].append(cost)
    for j,z in enumerate(s['zones']):
        for period in ['peak','offpeak']:
            route=copy.deepcopy(original['routes'][0]);route.update(site_id=sid,zone_id=z,period=period,minutes=60+(i%5)*5+j%7*2,variable_cost_rub_pallet=200+i*3+j%7);s['routes'].append(route)
    f['sites'][sid]={**finance,'fixed_opex_rub_year':(40+i)*1e6}
write_json(root/'snapshot.json',s);write_json(root/'finance.json',f)
times=[]
for k in range(a.repetitions):
    wall_start=time.perf_counter()
    run,folder=recommend(root/'snapshot.json',root/'finance.json',dict(allow_demo=True,demand_scale=.75),root/'runs',progress=lambda text,p:print(k,text,flush=True))
    wall=time.perf_counter()-wall_start
    times.append(wall);print('BENCHMARK',k,wall,flush=True)
    write_json('reports/stages5_8/benchmark.json',dict(timing='end-to-end recommend(), including model audits and file exports',workload='20 sites × 50 zones × 12 forecast months × 5 operating years × 100 planning + 1000 independent scenarios',machine=dict(platform=platform.platform(),cpu_count=os.cpu_count()),seconds=times,p95_seconds=float(np.quantile(times,.95)),target_seconds=60,target_met=float(np.quantile(times,.95))<=60,replications=len(times),limitations='Empirical p95 on a small repetition count; not an SLA guarantee.'))
