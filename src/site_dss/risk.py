import math

def wilson(successes,n,z=1.959963984540054):
    if n<=0 or not 0<=successes<=n:raise ValueError('invalid binomial sample')
    p=successes/n;den=1+z*z/n;centre=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,centre-half),min(1,centre+half)]

def weighted_quantile(values,probabilities,q):
    if not 0<=q<=1:raise ValueError('invalid quantile')
    cumulative=0
    for v,p in sorted(zip(values,probabilities)):
        cumulative+=p
        if cumulative+1e-12>=q:return v
    return max(values)

def cvar(values,probabilities,alpha=.9):
    if not 0<=alpha<1:raise ValueError('invalid CVaR level')
    remaining=1-alpha;tail=0.
    for v,p in sorted(zip(values,probabilities),reverse=True):
        take=min(remaining,p);tail+=take*v;remaining-=take
        if remaining<1e-12:break
    return tail/(1-alpha)

def summarize(rows,*,independent=False):
    if not rows:raise ValueError('empty scenario set')
    probs=[r['probability'] for r in rows]
    if any(p<0 for p in probs) or abs(sum(probs)-1)>1e-9:raise ValueError('invalid probabilities')
    expect=lambda name:sum(p*r[name] for p,r in zip(probs,rows))
    costs=[r['cost_rub'] for r in rows]
    reasons={k:sum(p for p,r in zip(probs,rows) if k in r['violations']) for k in sorted({k for r in rows for k in r['violations']})}
    result=dict(expected_cost_rub=expect('cost_rub'),p90_cost_rub=weighted_quantile(costs,probs,.9),cvar90_rub=cvar(costs,probs),success_rate=expect('success'),expected_sla=expect('sla'),expected_launch_months=expect('launch_months'),max_peak_utilization=max(r['peak_utilization'] for r in rows),failures=reasons,expected_breakdown={k:expect(k) for k in ['capex_rub','operating_pv_rub','transport_pv_rub','unserved_loss_pv_rub','waiting_rub','residual_pv_rub']})
    if independent:
        if max(probs)-min(probs)>1e-12:raise ValueError('Wilson requires equal independent draws')
        result['wilson95']=wilson(sum(bool(r['success']) for r in rows),len(rows))
    return result
