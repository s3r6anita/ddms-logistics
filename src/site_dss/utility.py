import numpy as np
from scipy.optimize import brentq

def utilities(cost_million,sla,launch_months,expansion):
    a=np.asarray([cost_million,sla,launch_months,expansion],dtype=float)
    if not np.isfinite(a).all() or cost_million<0 or not 0<=sla<=1 or launch_months<0 or expansion<0: raise ValueError('invalid criteria')
    return np.clip([(1300-cost_million)/400,(sla-.85)/.14,(20-launch_months)/10,expansion/.5],0,1)

def compare(a,b,weights):
    a=np.asarray(a); b=np.asarray(b); w=np.asarray(weights)
    if a.shape!=(4,) or b.shape!=(4,) or not np.isfinite(a).all() or not np.isfinite(b).all(): raise ValueError('invalid utility vectors')
    if w.shape!=(4,) or (w<0).any() or not np.isfinite(w).all() or not np.isclose(w.sum(),1): raise ValueError('invalid weights')
    return dict(score_a=float(a@w),score_b=float(b@w),contributions=(w*(b-a)).tolist(),delta=float((b-a)@w))

def cost_weight_switch(a,b):
    diff=np.asarray(b)-np.asarray(a)
    def f(k): return float(np.array([k,(1-k)*.5,(1-k)/3,(1-k)/6])@diff)
    return float(brentq(f,0,1)) if f(0)*f(1)<0 else None
