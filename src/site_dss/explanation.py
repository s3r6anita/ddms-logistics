from site_dss.utility import compare,cost_weight_switch

def explain(sites,winner,weights):
    if not winner:
        return dict(summary='Площадки, удовлетворяющей всем условиям, не найдено.',reasons={s.site_id:s.diagnostics or [s.status] for s in sites},next_steps=['Изучите причины отказа и сценарные нарушения.','Изменения бюджета, мощности или требований проверяются отдельным расчетом.'])
    chosen=next(s for s in sites if s.site_id==winner)
    comparisons=[]
    for other in sites:
        if other.site_id!=winner and other.score is not None:
            delta=compare(other.utilities,chosen.utilities,weights)
            comparisons.append(dict(other=other.site_id,status=other.status,**delta,cost_weight_switch=cost_weight_switch(other.utilities,chosen.utilities)))
    return dict(summary=f'Предварительная рекомендация: площадка {winner}.',weights=weights,comparisons=comparisons,weaknesses=['Все исходные данные синтетические; рекомендация учебная.','Модельные вероятности не подтверждены статистикой рынка.','Прогнозные интервалы недопокрывают тест; это ограничение исходной модели.'],conditions='Результат действителен только для сохраненных данных, бюджета, требований и сценарных допущений.')
