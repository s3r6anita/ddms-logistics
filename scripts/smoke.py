"""Small functional smoke; does not replace the full 100/1000 run."""
from site_dss.recommendation import recommend
r,p=recommend(request=dict(allow_demo=True,demand_scale=.75,planning_scenarios=10,validation_scenarios=100),output_root='.runtime/smoke')
assert r.recommendation=='B'
print('Smoke passed: B; 10 planning / 100 validation scenarios; report:',p)
