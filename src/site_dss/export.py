from html import escape
import json

def html_report(run):
    rows=[]
    for s in run.sites:
        v=s.validation or {}
        rows.append('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in [s.site_id,s.status,round(s.score,4) if s.score is not None else '—',round(v.get('expected_cost_rub',0)/1e6,2) if v else '—',f"{v['success_rate']:.1%}" if v else '—','; '.join(s.diagnostics)])+'</tr>')
    return '''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Site DSS</title>
<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;color:#243448}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap}.warning{background:#fff0ce;padding:16px}</style>
<h1>Выбор площадки склада</h1>'''+f'<p>Расчет {escape(run.run_id)}</p><p class="warning">'+('Синтетические данные. Учебная рекомендация. ' if run.synthetic else '')+'Модельные вероятности и недопокрытие прогнозных интервалов ограничивают применимость.</p>'+f'<h2>{escape(run.explanation["summary"])}</h2><table><tr><th>Площадка</th><th>Статус</th><th>U</th><th>Затраты, млн ₽</th><th>Успешность</th><th>Причина</th></tr>'+''.join(rows)+'</table><h2>Обоснование</h2><pre>'+escape(json.dumps(run.explanation,ensure_ascii=False,indent=2))+'</pre><h2>Параметры</h2><pre>'+escape(json.dumps(run.request.model_dump(),ensure_ascii=False,indent=2))+'</pre><h2>Ограничения прогноза</h2><pre>'+escape(json.dumps(run.forecast['metrics'],ensure_ascii=False,indent=2))+'</pre></html>'
