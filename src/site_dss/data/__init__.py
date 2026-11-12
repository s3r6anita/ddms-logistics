"""Strict import, spatial checks and immutable source snapshots."""
import csv, hashlib, json
from pathlib import Path
from shapely.geometry import shape
from pyproj import Geod
from pydantic import TypeAdapter
from site_dss.domain import Snapshot, DemandObservation, Site

def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def write_json(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def load_snapshot(path, *, allow_demo=False):
    raw=json.loads(Path(path).read_text())
    s=Snapshot.model_validate(raw)
    ids=[e.source_id for e in s.evidence]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate evidence')
    sources={e.source_id:e for e in s.evidence}
    has_demo=any(e.source_kind=='synthetic' for e in s.evidence)
    if has_demo and not s.synthetic: raise ValueError('synthetic evidence mislabeled')
    if (s.synthetic or has_demo) and not allow_demo: raise ValueError('demo requires allow_demo')
    for e in s.evidence:
        if e.observed_at>s.as_of: raise ValueError('future evidence')
    projects={x.project_id for x in s.designs}
    if len(projects)!=len(s.designs) or len(set(s.zones))!=len(s.zones): raise ValueError('duplicate design/zone')
    seen=set(); missing={}; areas={}
    for site in s.sites:
        if site.site_id in seen: raise ValueError('duplicate site')
        seen.add(site.site_id)
        if site.project_id not in projects: raise ValueError('unknown project')
        for key in site.evidence_ids:
            if key not in sources: raise ValueError('unknown evidence')
        if not site.evidence_ids: raise ValueError('missing provenance')
        design=next(d for d in s.designs if d.project_id==site.project_id)
        if site.utilities_sufficient is True and site.power_available_kw is not None and site.power_available_kw<design.power_required_kw: raise ValueError('contradictory power facts')
        g=site.geometry; area=abs(Geod(ellps='WGS84').geometry_area_perimeter(shape(g))[0])
        if abs(area-site.document_area_m2)/site.document_area_m2>.1: raise ValueError('area differs >10%')
        areas[site.site_id]=area
        problems=[]
        if site.legal_status=='unknown': problems.append('legal_status')
        for k in ['access_confirmed','utilities_sufficient','prohibiting_condition','expandable_fraction']:
            if getattr(site,k) is None: problems.append(k)
        for key in site.evidence_ids:
            if sources[key].valid_until<s.as_of or sources[key].quality_status!='confirmed': problems.append('evidence:'+key)
        missing[site.site_id]=problems
    def unique(rows,key):
        keys=[key(x) for x in rows]
        if len(keys)!=len(set(keys)): raise ValueError('duplicate record')
    unique(s.demand,lambda d:(d.zone_id,d.month))
    unique(s.routes,lambda r:(r.site_id,r.zone_id,r.period,r.vehicle_profile))
    for row in [*s.demand,*s.routes,*s.costs]:
        if row.evidence_id not in sources: raise ValueError('unknown evidence')
        if hasattr(row,'zone_id') and row.zone_id not in s.zones: raise ValueError('unknown zone')
        if hasattr(row,'site_id') and row.site_id not in seen: raise ValueError('unknown site')
    for d in s.demand:
        if d.month>s.as_of: raise ValueError('future demand')
        if sources[d.evidence_id].unit!='pallet': raise ValueError('demand evidence unit mismatch')
    for c in s.costs:
        if c.price_date>s.as_of: raise ValueError('future price')
        if sources[c.evidence_id].unit!='RUB': raise ValueError('cost evidence unit mismatch')
    for zone in s.zones:
        months=sorted(d.month.year*12+d.month.month for d in s.demand if d.zone_id==zone)
        if not months or months!=list(range(months[0],months[-1]+1)): raise ValueError('irregular demand')
    required={(i,z,p) for i in seen for z in s.zones for p in ['peak','offpeak']}
    if {(r.site_id,r.zone_id,r.period) for r in s.routes}!=required: raise ValueError('incomplete route matrix')
    for r in s.routes:
        e=sources[r.evidence_id]
        if e.unit!='minute': raise ValueError('route evidence unit mismatch')
        if r.reachable is None or e.valid_until<s.as_of or e.quality_status!='confirmed':
            missing[r.site_id].append('route:'+r.zone_id+':'+r.period)
    for site in s.sites:
        capex=sum(c.amount for c in s.costs if c.site_id==site.site_id and c.category=='capex_total' and c.scenario_id=='base')
        if abs(capex-site.capex_rub)>1e-6: raise ValueError('CAPEX mismatch')
    return s,dict(data_kind='synthetic' if s.synthetic else 'real',sites=len(s.sites),demand_rows=len(s.demand),route_rows=len(s.routes),missing_critical=missing,areas_m2=areas)

def import_demand_csv(path):
    with open(path,newline='') as f: return TypeAdapter(list[DemandObservation]).validate_python(list(csv.DictReader(f)))

def import_sites_geojson(path):
    raw=json.loads(Path(path).read_text())
    if raw.get('type')!='FeatureCollection': raise ValueError('expected FeatureCollection')
    return [Site.model_validate({**f['properties'],'geometry':f['geometry']}) for f in raw['features']]

def save_snapshot(snapshot, directory):
    raw=snapshot.model_dump(mode='json'); h=digest(raw); folder=Path(directory)/h
    folder.mkdir(parents=True,exist_ok=True)
    p=folder/'snapshot.json'
    if p.exists() and json.loads(p.read_text())!=raw: raise ValueError('snapshot collision')
    write_json(p,raw)
    write_json(folder/'manifest.json',{'sha256':h,'schema_version':snapshot.schema_version,'as_of':str(snapshot.as_of),'synthetic':snapshot.synthetic})
    return h
