"""Интерфейс локального сайта DSS; у модуля вычислений нет зависимости Streamlit."""
import json,os
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from site_dss.domain import DecisionRequest,DecisionRun
from site_dss.recommendation import recommend
from site_dss.data import digest
from site_dss.export import html_report
from site_dss.bi import export_bi

RUN_ROOT=Path(os.environ.get('SITE_DSS_REPORT_ROOT','reports/runs'))


def format_millions(value):
    return f'{round(value,2) or 0:,.2f}'.replace(',','\u202f').replace('.',',')


def clear_cost_selection():
    key=st.session_state.get('cost_selection_key')
    if key:
        st.session_state[key]={'selection':{'cells':[]}}


@st.dialog('Состав затрат',width='small',on_dismiss=clear_cost_selection)
def show_cost_breakdown(site,request):
    st.markdown(f'**Площадка {site.site_id}**')
    validation=site.validation or {}
    breakdown=validation.get('expected_breakdown')
    if not breakdown:
        st.info('Затраты для этой площадки не рассчитаны.')
        st.write('; '.join(site.diagnostics) or 'Детализация отсутствует в сохраненном расчете.')
    else:
        entries=[
            ('Первоначальные вложения (CAPEX)',breakdown['capex_rub']),
            ('Эксплуатация',breakdown['operating_pv_rub']),
            ('Перевозки',breakdown['transport_pv_rub']),
            ('Потери из-за необслуженного спроса',breakdown['unserved_loss_pv_rub']),
            ('Ожидание запуска',breakdown['waiting_rub']),
            ('Остаточная стоимость (вычитается)',-breakdown['residual_pv_rub']),
            ('Итого',validation['expected_cost_rub'])]
        costs=pd.DataFrame(entries,columns=['Статья','млн ₽'])
        costs['млн ₽']=costs['млн ₽']/1e6
        st.table(costs.style.format({'млн ₽':format_millions}).hide(axis='index'))
        st.caption(f'Ожидаемые затраты по проверочным сценариям за {request.horizon_years} лет эксплуатации. '
                   f'Будущие расходы приведены к моменту инвестиционного решения; ставка {request.discount_rate:.0%}. '
                   'Итог рассчитан до округления статей.')
        st.info(f'Бюджет CAPEX: {format_millions(request.budget_rub/1e6)} млн ₽. '
                'Он ограничивает первоначальные вложения. Итог также включает эксплуатацию и другие статьи.')
    if st.button('Закрыть',on_click=clear_cost_selection,key='close_cost_breakdown'):
        st.rerun()


st.set_page_config(page_title='Site DSS · выбор площадки',page_icon='📍',layout='wide')
st.markdown('<style>.block-container{padding-top:2rem}h1{letter-spacing:-.04em}div[data-testid="stMetric"]{background:#f3f6fa;padding:1rem;border-radius:12px}div[data-testid="stMetric"] *{color:#243448!important}</style>',unsafe_allow_html=True)
st.title('Выбор площадки склада')
st.write('Сравните стоимость, сервис и запас мощности. Проверьте, при каких условиях рекомендация сохраняется.')
st.warning('Учебный режим: площадки, история спроса, документы и грузовые маршруты синтетические. Координаты показаны на условной схеме.')
with st.sidebar:
    st.header('Условия решения')
    with st.form('decision'):
        budget=st.number_input('Бюджет CAPEX, млн ₽',min_value=1.,max_value=5000.,value=900.,step=50.)
        scale=st.number_input('Множитель спроса',min_value=.1,max_value=5.,value=1.,step=.05)
        alpha=st.slider('Совместная успешность',min_value=.5,max_value=1.,value=.9,step=.01)
        sla=st.slider('Доля спроса в пределах времени доставки',min_value=.5,max_value=1.,value=.9,step=.01)
        minutes=st.number_input('Доставка, мин.',min_value=1.,max_value=600.,value=120.,step=10.)
        launch=st.number_input('Предельный запуск, мес.',min_value=1.,max_value=60.,value=18.)
        conservative=st.checkbox('Принимать по нижней границе Уилсона',value=True)
        st.subheader('Предпочтения AHP')
        st.caption('K — затраты, L — сервис, T — срок, G — расширение. Сравнение >1 означает приоритет первого критерия.')
        comparisons=[st.number_input(label,min_value=1/9,max_value=9.,value=float(value),step=.1,key='cmp_'+str(i)) for i,(label,value) in enumerate(zip(['K / L','K / T','K / G','L / T','L / G','T / G'],[4/3,2,4,1.5,3,2]))]
        allow=st.checkbox('Разрешаю расчет на моковых данных',value=True)
        submit=st.form_submit_button('Рассчитать рекомендацию',type='primary')
request=DecisionRequest(budget_rub=budget*1e6,demand_scale=scale,alpha=alpha,sla_target=sla,max_delivery_minutes=minutes,max_launch_months=launch,risk_policy='wilson_lower' if conservative else 'point',comparisons=comparisons,allow_demo=allow)
if 'run' not in st.session_state:
    files=sorted(RUN_ROOT.glob('*/run.json'),key=lambda p:p.stat().st_mtime)
    if files:
        st.session_state.run=DecisionRun.model_validate_json(files[-1].read_text())
if submit:
    bar=st.progress(0.,text='Подготовка расчета')
    try:
        result,folder=recommend(request=request.model_dump(),output_root=RUN_ROOT,progress=lambda text,value:bar.progress(value,text=text))
        st.session_state.run=result;st.session_state.run_folder=str(folder)
    except (ValueError,RuntimeError) as e:st.error(str(e))
    finally:bar.empty()
run=st.session_state.get('run')
if run is None:
    st.info('Задайте условия слева и начните расчет. Для каждого отказа система покажет причину.')
    st.stop()
st.caption(f'Сохраненный расчет: {run.run_id} · версия {run.version} · {run.elapsed_seconds:.1f} с')
if digest(request.model_dump())!=digest(run.request.model_dump()):st.info('Параметры отличаются от сохраненного расчета. Нажмите «Рассчитать рекомендацию», чтобы применить изменения.')
if run.recommendation:
    best=next(s for s in run.sites if s.site_id==run.recommendation)
    st.success(run.explanation['summary'])
    cols=st.columns(4)
    cols[0].metric('Площадка',best.site_id)
    cols[1].metric('Приведенные затраты, млн ₽',f"{best.validation['expected_cost_rub']/1e6:,.1f}")
    cols[2].metric('Совместная успешность',f"{best.validation['success_rate']:.1%}")
    cols[3].metric('Баллы предпочтений',f'{best.score:.4f}')
    st.caption('Предварительная рекомендация в рамках заданной модели. Стресс-проверки ниже могут выявить дополнительные нарушения.')
else:
    st.error(run.explanation['summary'])
    st.write('Изучите причины отказов. Снижение нагрузки или иное изменение условий проверяется новым расчетом.')
rows=[]
labels={'eligible':'Допущена','excluded':'Исключена','needs_confirmation':'Нужно подтверждение','risk_rejected':'Не проходит риск','solver_unresolved':'Расчет не завершен'}
for s in run.sites:
    v=s.validation or {}
    rows.append({'Площадка':s.site_id,'Статус':labels.get(s.status,s.status),'U':s.score,'Затраты, млн ₽':v.get('expected_cost_rub',0)/1e6 if v else None,'Успешность':v.get('success_rate'),'Нижняя граница':v.get('wilson95',[None])[0],'SLA':v.get('expected_sla'),'Причина':'; '.join(s.diagnostics)})
tabs=st.tabs(['Сравнение','Схема площадок','Прогноз','Риски','Обоснование и источники'])
with tabs[0]:
    st.caption('Нажмите ячейку в столбце «Затраты, млн ₽», чтобы увидеть состав затрат.')
    comparison_key='site_comparison_'+run.run_id
    st.session_state.cost_selection_key=comparison_key
    selection=st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch',key=comparison_key,on_select='rerun',selection_mode='single-cell',column_config={'U':st.column_config.NumberColumn(format='%.4f'),'Затраты, млн ₽':st.column_config.NumberColumn(format='%.2f',help='Нажмите сумму, чтобы увидеть состав затрат.'),'Успешность':st.column_config.NumberColumn(format='percent'),'Нижняя граница':st.column_config.NumberColumn(format='percent'),'SLA':st.column_config.NumberColumn(format='percent')})
    if selection.selection.cells:
        row,column=selection.selection.cells[0]
        if column=='Затраты, млн ₽':
            site_id=rows[row]['Площадка']
            show_cost_breakdown(next(s for s in run.sites if s.site_id==site_id),run.request)
    scores=[s for s in run.sites if s.utilities is not None]
    fig=go.Figure()
    weights=run.explanation.get('weights')
    if weights is None:
        from site_dss.ahp import ahp,pairwise
        weights=ahp(pairwise(run.request.comparisons))['weights']
    for j,label in enumerate(['Затраты','Сервис','Запуск','Расширение']):
        fig.add_bar(name=label,x=[s.site_id for s in scores],y=[s.utilities[j]*weights[j] for s in scores])
    fig.update_layout(barmode='stack',title='Вклады критериев в балл · до фильтра риска',height=350,legend_orientation='h')
    st.plotly_chart(fig,width='stretch')
with tabs[1]:
    st.subheader('Условная пространственная схема')
    st.warning('Это условная схема моковых площадок, а не карта реальных участков. Метки статуса показывают результат расчета; расположение не подтверждает транспортную доступность.')
    snapshot=json.loads((RUN_ROOT/run.run_id/'snapshot.json').read_text())
    fig=go.Figure()
    for site in snapshot['sites']:
        xy=site['geometry']['coordinates'][0];status=next(s.status for s in run.sites if s.site_id==site['site_id'])
        color='#15846b' if status=='eligible' else '#d49a35' if status=='needs_confirmation' else '#a2acb8'
        fig.add_trace(go.Scatter(x=[p[0]*111.32 for p in xy],y=[p[1]*110.57 for p in xy],fill='toself',mode='lines',line_color=color,name=site['site_id']+' · '+labels.get(status,status)))
    fig.update_layout(xaxis_title='Условная ось X, км',yaxis_title='Условная ось Y, км',height=360,yaxis_scaleanchor='x')
    st.plotly_chart(fig,width='stretch')
with tabs[2]:
    fc=run.forecast;zone=st.selectbox('Зона спроса',fc['zones'])
    history=[d for d in snapshot['demand'] if d['zone_id']==zone]
    points=[p for p in fc['points'] if p['zone_id']==zone]
    fig=go.Figure()
    fig.add_scatter(x=[d['month'] for d in history],y=[d['ordered_pallets'] for d in history],name='История (мок)',line_color='#79899d')
    fig.add_scatter(x=[p['target_month'] for p in points],y=[p['p90'] for p in points],name='Верхняя 80%',line_width=0)
    fig.add_scatter(x=[p['target_month'] for p in points],y=[p['p10'] for p in points],name='Интервал 80%',fill='tonexty',line_width=0,fillcolor='rgba(44,105,193,.18)')
    fig.add_scatter(x=[p['target_month'] for p in points],y=[p['point'] for p in points],name='Прогноз',line_color='#2c69c1')
    fig.update_layout(height=370,yaxis_title='Паллет / месяц');st.plotly_chart(fig,width='stretch')
    st.warning('Интервалы недопокрывают тест. Не трактуйте их как гарантию достаточности мощности.')
    st.json(fc['metrics'])
with tabs[3]:
    data=pd.DataFrame([dict(Площадка=r['site_id'],Затраты=r['cost_rub']/1e6,Выборка=r['sample']) for r in run.scenario_metrics])
    if not data.empty:st.plotly_chart(px.box(data[data['Выборка']=='validation'],x='Площадка',y='Затраты',title='Проверочные сценарии: приведенные затраты, млн ₽'),width='stretch')
    st.write('Один сценарий успешен, только если все месяцы пяти лет удовлетворяют ограничениям. Доля своевременного спроса считается от всего спроса.')
    st.dataframe(pd.DataFrame([dict(Площадка=s.site_id,CVaR90=s.validation['cvar90_rub']/1e6,**s.validation['failures']) for s in run.sites if s.validation]),hide_index=True)
    from site_dss.decision_tree import tree_svg
    st.image(tree_svg(run.decision_tree))
    st.subheader('Стрессы вне вероятностной выборки')
    st.dataframe(pd.DataFrame([dict(Площадка=r['site_id'],Стресс=r['stress'],Успех=r['success'],Нарушения=', '.join(r['violations'])) for r in run.stresses]),hide_index=True)
with tabs[4]:
    st.json(run.explanation)
    st.line_chart(pd.DataFrame([dict(Вес_затрат=r['cost_weight'],**r['scores']) for r in run.sensitivity]).set_index('Вес_затрат'))
    for site in run.sites:
        with st.expander('Площадка '+site.site_id+' · основания статуса'):st.json(site.knowledge)
    with st.expander('Версии и происхождение'):st.json(run.provenance)
cols=st.columns(3)
cols[0].download_button('Скачать JSON',data=run.model_dump_json(indent=2),file_name=run.run_id+'.json',mime='application/json')
cols[1].download_button('Скачать HTML',data=html_report(run),file_name=run.run_id+'.html',mime='text/html')
if cols[2].button('Передать этот расчет в BI'):
    export_bi(run);st.success('BI-витрины переключены на '+run.run_id)
st.link_button('Открыть локальный Superset','http://127.0.0.1:8089/superset/dashboard/site-dss/')
