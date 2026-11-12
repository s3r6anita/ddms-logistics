"""Chronological validation 24:36, calibration 36:48, held-out test 48:60."""
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from site_dss.data import digest
from site_dss.domain import ForecastPoint

def predict(y,method,h=12):
    y=np.asarray(y,dtype=float)
    if len(y)<24 or (y<0).any() or not np.isfinite(y).all(): raise ValueError('need >=24 finite nonnegative months')
    if method=='seasonal_naive': result=np.tile(y[-12:],int(np.ceil(h/12)))[:h]
    elif method=='ets':
        with warnings.catch_warnings(record=True) as caught:
            fitted=ExponentialSmoothing(y,trend='add',damped_trend=True,seasonal='add',seasonal_periods=12,initialization_method='estimated').fit(optimized=True)
        if any('converg' in str(w.message).lower() for w in caught): raise ValueError('ETS did not converge')
        result=fitted.forecast(h)
    else: raise ValueError('unknown forecast method')
    if not np.isfinite(result).all(): raise ValueError('nonfinite forecast')
    return np.maximum(result,0)

def metrics(actual,pred):
    a=np.asarray(actual);p=np.asarray(pred);den=float(a.sum());err=np.abs(a-p)
    peaks=np.argmax(a,axis=0) if a.ndim>1 else np.array([np.argmax(a)])
    peak=float(np.mean([err[peaks[j],j] for j in range(a.shape[1])])) if a.ndim>1 else float(err[peaks[0]])
    return dict(MAE=float(err.mean()),WAPE=float(err.sum()/den) if den else None,peak_MAE=peak)

def train(snapshot):
    df=pd.DataFrame([d.model_dump() for d in snapshot.demand])
    table=df.pivot(index='month',columns='zone_id',values='ordered_pallets').sort_index()
    if len(table)!=60 or table.isna().any().any(): raise ValueError('protocol requires exactly 60 aligned months')
    values=table.to_numpy();zones=list(table.columns); dates=list(table.index)
    prediction_cache={}
    def cached(cut,method,h,j):
        key=(values[:cut,j].tobytes(),method,h)
        if key not in prediction_cache:prediction_cache[key]=predict(values[:cut,j],method,h)
        return prediction_cache[key]
    def all_predict(cut,method,h=12):return np.column_stack([cached(cut,method,h,j) for j in range(len(zones))])
    validation={};failures={}
    for method in ['seasonal_naive','ets']:
        try:
            actual_folds=[];pred_folds=[]
            for cut in [24,27,30]:
                horizon=36-cut
                actual_folds.append(values[cut:36]);pred_folds.append(all_predict(cut,method,horizon))
            validation[method]=metrics(np.concatenate(actual_folds),np.concatenate(pred_folds))
        except ValueError as e:failures[method]=str(e)
    baseline=validation['seasonal_naive'];candidate=validation.get('ets')
    selected='ets' if candidate and baseline['WAPE'] is not None and candidate['WAPE']<=baseline['WAPE']*.95 and candidate['peak_MAE']<=baseline['peak_MAE']*1.05 else 'seasonal_naive'
    errors=values[36:48]-all_predict(36,selected)
    low95=np.minimum(0,np.quantile(errors,.025,axis=0));low80=np.minimum(0,np.quantile(errors,.1,axis=0))
    high80=np.maximum(0,np.quantile(errors,.9,axis=0));high95=np.maximum(0,np.quantile(errors,.975,axis=0))
    tests={m:metrics(values[48:60],all_predict(48,m)) for m in validation}
    test_pred=all_predict(48,selected);actual=values[48:60]
    for level,lo,hi in [('80',low80,high80),('95',low95,high95)]:
        lower=np.maximum(0,test_pred+lo);upper=test_pred+hi
        tests[selected]['coverage_'+level]=float(((actual>=lower)&(actual<=upper)).mean())
        tests[selected]['width_'+level]=float((upper-lower).mean())
    h=digest(snapshot.model_dump(mode='json')); final=all_predict(60,selected)
    future=pd.date_range(pd.Timestamp(dates[-1])+pd.offsets.MonthBegin(1),periods=12,freq='MS')
    points=[];test_rows=[]
    for j,z in enumerate(zones):
        for t in range(12):
            point=ForecastPoint(model_id=selected,zone_id=z,origin=snapshot.as_of,target_month=future[t].date(),point=final[t,j],p10=max(0,final[t,j]+low80[j]),p90=final[t,j]+high80[j],p025=max(0,final[t,j]+low95[j]),p975=final[t,j]+high95[j],training_cutoff=dates[-1],data_hash=h)
            points.append(point.model_dump(mode='json'))
            test_rows.append(dict(zone_id=z,month=str(dates[48+t]),actual=float(actual[t,j]),predicted=float(test_pred[t,j]),training_cutoff=str(dates[47])))
    report=dict(data_kind='synthetic' if snapshot.synthetic else 'real',selection=selected,validation=validation,test=tests,failures=failures,split=dict(validation_train_end=str(dates[23]),validation_origins=[str(dates[k-1]) for k in [24,27,30]],validation_target=[str(dates[24]),str(dates[35])],calibration_train_end=str(dates[35]),calibration_target=[str(dates[36]),str(dates[47])],test_train_end=str(dates[47]),test_target=[str(dates[48]),str(dates[59])]),calibration_months=12,interval_method='pooled signed calibration residuals per zone; quantiles expanded to contain point',limitations=['Только 12 калибровочных ошибок на зону; 95% покрытие не гарантировано','Три expanding validation origin с горизонтами 12/9/6; повторные целевые месяцы не независимы','Синтетический тренд и сезонность не подтверждают качество на рынке','Интервалы по объединенным горизонтам: недостаточно ошибок для отдельной калибровки каждого горизонта'])
    return dict(metrics=report,points=points,calibration_errors=errors.tolist(),zones=zones,test_rows=test_rows,data_hash=h)
