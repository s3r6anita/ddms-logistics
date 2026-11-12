"""Authenticated Superset REST query and export, against actual local marts."""
import json,sqlite3
from pathlib import Path
from superset.app import create_app
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'reports/stages5_8').mkdir(parents=True,exist_ok=True)
app=create_app()
with app.app_context():
    from superset.extensions import db
    from superset.models.dashboard import Dashboard
    client=app.test_client();credentials=json.loads((Path(app.config['DATA_DIR'])/'admin.json').read_text())
    login=client.post('/api/v1/security/login',json={**credentials,'provider':'db','refresh':False});assert login.status_code==200
    headers={'Authorization':'Bearer '+login.json['access_token']}
    csrf=client.get('/api/v1/security/csrf_token/',headers=headers);assert csrf.status_code==200;headers['X-CSRFToken']=csrf.json['result']
    assert client.post('/login/',data={**credentials,'csrf_token':csrf.json['result']}).status_code==302
    dashboard=db.session.query(Dashboard).filter_by(slug='site-dss').one()
    with sqlite3.connect(ROOT/'data/processed/bi.sqlite') as conn:active=conn.execute('select run_id from selected_run').fetchone()[0]
    checks=[]
    for chart in sorted(dashboard.slices,key=lambda c:c.id):
        form=json.loads(chart.params)
        query=dict(columns=form.get('all_columns',[]),metrics=[],row_limit=10000,time_range='No filter',filters=[dict(col='run_id',op='==',val=active)],extras={'where':'','having':''},orderby=[])
        if chart.viz_type=='echarts_timeseries_line':query.update(granularity='month',is_timeseries=True,columns=['zone_id'],metrics=form['metrics'],extras=dict(time_grain_sqla='P1M',where='',having=''))
        from flask import g
        g.pop('user',None);g.pop('_login_user',None)
        payload=dict(datasource=dict(id=chart.datasource_id,type='table'),force=True,queries=[query],form_data=form,result_format='json',result_type='full')
        response=client.post('/api/v1/chart/data',headers=headers,json=payload)
        assert response.status_code==200,(chart.slice_name,response.get_data(as_text=True)[:1000])
        data=response.json['result'][0];assert data.get('status')!='failed' and not data.get('error'),data
        assert data['data'],chart.slice_name
        if chart.viz_type=='table':assert {r['run_id'] for r in data['data']}=={active}
        checks.append(dict(chart=chart.slice_name,status=response.status_code,rows=len(data['data']),run_id=active))
        # An invalid run filter must never leak rows from another run.
        query['filters']=[dict(col='run_id',op='==',val='nonexistent-run')]
        g.pop('user',None);g.pop('_login_user',None)
        rejected=client.post('/api/v1/chart/data',headers=headers,json=payload)
        assert rejected.status_code==200 and not rejected.json['result'][0]['data']
    exported=client.get('/api/v1/dashboard/export/?q='+json.dumps([dashboard.id]),headers=headers);assert exported.status_code==200
    (ROOT/'bi/superset_dashboard.zip').write_bytes(exported.data)
    (ROOT/'reports/stages5_8/superset_check.json').write_text(json.dumps(dict(engine='Apache Superset 4.1.4 authenticated Flask REST API',checks=checks,wrong_run_filter='empty for all charts',export_http_status=200),ensure_ascii=False,indent=2))
    print('Superset REST queries and ZIP export passed:',len(checks),'charts')
