CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS snapshots (
 sha256 text PRIMARY KEY, as_of date NOT NULL, synthetic boolean NOT NULL, payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
 snapshot_hash text REFERENCES snapshots ON DELETE CASCADE, source_id text NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(snapshot_hash,source_id)
);

CREATE TABLE IF NOT EXISTS sites (
 snapshot_hash text REFERENCES snapshots ON DELETE CASCADE, site_id text NOT NULL,
 geom geometry(Polygon,4326) NOT NULL CHECK (ST_IsValid(geom)), payload jsonb NOT NULL,
 PRIMARY KEY(snapshot_hash,site_id)
);

CREATE INDEX IF NOT EXISTS sites_geom_idx ON sites USING gist(geom);

CREATE TABLE IF NOT EXISTS demand (
 snapshot_hash text REFERENCES snapshots ON DELETE CASCADE, zone_id text NOT NULL, month date NOT NULL,
 pallets double precision NOT NULL CHECK(pallets>=0), payload jsonb NOT NULL,
 PRIMARY KEY(snapshot_hash,zone_id,month)
);

CREATE TABLE IF NOT EXISTS routes (
 snapshot_hash text NOT NULL, site_id text NOT NULL, zone_id text NOT NULL, period text NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(snapshot_hash,site_id,zone_id,period),
 FOREIGN KEY(snapshot_hash,site_id) REFERENCES sites
);

CREATE TABLE IF NOT EXISTS designs (snapshot_hash text REFERENCES snapshots, project_id text, payload jsonb NOT NULL, PRIMARY KEY(snapshot_hash,project_id));

CREATE TABLE IF NOT EXISTS costs (snapshot_hash text REFERENCES snapshots, ordinal integer, payload jsonb NOT NULL, PRIMARY KEY(snapshot_hash,ordinal));
