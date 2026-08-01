#!/bin/bash
# Importul grafului rutier OSM România + spitalele în baza de rutare (pgRouting).
# Idempotent: pbf-ul e cache-uit în /data/osm/, importul recreează tabelele.
set -euo pipefail

PBF=/data/osm/romania-latest.osm.pbf
ROADS_PBF=/tmp/roads.osm.pbf
ROADS_OSM=/tmp/roads.osm
export PGPASSWORD="${PGPASSWORD:-ulrpass}"
PGHOST="${PGHOST:-routing-db}"
PGUSER="${PGUSER:-ulr}"
PGDB="${PGDATABASE:-routing}"

log() { echo "[import $(date -u +%H:%M:%S)] $*"; }

mkdir -p /data/osm
if [ ! -s "$PBF" ]; then
  log "descarc extractul OSM România (Geofabrik)…"
  curl -fL --retry 3 -o "$PBF.part" https://download.geofabrik.de/europe/romania-latest.osm.pbf
  mv "$PBF.part" "$PBF"
fi
log "pbf: $(du -h "$PBF" | cut -f1)"

log "filtrez rețeaua rutieră (motorway…unclassified, fără residential/service)…"
osmium tags-filter "$PBF" \
  w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,unclassified \
  -o "$ROADS_PBF" --overwrite
osmium cat "$ROADS_PBF" -o "$ROADS_OSM" --overwrite
log "rețea filtrată: $(du -h "$ROADS_OSM" | cut -f1)"

log "aștept baza de date…"
until pg_isready -h "$PGHOST" -U "$PGUSER" -d "$PGDB" -q; do sleep 2; done

psql -h "$PGHOST" -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS pgrouting;"

log "osm2pgrouting (construiește topologia — durează câteva minute)…"
osm2pgrouting -f "$ROADS_OSM" -c /import/mapconfig.xml \
  -d "$PGDB" -U "$PGUSER" -h "$PGHOST" -W "$PGPASSWORD" --clean

log "încarc spitalele, punctele de trecere și linia de frontieră…"
ogr2ogr -f PostgreSQL "PG:host=$PGHOST user=$PGUSER dbname=$PGDB password=$PGPASSWORD" \
  /out/hospitals.geojson -nln hospitals -overwrite -lco GEOMETRY_NAME=geom -nlt POINT
ogr2ogr -f PostgreSQL "PG:host=$PGHOST user=$PGUSER dbname=$PGDB password=$PGPASSWORD" \
  /out/crossings.geojson -nln crossings -overwrite -lco GEOMETRY_NAME=geom -nlt POINT
ogr2ogr -f PostgreSQL "PG:host=$PGHOST user=$PGUSER dbname=$PGDB password=$PGPASSWORD" \
  /out/airports.geojson -nln airports -overwrite -lco GEOMETRY_NAME=geom -nlt POINT
ogr2ogr -f PostgreSQL "PG:host=$PGHOST user=$PGUSER dbname=$PGDB password=$PGPASSWORD" \
  /out/sea_target.geojson -nln sea_target -overwrite -lco GEOMETRY_NAME=geom -nlt POINT
ogr2ogr -f PostgreSQL "PG:host=$PGHOST user=$PGUSER dbname=$PGDB password=$PGPASSWORD" \
  /out/country_line.geojson -nln country_line -overwrite -lco GEOMETRY_NAME=geom -nlt LINESTRING

log "post-procesare: vertecși pentru spitale + indecși…"
psql -h "$PGHOST" -U "$PGUSER" -d "$PGDB" -v ON_ERROR_STOP=1 <<'SQL'
-- osm2pgrouting lasă ocazional costuri NULL pe câteva muchii — le reconstruim din geometrie
UPDATE ways SET length_m = ST_Length(the_geom::geography) WHERE length_m IS NULL;
UPDATE ways SET cost_s = length_m / 13.9 WHERE cost_s IS NULL;
UPDATE ways SET reverse_cost_s = length_m / 13.9 WHERE reverse_cost_s IS NULL;
CREATE INDEX IF NOT EXISTS ways_vertices_geom_idx ON ways_vertices_pgr USING gist(the_geom);

-- componentele tari ale grafului: ancorele (surse și ținte) se restricționează la componenta-gigant,
-- altfel un vertex „cel mai apropiat" de pe un fragment izolat face ruta imposibilă
-- (ex.: aeroportul Otopeni ancorat pe drumurile de incintă → Dijkstra alegea Craiova)
DROP TABLE IF EXISTS vertex_comp;
CREATE TABLE vertex_comp AS
  SELECT component, node AS id FROM pgr_strongComponents(
    'SELECT gid AS id, source, target, COALESCE(cost_s, length_m/13.9) AS cost,
            COALESCE(reverse_cost_s, length_m/13.9) AS reverse_cost FROM ways');
CREATE INDEX ON vertex_comp(id);
DROP TABLE IF EXISTS graph_meta;
CREATE TABLE graph_meta AS
  SELECT component AS giant FROM vertex_comp GROUP BY component ORDER BY count(*) DESC LIMIT 1;
CREATE INDEX IF NOT EXISTS ways_geom_idx ON ways USING gist(the_geom);
ALTER TABLE hospitals ADD COLUMN IF NOT EXISTS vertex_id BIGINT;
UPDATE hospitals h SET vertex_id = (
  SELECT v.id FROM ways_vertices_pgr v
  JOIN vertex_comp c ON c.id = v.id JOIN graph_meta g ON c.component = g.giant
  ORDER BY v.the_geom <-> h.geom LIMIT 1
);
CREATE INDEX IF NOT EXISTS hospitals_geom_idx ON hospitals USING gist(geom);

ALTER TABLE crossings ADD COLUMN IF NOT EXISTS vertex_id BIGINT;
UPDATE crossings x SET vertex_id = (
  SELECT v.id FROM ways_vertices_pgr v
  JOIN vertex_comp c ON c.id = v.id JOIN graph_meta g ON c.component = g.giant
  ORDER BY v.the_geom <-> x.geom LIMIT 1
);
CREATE INDEX IF NOT EXISTS crossings_geom_idx ON crossings USING gist(geom);

ALTER TABLE airports ADD COLUMN IF NOT EXISTS vertex_id BIGINT;
UPDATE airports a SET vertex_id = (
  SELECT v.id FROM ways_vertices_pgr v
  JOIN vertex_comp c ON c.id = v.id JOIN graph_meta g ON c.component = g.giant
  ORDER BY v.the_geom <-> a.geom LIMIT 1
);
CREATE INDEX IF NOT EXISTS airports_geom_idx ON airports USING gist(geom);

ALTER TABLE sea_target ADD COLUMN IF NOT EXISTS vertex_id BIGINT;
UPDATE sea_target s SET vertex_id = (
  SELECT v.id FROM ways_vertices_pgr v
  JOIN vertex_comp c ON c.id = v.id JOIN graph_meta g ON c.component = g.giant
  ORDER BY v.the_geom <-> s.geom LIMIT 1
);
CREATE INDEX IF NOT EXISTS sea_target_geom_idx ON sea_target USING gist(geom);

-- vertecși de graf lângă frontiera terestră (5 km) — pentru rutarea „până la frontieră"
-- (ruta „către mare" folosește o destinație concretă, Constanța, din tabela sea_target)
CREATE INDEX IF NOT EXISTS country_line_geom_idx ON country_line USING gist(geom);
DROP TABLE IF EXISTS border_vertices;
CREATE TABLE border_vertices AS
  SELECT DISTINCT v.id, v.the_geom FROM ways_vertices_pgr v
  JOIN country_line c ON c.border <> 'RO.RO'
  WHERE ST_DWithin(v.the_geom::geography, c.geom::geography, 5000);
DELETE FROM border_vertices WHERE id NOT IN (SELECT c.id FROM vertex_comp c JOIN graph_meta g ON c.component=g.giant);
CREATE INDEX ON border_vertices USING gist(the_geom);

ANALYZE ways; ANALYZE ways_vertices_pgr; ANALYZE hospitals; ANALYZE crossings; ANALYZE airports;
ANALYZE sea_target; ANALYZE border_vertices;
SQL

EDGES=$(psql -h "$PGHOST" -U "$PGUSER" -d "$PGDB" -tAc "SELECT count(*) FROM ways")
HOSP=$(psql -h "$PGHOST" -U "$PGUSER" -d "$PGDB" -tAc "SELECT count(*) FROM hospitals WHERE vertex_id IS NOT NULL")
log "GATA: $EDGES muchii în graf, $HOSP spitale ancorate la rețea."
