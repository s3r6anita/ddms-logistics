from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope='module')
def cost_run(tmp_path_factory):
    from site_dss.recommendation import recommend
    root=tmp_path_factory.mktemp('cost-popup')
    run,_=recommend(request=dict(allow_demo=True,demand_scale=.75,planning_scenarios=10,validation_scenarios=100),output_root=root)
    return root,run


def select_comparison_cell(at,run,site_id,column='Затраты, млн ₽'):
    index=next(i for i,site in enumerate(run.sites) if site.site_id==site_id)
    at.session_state['site_comparison_'+run.run_id]={'selection':{'cells':[[index,column]]}}
    return at.run()


def test_cost_popup_matches_saved_result_and_reopens(monkeypatch,cost_run):
    root,run=cost_run
    monkeypatch.setenv('SITE_DSS_REPORT_ROOT',str(root))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py').run()
    select_comparison_cell(at,run,'B')
    assert not at.exception
    costs=at.table[0].value.set_index('Статья')['млн ₽']
    validation=next(s.validation for s in run.sites if s.site_id=='B')
    assert costs['Первоначальные вложения (CAPEX)']==pytest.approx(validation['expected_breakdown']['capex_rub']/1e6)
    assert costs['Итого']==pytest.approx(validation['expected_cost_rub']/1e6)
    assert costs.drop('Итого').sum()==pytest.approx(costs['Итого'])
    assert any('Бюджет CAPEX: 900,00' in text.value for text in at.info)
    at.button(key='close_cost_breakdown').click().run()
    assert not at.exception and not at.table
    assert not at.session_state['site_comparison_'+run.run_id]['selection']['cells']
    select_comparison_cell(at,run,'B')
    assert not at.exception and len(at.table)==1
    at.button(key='close_cost_breakdown').click().run()
    select_comparison_cell(at,run,'A')
    assert not at.exception
    other=next(s.validation for s in run.sites if s.site_id=='A')
    assert at.table[0].value.iloc[-1]['млн ₽']==pytest.approx(other['expected_cost_rub']/1e6)


def test_uncalculated_site_has_no_invented_costs(monkeypatch,cost_run):
    root,run=cost_run
    monkeypatch.setenv('SITE_DSS_REPORT_ROOT',str(root))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py').run()
    select_comparison_cell(at,run,'C')
    assert not at.exception and not at.table
    assert any('Затраты для этой площадки не рассчитаны.'==text.value for text in at.info)
    assert any('Превышен бюджет' in text.value for text in at.markdown)


def test_other_columns_do_not_open_cost_popup(monkeypatch,cost_run):
    root,run=cost_run
    monkeypatch.setenv('SITE_DSS_REPORT_ROOT',str(root))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py').run()
    select_comparison_cell(at,run,'B','Статус')
    assert not at.exception and not at.table
    assert not any(button.key=='close_cost_breakdown' for button in at.button)

def test_form_and_saved_run(monkeypatch,tmp_path):
    monkeypatch.setenv("SITE_DSS_REPORT_ROOT",str(tmp_path))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py',default_timeout=60).run();assert not at.exception
    assert at.title[0].value=='Выбор площадки склада'
    # Run an impossible budget; no heavy scenario solves are needed.
    next(x for x in at.number_input if x.label=='Бюджет CAPEX, млн ₽').set_value(1.)
    next(b for b in at.button if b.label=='Рассчитать рекомендацию').click().run(timeout=60)
    assert not at.exception
    assert any('не найдено' in e.value for e in at.error)
    assert at.session_state['run'].recommendation is None
    next(x for x in at.number_input if x.label=='K / L').set_value(9.)
    next(x for x in at.number_input if x.label=='K / T').set_value(1/9)
    next(x for x in at.number_input if x.label=='L / T').set_value(9.)
    next(b for b in at.button if b.label=='Рассчитать рекомендацию').click().run(timeout=60)
    assert not at.exception and any('inconsistent' in e.value for e in at.error)
