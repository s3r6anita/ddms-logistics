import json
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from site_dss.data import digest

def import_postgres(snapshot,dsn,migration):
    raw=snapshot.model_dump(mode='json');h=digest(raw)
    with psycopg.connect(dsn) as conn:
        conn.execute(Path(migration).read_text())
        conn.execute('INSERT INTO snapshots VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',(h,snapshot.as_of,snapshot.synthetic,Jsonb(raw)))
        for e in snapshot.evidence:conn.execute('INSERT INTO evidence VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(h,e.source_id,Jsonb(e.model_dump(mode='json'))))
        for s in snapshot.sites:conn.execute('INSERT INTO sites VALUES (%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s) ON CONFLICT DO NOTHING',(h,s.site_id,json.dumps(s.geometry),Jsonb(s.model_dump(mode='json'))))
        for d in snapshot.demand:conn.execute('INSERT INTO demand VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(h,d.zone_id,d.month,d.ordered_pallets,Jsonb(d.model_dump(mode='json'))))
        for r in snapshot.routes:conn.execute('INSERT INTO routes VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(h,r.site_id,r.zone_id,r.period,Jsonb(r.model_dump(mode='json'))))
        for d in snapshot.designs:conn.execute('INSERT INTO designs VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(h,d.project_id,Jsonb(d.model_dump(mode='json'))))
        for i,c in enumerate(snapshot.costs):conn.execute('INSERT INTO costs VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',(h,i,Jsonb(c.model_dump(mode='json'))))
        counts={t:conn.execute(f'SELECT count(*) FROM {t} WHERE snapshot_hash=%s',(h,)).fetchone()[0] for t in ['sites','demand','routes','evidence','designs','costs']}
    return dict(sha256=h,counts=counts)
