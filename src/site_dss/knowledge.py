from pathlib import Path
import json
from site_dss.data import digest

RULES=[
 dict(id='R01',field='prohibiting_condition',op='eq',value=True,status='excluded',reason='Подтвержденный запрет'),
 dict(id='R01b',field='legal_status',op='eq',value='rejected',status='excluded',reason='Правовая непригодность'),
 dict(id='R02',field='critical_unknown',op='eq',value=True,status='needs_confirmation',reason='Неизвестный или просроченный критический факт'),
 dict(id='R03',field='access_confirmed',op='eq',value=False,status='excluded',reason='Нет грузового доступа'),
 dict(id='R04',field='utilities_sufficient',op='eq',value=False,status='excluded',reason='Недостаточно инженерных мощностей'),
 dict(id='R05',field='capex_rub',op='gt_budget',status='excluded',reason='Превышен бюджет'),
 dict(id='R06',field='all_confirmed',op='eq',value=True,status='eligible_for_calculation',reason='Критические проверки пройдены'),
 dict(id='R07',field='success',op='lt_alpha',status='risk_rejected',reason='Риск выше допустимого'),
 dict(id='R08',field='synthetic',op='eq',value=True,status='demo_only',reason='Только учебный расчет'),
 dict(id='R09',field='expandable_fraction',op='eq',value=0,status='no_expansion',reason='Подтверждено отсутствие расширения'),
]

def infer(site,*,unknown=(),synthetic=False,budget=900e6,success=None,alpha=.9,power_required_kw=1000,rules=None):
    rules=RULES if rules is None else rules
    if len({r['id'] for r in rules})!=len(rules): raise ValueError('duplicate rule id')
    if (site.power_available_kw is not None and site.utilities_sufficient is True and site.power_available_kw<power_required_kw): raise ValueError('contradictory utility facts')
    facts=site.model_dump(); facts.update(critical_unknown=bool(unknown) or site.legal_status=='unknown' or any(getattr(site,k) is None for k in ['access_confirmed','utilities_sufficient','prohibiting_condition']),synthetic=synthetic,success=success)
    facts['all_confirmed']=not facts['critical_unknown'] and site.legal_status=='confirmed' and site.access_confirmed is True and site.utilities_sufficient is True and site.prohibiting_condition is False
    trace=[]; tags=set()
    for r in rules:
        value=facts.get(r['field']);op=r['op']
        match=(op=='eq' and value is not None and value==r.get('value')) or (op=='gt_budget' and value is not None and value>budget) or (op=='lt_alpha' and value is not None and value<alpha)
        if match:
            tags.add(r['status']); trace.append(dict(rule_id=r['id'],value=value,conclusion=r['status'],reason=r['reason'],evidence_ids=site.evidence_ids))
    status=next((s for s in ['excluded','needs_confirmation','risk_rejected','eligible_for_calculation'] if s in tags),'needs_confirmation')
    return dict(site_id=site.site_id,status=status,demo_only='demo_only' in tags,trace=trace,rules_hash=digest(rules))

def export_ontology(sites,path):
    from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, BNode
    g=Graph();ns=Namespace('https://example.org/site-dss#');g.bind('sd',ns)
    g.add((ns.Ontology,RDF.type,OWL.Ontology))
    for cls in ['Site','WarehouseDesign','DemandZone','RoadAccess','UtilityConnection','Restriction','Evidence','Scenario','DecisionRun','UnknownLegalSite','NeedsConfirmationSite']:
        g.add((ns[cls],RDF.type,OWL.Class))
    g.add((ns.UnknownLegalSite,RDFS.subClassOf,ns.Site));g.add((ns.UnknownLegalSite,RDFS.subClassOf,ns.NeedsConfirmationSite))
    for prop in ['hasEvidence','hasAccess','hasConnection','intersectsRestriction','servesZone']:
        g.add((ns[prop],RDF.type,OWL.ObjectProperty))
    for site in sites:
        node=ns['site_'+site.site_id];g.add((node,RDF.type,ns.Site));g.add((node,RDFS.label,Literal(site.name)))
        if site.legal_status=='unknown':g.add((node,RDF.type,ns.UnknownLegalSite))
        for evidence in site.evidence_ids:
            e=ns['evidence_'+evidence];g.add((e,RDF.type,ns.Evidence));g.add((node,ns.hasEvidence,e))
    Path(path).parent.mkdir(parents=True,exist_ok=True);g.serialize(path,format='xml')
    return len(g)
