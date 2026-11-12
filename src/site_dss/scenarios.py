import numpy as np
from site_dss.domain import Scenario

def build_scenarios(forecast,n=100,seed=20261112):
    if n<1:raise ValueError('n must be positive')
    rng=np.random.default_rng(seed);zones=forecast['zones'];errors=np.asarray(forecast['calibration_errors'])
    points={z:np.array([p['point'] for p in forecast['points'] if p['zone_id']==z]) for z in zones}
    scenarios=[]
    for i in range(n):
        # All zones share the same sampled contiguous blocks: preserve cross-zone dependence.
        indices=np.concatenate([np.arange(k,k+3)%len(errors) for k in rng.integers(0,len(errors),4)])
        shock=float(rng.normal());growth=float(np.clip(.03+.02*shock,-.03,.12))
        demand={z:np.maximum(0,points[z]+errors[indices,j]).tolist() for j,z in enumerate(zones)}
        tariffs=[float(np.exp(.07*shock)*(1+growth)**y) for y in range(5)]
        capex=[float(np.exp(.05*shock))]*5
        s=Scenario(scenario_id=f'S{i:04}',probability=1/n,kind='synthetic',demand_paths=demand,demand_growth_factors=[float((1+growth)**y) for y in range(5)],tariff_factors=tariffs,capex_factors=capex,route_state='restricted' if shock>1.28 else 'normal',connection_delay=max(0,int(round(shock*2))),seed=seed)
        scenarios.append(s.model_dump())
    if abs(sum(s['probability'] for s in scenarios)-1)>1e-9:raise ValueError('probabilities must sum to 1')
    return dict(synthetic=True,seed=seed,forecast_data_hash=forecast['data_hash'],target_months=sorted({p['target_month'] for p in forecast['points']}),assumptions='Экспертная Gaussian-связь факторов; трехмесячные блоки ошибок; год 1 по прогнозу, годы 2–5 по факторам роста; одинаковы для всех площадок',scenarios=scenarios,stress_tests=[dict(id='road_closed',probability=None,description='Основной подъезд недоступен'),dict(id='connection_delay',probability=None,delay_months=12)])
