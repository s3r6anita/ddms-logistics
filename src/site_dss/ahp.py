import numpy as np

def ahp(matrix):
    a=np.asarray(matrix,dtype=float)
    if a.shape!=(4,4) or not np.isfinite(a).all() or (a<=0).any(): raise ValueError('expected positive finite 4x4 matrix')
    if not np.allclose(np.diag(a),1) or not np.allclose(a*a.T,1): raise ValueError('matrix must be reciprocal with unit diagonal')
    values,vectors=np.linalg.eig(a); index=np.argmax(values.real)
    w=np.abs(vectors[:,index].real); w/=w.sum()
    lam=float(values[index].real); ci=max(0,(lam-4)/3); cr=ci/.9
    if cr>.1: raise ValueError(f'inconsistent AHP: CR={cr:.6f}>0.10')
    return dict(weights=w.tolist(),lambda_max=lam,CI=ci,CR=cr)

def pairwise(values):
    v=np.asarray(values,dtype=float)
    if v.shape!=(6,) or (v<=0).any() or not np.isfinite(v).all(): raise ValueError('six positive comparisons required')
    a=np.eye(4); k=0
    for i in range(4):
        for j in range(i+1,4): a[i,j]=v[k]; a[j,i]=1/v[k]; k+=1
    return a

def aggregate(matrices,authority):
    weights=np.asarray(authority,dtype=float)
    if (weights<0).any() or not np.isfinite(weights).all() or weights.sum()<=0 or len(matrices)!=len(weights): raise ValueError('invalid authority')
    for a in matrices: ahp(a)
    return np.exp(np.average(np.log(matrices),axis=0,weights=weights))
