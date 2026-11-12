import argparse,json,hashlib,platform
import importlib.metadata
from pathlib import Path
from site_dss.data import load_snapshot,save_snapshot,write_json
from site_dss.ahp import ahp,pairwise
from site_dss.utility import utilities,compare,cost_weight_switch
from site_dss.knowledge import infer,export_ontology,RULES
from site_dss.forecast import train
from site_dss.scenarios import build_scenarios

def run(path,out,allow_demo):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    snapshot,quality=load_snapshot(path,allow_demo=allow_demo)
    h=save_snapshot(snapshot,out/'snapshots');write_json(out/'quality.json',quality)
    results=[infer(s,unknown=quality['missing_critical'][s.site_id],synthetic=snapshot.synthetic,power_required_kw=next(d.power_required_kw for d in snapshot.designs if d.project_id==s.project_id)) for s in snapshot.sites]
    write_json(out/'knowledge.json',results);write_json(out/'rules.json',RULES)
    export_ontology(snapshot.sites,out/'site_dss.owl')
    ahp_result=ahp(pairwise([4/3,2,4,1.5,3,2]))
    a=utilities(1009.216875399718,.922,14,.2);b=utilities(1046.2763782901068,.961,12,.4)
    write_json(out/'ahp.json',dict(**ahp_result,**compare(a,b,ahp_result['weights']),cost_weight_switch=cost_weight_switch(a,b)))
    fc=train(snapshot)
    write_json(out/'forecast_metrics.json',fc['metrics']);write_json(out/'forecast_points.json',fc['points']);write_json(out/'forecast_test.json',fc['test_rows']);write_json(out/'calibration.json',fc['calibration_errors'])
    write_json(out/'scenarios.json',build_scenarios(fc))
    code_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.rglob('*.py')))).hexdigest()
    write_json(out/'manifest.json',dict(version='0.2.0',snapshot_hash=h,code_hash=code_hash,python=platform.python_version(),dependencies={name:importlib.metadata.version(name) for name in ['pydantic','numpy','scipy','statsmodels','shapely','pyproj','rdflib']},synthetic=snapshot.synthetic,stages=[1,2,3,4]))
    print(json.dumps(dict(snapshot_hash=h,knowledge={r['site_id']:r['status'] for r in results},forecast=fc['metrics']['selection'],test=fc['metrics']['test']),ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',default='data/mock/snapshot.json');p.add_argument('--out',default='reports/stages1_4');p.add_argument('--allow-demo',action='store_true');p.add_argument('--postgres-dsn');p.add_argument('--mvp',action='store_true');p.add_argument('--request');p.add_argument('--finance',default='data/mock/finance.json');a=p.parse_args()
    if a.mvp:
        from site_dss.recommendation import recommend
        from site_dss.bi import export_bi
        request=json.loads(Path(a.request).read_text()) if a.request else {}
        request['allow_demo']=a.allow_demo
        result,folder=recommend(a.snapshot,a.finance,request,output_root='reports/runs')
        export_bi(result)
        print(json.dumps(dict(run_id=result.run_id,recommendation=result.recommendation,elapsed_seconds=result.elapsed_seconds,folder=str(folder)),ensure_ascii=False,indent=2))
    elif a.postgres_dsn:
        from site_dss.data.postgres import import_postgres
        s,_=load_snapshot(a.snapshot,allow_demo=a.allow_demo);print(import_postgres(s,a.postgres_dsn,'migrations/001_initial.sql'))
    else:run(a.snapshot,a.out,a.allow_demo)
if __name__=='__main__':main()
