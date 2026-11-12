"""Append immutable run marts; atomically select one run for all BI views."""
import json,sqlite3
from pathlib import Path

TABLES={
'run_sites':'run_id TEXT,site_id TEXT,status TEXT,score REAL,expected_cost_million REAL,success_rate REAL,wilson_lower REAL,sla REAL,solver_status TEXT',
'scenario_metrics':'run_id TEXT,site_id TEXT,sample TEXT,scenario_id TEXT,cost_million REAL,success INTEGER,unserved_pallets REAL',
'forecast_points':'run_id TEXT,zone_id TEXT,month TEXT,point REAL,p10 REAL,p90 REAL',
'forecast_quality':'run_id TEXT,model TEXT,mae REAL,wape REAL,coverage80 REAL,coverage95 REAL',
'rule_trace':'run_id TEXT,site_id TEXT,rule_id TEXT,conclusion TEXT,reason TEXT',
}

def export_bi(run,path='data/processed/bi.sqlite'):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS registered_runs (run_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS selected_run (singleton INTEGER PRIMARY KEY CHECK(singleton=1),run_id TEXT NOT NULL REFERENCES registered_runs)')
        for name,cols in TABLES.items():
            conn.execute(f'CREATE TABLE IF NOT EXISTS {name} ({cols})')
            conn.execute(f'CREATE VIEW IF NOT EXISTS active_{name} AS SELECT t.* FROM {name} t JOIN selected_run s ON t.run_id=s.run_id')
        from site_dss.data import digest
        h=digest(run.model_dump(mode='json'));old=conn.execute('SELECT payload_hash FROM registered_runs WHERE run_id=?',(run.run_id,)).fetchone()
        if old and old[0]!=h:raise ValueError('attempt to overwrite immutable BI run')
        if not old:
            conn.execute('INSERT INTO registered_runs VALUES (?,?)',(run.run_id,h))
            for s in run.sites:
                v=s.validation or {}
                conn.execute('INSERT INTO run_sites VALUES (?,?,?,?,?,?,?,?,?)',(run.run_id,s.site_id,s.status,s.score,v.get('expected_cost_rub',0)/1e6 if v else None,v.get('success_rate'),v.get('wilson95',[None])[0],v.get('expected_sla'),s.solver_status))
                for t in s.knowledge['trace']:conn.execute('INSERT INTO rule_trace VALUES (?,?,?,?,?)',(run.run_id,s.site_id,t['rule_id'],t['conclusion'],t['reason']))
            conn.executemany('INSERT INTO scenario_metrics VALUES (?,?,?,?,?,?,?)',[(run.run_id,r['site_id'],r['sample'],r['scenario_id'],r['cost_rub']/1e6,int(r['success']),r['unserved_pallets']) for r in run.scenario_metrics])
            conn.executemany('INSERT INTO forecast_points VALUES (?,?,?,?,?,?)',[(run.run_id,r['zone_id'],r['target_month'],r['point'],r['p10'],r['p90']) for r in run.forecast['points']])
            m=run.forecast['metrics'];v=m['test'][m['selection']]
            conn.execute('INSERT INTO forecast_quality VALUES (?,?,?,?,?,?)',(run.run_id,m['selection'],v['MAE'],v['WAPE'],v['coverage_80'],v['coverage_95']))
        conn.execute('INSERT INTO selected_run VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET run_id=excluded.run_id',(run.run_id,))
    return str(path)
