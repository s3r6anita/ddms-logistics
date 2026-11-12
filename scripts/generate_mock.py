"""Generate synthetic JSON/CSV/GeoJSON, never real candidate coordinates."""
import csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from pyproj import Geod
from shapely.geometry import shape
from site_dss.data import write_json
ROOT=Path(__file__).resolve().parents[1]
def main():
    rng=np.random.default_rng(42); evidence=[]
    for key,unit in [('site','mixed'),('demand','pallet'),('route','minute'),('cost','RUB')]:
        evidence.append(dict(source_id=key,source_kind='synthetic',observed_at='2026-11-01',valid_until='2027-02-01',unit=unit,quality_status='confirmed',evidence_uri='mock://site-dss/v1/'+key,confirmed_by='mock-generator'))
    sites=[]
    for k,(i,cap,months,expansion) in enumerate(zip('ABCDE',[650,740,950,620,780],[14,12,12,16,15],[.2,.4,.3,.1,.25])):
        # Near (0,0): deliberately fictional polygons, never a real-region map layer.
        x=.01*k; geom=dict(type='Polygon',coordinates=[[[x,0],[x+.002,0],[x+.002,.002],[x,.002],[x,0]]])
        area=abs(Geod(ellps='WGS84').geometry_area_perimeter(shape(geom))[0])
        sites.append(dict(site_id=i,name='Условная площадка '+i,geometry=geom,crs='EPSG:4326',legal_status='unknown' if i=='D' else 'confirmed',project_id=i,evidence_ids=['site'],capex_rub=cap*1e6,launch_months=months,expandable_fraction=expansion,access_confirmed=True,utilities_sufficient=True,prohibiting_condition=False,power_available_kw=1500,document_area_m2=area))
    designs=[dict(project_id=i,storage_pallets=20000,throughput_pallets_month=[q/12]*12,power_required_kw=1000) for i,q in zip('ABCDE',[160000,190000,200000,180000,180000])]
    demand=[]; common=rng.normal(0,90,60)
    for z,base in [('Z1',4000),('Z2',3500),('Z3',2500)]:
        for t in range(60):
            year=2021+(t+10)//12; month=(t+10)%12+1
            total=round(max(0,base*(1+.15*np.sin(2*np.pi*t/12))+t*7+common[t]+rng.normal(0,45)),2)
            unfilled=round(total*.02,2)
            demand.append(dict(zone_id=z,month=f'{year}-{month:02d}-01',ordered_pallets=total,shipped_pallets=round(total-unfilled,2),unfulfilled_pallets=unfilled,evidence_id='demand',unit='pallet'))
    routes=[dict(site_id=i,zone_id=z,period=p,vehicle_profile='truck_20t',reachable=True,minutes=45+k*9+j*10+(25 if p=='peak' else 0),km=30+k*5+j*7,variable_cost_rub_pallet=200+k*10+j*15,evidence_id='route') for k,i in enumerate('ABCDE') for j,z in enumerate(['Z1','Z2','Z3']) for p in ['peak','offpeak']]
    costs=[dict(site_id=s['site_id'],category='capex_total',cashflow_date='2026-11-01',amount=s['capex_rub'],currency='RUB',price_date='2026-11-01',vat_policy='excluded',real_or_nominal='real',scenario_id='base',evidence_id='cost') for s in sites]
    raw=dict(schema_version='1.0',as_of='2026-11-12',synthetic=True,evidence=evidence,designs=designs,sites=sites,zones=['Z1','Z2','Z3'],demand=demand,routes=routes,costs=costs)
    out=ROOT/'data/mock';out.mkdir(exist_ok=True)
    write_json(out/'snapshot.json',raw)
    write_json(out/'sites.geojson',dict(type='FeatureCollection',features=[dict(type='Feature',geometry=s['geometry'],properties={k:v for k,v in s.items() if k!='geometry'}) for s in sites]))
    with (out/'demand.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(demand[0]));w.writeheader();w.writerows(demand)
    write_json(out/'README.json',dict(synthetic=True,seed=42,reason='Нет региона, документов, грузовой матрицы и ERP-истории заказчика. Открытая карта не заменяет эти сведения.',coordinates='Условные полигоны около (0,0); не показывать на реальной карте',history='2021-11..2026-10; 60 месяцев, 3 зоны; тренд+сезонность+общий шум; известный процесс, не рыночные наблюдения'))
if __name__=='__main__':main()
