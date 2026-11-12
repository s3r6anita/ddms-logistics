import json
from pathlib import Path
from superset.app import create_app
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'reports/stages5_8').mkdir(parents=True,exist_ok=True)
app=create_app()
with app.app_context():
    from superset.extensions import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
    credentials=json.loads((Path(app.config['DATA_DIR'])/'admin.json').read_text());security=app.appbuilder.sm
    admin=security.find_user(username=credentials['username'])
    if admin is None:admin=security.add_user(credentials['username'],'Local','Reviewer','reviewer@example.invalid',security.find_role('Admin'),credentials['password'])
    database=db.session.query(Database).filter_by(database_name='Site DSS').one_or_none()
    if database is None:
        database=Database(database_name='Site DSS',sqlalchemy_uri='sqlite:///'+str(ROOT/'data/processed/bi.sqlite'));db.session.add(database);db.session.flush()
    definitions=[
      ('Сравнение площадок','run_sites',['run_id','site_id','status','score','expected_cost_million','success_rate','wilson_lower','sla','solver_status']),
      ('Сценарии затрат и нарушений','scenario_metrics',['run_id','site_id','sample','scenario_id','cost_million','success','unserved_pallets']),
      ('Прогноз спроса','forecast_points',['run_id','zone_id','month','point','p10','p90']),
      ('Качество прогноза','forecast_quality',['run_id','model','mae','wape','coverage80','coverage95']),
      ('Объяснение правил','rule_trace',['run_id','site_id','rule_id','conclusion','reason'])]
    charts=[];tables=[]
    for title,name,columns in definitions:
        name='active_'+name
        table=db.session.query(SqlaTable).filter_by(table_name=name,database_id=database.id).one_or_none()
        if table is None:table=SqlaTable(table_name=name,database=database);db.session.add(table);db.session.flush()
        table.fetch_metadata();tables.append(table)
        chart=db.session.query(Slice).filter_by(slice_name=title).one_or_none()
        if chart is None:chart=Slice(slice_name=title,owners=[admin]);db.session.add(chart)
        chart.datasource_id,chart.datasource_type,chart.viz_type=table.id,'table','table'
        chart.params=json.dumps(dict(viz_type='table',datasource=f'{table.id}__table',time_range='No filter',row_limit=10000,query_mode='raw',all_columns=columns,adhoc_filters=[]),ensure_ascii=False);charts.append(chart)
    table=tables[2]
    for column in table.columns:
        if column.column_name=='month':column.is_dttm=True
    line=db.session.query(Slice).filter_by(slice_name='Динамика прогнозного спроса').one_or_none()
    if line is None:line=Slice(slice_name='Динамика прогнозного спроса',owners=[admin]);db.session.add(line)
    line.datasource_id,line.datasource_type,line.viz_type=table.id,'table','echarts_timeseries_line'
    line.params=json.dumps(dict(viz_type=line.viz_type,datasource=f'{table.id}__table',time_range='No filter',row_limit=1000,x_axis='month',granularity_sqla='month',time_grain_sqla='P1M',groupby=['zone_id'],metrics=[dict(expressionType='SQL',sqlExpression='AVG(point)',label='Паллеты')],adhoc_filters=[],show_legend=True))
    charts.append(line)
    db.session.flush()
    dashboard=db.session.query(Dashboard).filter_by(slug='site-dss').one_or_none()
    if dashboard is None:dashboard=Dashboard(dashboard_title='СППР площадки — synthetic demo',slug='site-dss',owners=[admin]);db.session.add(dashboard)
    dashboard.slices=charts;dashboard.published=True
    position={'DASHBOARD_VERSION_KEY':'v2','ROOT_ID':{'id':'ROOT_ID','type':'ROOT','children':['GRID_ID']},'GRID_ID':{'id':'GRID_ID','type':'GRID','parents':['ROOT_ID'],'children':[]}}
    for k,c in enumerate(charts):
        row=f'ROW-{k}';cid=f'CHART-{c.id}';position['GRID_ID']['children'].append(row)
        position[row]=dict(id=row,type='ROW',parents=['ROOT_ID','GRID_ID'],children=[cid],meta={'background':'BACKGROUND_TRANSPARENT'})
        position[cid]=dict(id=cid,type='CHART',parents=['ROOT_ID','GRID_ID',row],children=[],meta=dict(chartId=c.id,width=12,height=45,sliceName=c.slice_name))
    dashboard.position_json=json.dumps(position)
    dashboard.json_metadata=json.dumps(dict(refresh_frequency=0,native_filter_configuration=[dict(id='NATIVE_FILTER-run',name='Расчет (run_id)',filterType='filter_select',targets=[dict(datasetId=t.id,column=dict(name='run_id')) for t in tables],defaultDataMask=dict(extraFormData={},filterState={},ownState={}),scope=dict(rootPath=['ROOT_ID'],excluded=[]),controlValues=dict(enableEmptyFilter=False,multiSelect=False,searchAllOptions=False,inverseSelection=False),cascadeParentIds=[],type='NATIVE_FILTER')]))
    db.session.commit()
    report=dict(path='/superset/dashboard/site-dss/',dashboard_id=dashboard.id,charts=[dict(id=c.id,table=c.datasource.table_name,title=c.slice_name) for c in charts],run_policy='active_* views join the single selected_run, all charts share one run_id')
    (ROOT/'reports/stages5_8/superset_dashboard.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(report['path'])
