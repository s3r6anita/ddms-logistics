import argparse,json
from pathlib import Path
import psycopg
from site_dss.data import load_snapshot,write_json
from site_dss.data.postgres import import_postgres
p=argparse.ArgumentParser();p.add_argument('--dsn',required=True);a=p.parse_args()
s,_=load_snapshot('data/mock/snapshot.json',allow_demo=True)
first=import_postgres(s,a.dsn,'migrations/001_initial.sql');second=import_postgres(s,a.dsn,'migrations/001_initial.sql');assert first==second
with psycopg.connect(a.dsn) as conn:
    version=conn.execute('SELECT postgis_full_version()').fetchone()[0]
    results=conn.execute('SELECT site_id,ST_IsValid(geom),ST_Area(geom::geography),ST_DWithin(geom::geography,geom::geography,1),ST_Intersects(geom,geom) FROM sites WHERE snapshot_hash=%s ORDER BY site_id',(first['sha256'],)).fetchall()
    assert len(results)==5 and all(r[1] and r[2]>0 and r[3] and r[4] for r in results)
write_json('reports/stages1_4/postgis_check.json',dict(**first,idempotent=True,version=version,spatial_checks=results))
print(json.dumps(first))
