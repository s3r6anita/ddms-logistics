"""Reproduce design example; standard library only. Not the future MVP."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = [0.7, 0.2, 0.1]
demand = [120, 150, 170]
w = [0.4, 0.3, 0.2, 0.1]
a = [[x/y for y in w] for x in w]
af = sum(1/1.1**t for t in range(1, 6))
sites = [
    dict(id='A', name='Север', capex=[650,720,880], opex=[80,92,106], sla=[.94,.91,.82], capacity=160, launch=14, expansion=.2, legal=True),
    dict(id='B', name='Восток', capex=[740,800,870], opex=[70,80,92], sla=[.97,.95,.92], capacity=190, launch=12, expansion=.4, legal=True),
    dict(id='C', name='Юг', capex=[950,1020,1150], opex=[65,75,90], sla=[.98,.96,.93], capacity=200, launch=12, expansion=.3, legal=True),
    dict(id='D', name='Запад', capex=[620,700,850], opex=[85,98,115], sla=[.93,.90,.80], capacity=180, launch=16, expansion=.1, legal=None),
]
def expectation(xs): return sum(q*x for q,x in zip(p,xs))
def clip(x): return min(1, max(0,x))
def quantile(xs, q):
    cumulative = 0
    for x, probability in sorted(zip(xs,p)):
        cumulative += probability
        if cumulative + 1e-12 >= q: return x

def cvar(xs, alpha):
    remaining=1-alpha
    loss=0
    for x, probability in sorted(zip(xs,p), reverse=True):
        take=min(remaining, probability)
        loss+=take*x
        remaining-=take
        if remaining<1e-12: break
    return loss/(1-alpha)

results=[]
for s in sites:
    costs=[k+af*o for k,o in zip(s['capex'],s['opex'])]
    success=[k<=900 and s['capacity']>=d and sl>=.9 and s['launch']<=18 for k,d,sl in zip(s['capex'],demand,s['sla'])]
    eligibility='eligible' if s['legal'] is True and s['capex'][0]<=900 else ('needs_confirmation' if s['legal'] is None else 'excluded')
    u=[clip((1300-expectation(costs))/400),clip((expectation(s['sla'])-.85)/.14),clip((20-s['launch'])/10),clip(s['expansion']/.5)]
    results.append(dict(id=s['id'],eligibility=eligibility,costs=costs,expected_cost=expectation(costs),p90=quantile(costs,.9),cvar90=cvar(costs,.9),expected_sla=expectation(s['sla']),success=expectation(success),utilities=u,score=sum(x*y for x,y in zip(u,w))))
rA,rB=results[:2]
other_diff=sum(w[i]/.6*(rB['utilities'][i]-rA['utilities'][i]) for i in range(1,4))
cost_diff=rB['utilities'][0]-rA['utilities'][0]
threshold=other_diff/(other_diff-cost_diff)
assert abs(sum(w)-1)<1e-12
assert all(abs(sum(a[i][j]*w[j] for j in range(4))-4*w[i])<1e-12 for i in range(4))
assert abs(rA['success']-.9)<1e-12 and abs(rB['success']-1)<1e-12
assert rB['score']>rA['score']
assert results[2]['eligibility']=='excluded' and results[3]['eligibility']=='needs_confirmation'
assert rA['cvar90']>rB['cvar90']
assert abs(threshold*cost_diff+(1-threshold)*other_diff)<1e-12
eligible_results=[r for r in results if r['eligibility']=='eligible' and r['success']+1e-12>=.9]
winner=max(eligible_results,key=lambda r:r['score'])['id']
out=dict(data_kind='synthetic',scenario_probabilities=p,demand_thousand_pallets=demand,weights=w,ahp_matrix=a,lambda_max=4,CR=0,annuity_factor=af,sites=results,cost_weight_switch=threshold,recommendation=winner,checks='8 assertions passed')
(ROOT/'data/demo/sites.json').write_text(json.dumps(sites,ensure_ascii=False,indent=2)+'\n')
(ROOT/'reports/design_example.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
