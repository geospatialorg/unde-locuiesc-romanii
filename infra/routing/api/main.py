"""API minimal de rutare (pgRouting): cel mai apropiat obiectiv PE DRUM.

  GET /route?lon&lat[&to=hospital|crossing|airport|sea|border]
     → {ok, drive_min, dist_km, straight_km, route: GeoJSON[, hospital|crossing|airport|sea]}

`to=hospital` (implicit): cel mai apropiat spital activ (ANMCS), cu nume.
`to=sea`: ruta către mare, cu Constanța ca destinație fixă (nu cel mai apropiat punct
arbitrar de pe litoral — o destinație reală, cu nume).
`to=border`: cel mai apropiat punct de pe rețeaua rutieră aflat lângă frontiera de stat
(set de vertecși precompus la import; nu are o destinație concretă unică, spre deosebire
de `crossing`, care rutează la un punct de trecere real).

Metodă comună: cei mai apropiați N vertecși-țintă în linie dreaptă (cel mai apropiat pe
șosea nu e mereu cel euclidian), pgr_dijkstra one-to-many pe costuri în secunde, apoi
reconstruirea geometriei către ținta cu timpul minim.
"""

from __future__ import annotations

import json
import os

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DSN = (
    f"host={os.environ.get('PGHOST', 'routing-db')} "
    f"dbname={os.environ.get('PGDATABASE', 'routing')} "
    f"user={os.environ.get('PGUSER', 'ulr')} "
    f"password={os.environ.get('PGPASSWORD', 'ulrpass')}"
)
N_CANDIDATES = 6
# unele muchii vin cu cost_s NULL din osm2pgrouting — fallback la 50 km/h (13,9 m/s)
EDGES_SQL = (
    "SELECT gid AS id, source, target, "
    "COALESCE(cost_s, length_m / 13.9) AS cost, "
    "COALESCE(reverse_cost_s, length_m / 13.9) AS reverse_cost FROM ways"
)
# fiecare țintă: tabelă, coloana geometriei, coloana id vertex-graf, coloane-atribut de întors
# (sub cheia `resp`), dacă are
TARGETS = {
    "hospital": {"table": "hospitals", "geom": "geom", "vid": "vertex_id",
                 "attrs": ["nume", "judet", "city"], "resp": "hospital"},
    "crossing": {"table": "crossings", "geom": "geom", "vid": "vertex_id",
                 "attrs": ["name", "waiting_time_min"], "resp": "crossing"},
    "airport": {"table": "airports", "geom": "geom", "vid": "vertex_id",
                "attrs": ["label", "name"], "resp": "airport"},
    "sea": {"table": "sea_target", "geom": "geom", "vid": "vertex_id",
            "attrs": ["name"], "resp": "sea"},
    "border": {"table": "border_vertices", "geom": "the_geom", "vid": "id", "attrs": [], "resp": None},
}

app = FastAPI(title="ULR routing")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def _conn() -> psycopg.Connection:
    try:
        return psycopg.connect(DSN, connect_timeout=5)
    except Exception as e:
        raise HTTPException(503, f"baza de rutare nu e disponibilă: {e}")


@app.get("/health")
def health():
    with _conn() as con:
        try:
            out = {"ok": True, "edges": con.execute("SELECT count(*) FROM ways").fetchone()[0]}
            for name, t in TARGETS.items():
                out[name] = con.execute(f"SELECT count(*) FROM {t['table']}").fetchone()[0]
        except Exception as e:
            raise HTTPException(503, f"graful nu e importat încă: {e}")
    return out


@app.get("/route")
def route(lon: float, lat: float, to: str = "hospital"):
    t = TARGETS.get(to)
    if t is None:
        raise HTTPException(400, f"țintă necunoscută: {to}")
    pt = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)"

    with _conn() as con:
        try:
            # sursa se ancorează doar pe componenta-gigant a grafului — vertexul pur apropiat
            # poate fi pe un fragment izolat (drumuri de incintă etc.) și rutarea ar eșua
            src = con.execute(
                f"SELECT v.id FROM ways_vertices_pgr v "
                f"JOIN vertex_comp c ON c.id = v.id JOIN graph_meta g ON c.component = g.giant "
                f"ORDER BY v.the_geom <-> {pt} LIMIT 1",
                (lon, lat),
            ).fetchone()
        except Exception as e:
            raise HTTPException(503, f"graful nu e importat încă: {e}")
        if not src:
            raise HTTPException(404, "niciun vertex în graf")
        src_id = src[0]

        attr_cols = "".join(f", {a}" for a in t["attrs"])
        cands = con.execute(
            f"SELECT {t['vid']} AS vid, "
            f"ST_Distance({t['geom']}::geography, {pt}::geography) AS d{attr_cols} "
            f"FROM {t['table']} WHERE {t['vid']} IS NOT NULL "
            f"ORDER BY {t['geom']} <-> {pt} LIMIT %s",
            (lon, lat, lon, lat, N_CANDIDATES),
        ).fetchall()
        if not cands:
            raise HTTPException(404, "nicio țintă în bază")

        targets = list({c[0] for c in cands})
        rows = con.execute(
            "SELECT end_vid, agg_cost FROM pgr_dijkstra(%s, %s, %s::bigint[], true) WHERE edge = -1",
            (EDGES_SQL, src_id, targets),
        ).fetchall()
        if not rows:
            raise HTTPException(404, "nicio țintă accesibilă rutier din acest punct")
        best_vid, best_cost = min(rows, key=lambda r: r[1])
        best = next(c for c in cands if c[0] == best_vid)

        edges = [
            r[0]
            for r in con.execute(
                "SELECT edge FROM pgr_dijkstra(%s, %s, %s, true) WHERE edge <> -1",
                (EDGES_SQL, src_id, best_vid),
            ).fetchall()
        ]
        geom_row = con.execute(
            "SELECT ST_AsGeoJSON(ST_LineMerge(ST_Collect(the_geom)))::text, COALESCE(SUM(length_m), 0) "
            "FROM ways WHERE gid = ANY(%s)",
            (edges,),
        ).fetchone()

    geometry = json.loads(geom_row[0]) if geom_row and geom_row[0] else None
    out = {
        "ok": True,
        "to": to,
        "drive_min": round(best_cost / 60.0, 1),
        "dist_km": round((geom_row[1] or 0) / 1000.0, 1),
        "straight_km": round(best[1] / 1000.0, 1),
        "route": {"type": "Feature", "properties": {}, "geometry": geometry},
    }
    if t["resp"]:
        out[t["resp"]] = dict(zip(t["attrs"], best[2 : 2 + len(t["attrs"])]))
    return out
