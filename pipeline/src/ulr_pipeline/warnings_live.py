"""Avertizări meteo (MeteoRomania) → populație afectată, în timp aproape real.

MeteoRomania publică DOUĂ tipuri de mesaje, în două feed-uri XML distincte:

  nowcasting  avertizari-nowcasting-xml-gis.php  — imediate, ore, „zonă delimitată" cu poligon propriu
  general     avertizari-xml.php                 — informări/atenționări/avertizări, valabile zile,
                                                    cu geometrie pe <judet> și <zona>, fiecare cu cod propriu

Serviciul preia periodic ambele feed-uri, taie geometriile peste grila de 1 km și publică în
directorul servit de Caddy trei produse mici:

  live/warnings.geojson       geometriile (WGS84), colorate pe cod, cu proprietatea `source` — pentru hartă
  live/warnings_cells.parquet cell_id × source → codul de severitate maxim — pentru DuckDB (măsură-conștient)
  live/warnings.json          meta + sumar (populație afectată pe sursă și pe cod), consumat instant de UI

  python -m ulr_pipeline.warnings_live once      # o singură reîmprospătare
  python -m ulr_pipeline.warnings_live serve      # buclă (WARN_INTERVAL secunde)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely import wkt
from shapely.ops import transform as shp_transform

from .config import DATA_OUT

NOWCAST_URL = os.environ.get(
    "WARN_NOWCAST_URL", "https://www.meteoromania.ro/avertizari-nowcasting-xml-gis.php"
)
GENERAL_URL = os.environ.get(
    "WARN_GENERAL_URL", "https://www.meteoromania.ro/avertizari-xml.php"
)
INTERVAL = int(os.environ.get("WARN_INTERVAL", "600"))
LIVE = DATA_OUT / "live"
UA = "unde-locuiesc-romanii/0.1 (+monitorizare avertizari meteo publice)"

# scala unică de severitate: rang → (cod, denumire, culoare). Rang mai mare = mai sever.
LEVEL_BY_RANK: dict[int, tuple[str, str, str]] = {
    0: ("VE", "Verde/Informare", "#2e9e3f"),
    1: ("GA", "Galben", "#f2c200"),
    2: ("PO", "Portocaliu", "#e8720c"),
    3: ("RO", "Roșu", "#cc1414"),
}
# nowcasting: avertizareNivelCod → rang
NOWCAST_RANK = {"VE": 0, "GA": 1, "PO": 2, "RO": 3}
# general: atributul întreg `culoare` de pe <judet>/<zona> → rang (0=verde … 3=roșu)
GEN_RANK = {0: 0, 1: 1, 2: 2, 3: 3}

_points_3857: gpd.GeoDataFrame | None = None
_transformers: dict[int, Transformer] = {}


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def _to_3857(srid: int):
    if srid == 3857:
        return None
    if srid not in _transformers:
        _transformers[srid] = Transformer.from_crs(f"EPSG:{srid}", "EPSG:3857", always_xy=True)
    tr = _transformers[srid]
    return lambda x, y, z=None: tr.transform(x, y)


def _geom(coords: str | None, use: str | None, srid: int):
    if not coords or (use or "true").lower() == "false":
        return None
    g = wkt.loads(coords)
    fn = _to_3857(srid)
    return g if fn is None else shp_transform(fn, g)


def _cell_points() -> gpd.GeoDataFrame:
    global _points_3857
    if _points_3857 is None:
        core = pd.read_parquet(DATA_OUT / "core.parquet", columns=["cell_id", "lon", "lat", "pop_total"])
        _points_3857 = gpd.GeoDataFrame(
            core[["cell_id", "pop_total"]],
            geometry=gpd.points_from_xy(core["lon"], core["lat"]),
            crs="EPSG:4326",
        ).to_crs("EPSG:3857")
        _log(f"centroizi celule pregătiți: {len(_points_3857):,}")
    return _points_3857


def fetch_xml(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _level(rank: int) -> tuple[str, str, str]:
    return LEVEL_BY_RANK.get(rank, LEVEL_BY_RANK[0])


def parse_nowcasting(xml_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Returnează (features, messages). O avertizare = un feature = un mesaj."""
    root = ET.fromstring(xml_bytes)
    features, messages, seen = [], [], set()
    for a in root.iter("avertizare"):
        # feed-ul gol este <avertizare/> — sare peste placeholder-ul „fără avertizări"
        if not a.get("avertizareId") and not a.get("coordsGis") and not a.get("fenomenAvertizat"):
            continue
        wid = a.get("avertizareId") or a.get("numarAvertizare") or str(len(messages))
        if wid in seen:
            continue
        seen.add(wid)
        rank = NOWCAST_RANK.get((a.get("avertizareNivelCod") or "").upper(), 1)
        code, name, color = _level(rank)
        geom = _geom(a.get("coordsGis"), a.get("useCoordsGis"), int(a.get("srid", "3857")))
        zones = " ".join(z.get("text", "") for z in a.findall("zona_afectata")).strip()
        msg = {
            "source": "nowcasting", "group_id": f"n{wid}", "id": wid,
            "kind": a.get("avertizareTipDenumire", "Avertizare nowcasting"),
            "level_code": code, "level_name": name, "color": color, "level_rank": rank,
            "phenomenon": a.get("fenomenAvertizat", ""),
            "start": a.get("dataInceput"), "end": a.get("dataSfarsit"),
            "interval": None, "entity": a.get("entitateOrganizatorica", ""),
            "area_text": zones, "affected_pop": 0,
        }
        messages.append(msg)
        if geom is not None:
            features.append({**msg, "geometry": geom})
    return features, messages


def parse_general(xml_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Returnează (features, messages). Un mesaj are multe <judet>/<zona>, fiecare cu cod propriu."""
    root = ET.fromstring(xml_bytes)
    features, messages = [], []
    for i, a in enumerate(root.iter("avertizare")):
        gid = f"g{i}"
        parts, ranks = [], []
        for el in list(a):
            if el.tag not in ("judet", "zona"):
                continue
            geom = _geom(el.get("coordGis"), el.get("useCoordGis"), 3857)
            if geom is None:
                continue
            try:
                rank = GEN_RANK.get(int(el.get("culoare", "1")), 1)
            except ValueError:
                rank = 1
            # culoare=0 (verde) = geometrie de context, NU sub cod activ (ex. județul întreg
            # când doar zona montană e avertizată). O ignorăm: nu se desenează, nu se numără.
            if rank < 1:
                continue
            code, name, color = _level(rank)
            ranks.append(rank)
            parts.append({
                "source": "general", "group_id": gid, "geometry": geom,
                "level_code": code, "level_name": name, "color": color, "level_rank": rank,
                "unit_kind": el.tag, "unit_cod": el.get("cod", ""),
            })
        max_rank = max(ranks) if ranks else 0
        code, name, color = _level(max_rank)
        # compoziția pe coduri: câte geometrii are mesajul la fiecare nivel (un buletin ANM
        # „cod portocaliu" acoperă și zone de cod galben — de aici cele două culori pe hartă)
        level_mix = []
        for r in sorted({p["level_rank"] for p in parts}, reverse=True):
            c, n, col = _level(r)
            level_mix.append({"code": c, "name": n, "color": col,
                              "n": sum(1 for p in parts if p["level_rank"] == r)})
        msg = {
            "source": "general", "group_id": gid, "id": gid,
            "kind": a.get("numeTipMesaj", "Atenționare meteorologică"),
            "level_code": code, "level_name": name, "color": color, "level_rank": max_rank,
            "num_culoare": a.get("numeCuloare", name.lower()),
            "phenomenon": a.get("fenomeneVizate", ""),
            "start": a.get("dataAparitiei"), "end": a.get("dataExpirarii"),
            "interval": a.get("intervalul", ""),
            "entity": "Administrația Națională de Meteorologie",
            "area_text": a.get("zonaAfectata", ""),
            "counties": sorted({p["unit_cod"] for p in parts if p["unit_kind"] == "judet"}),
            "n_zones": sum(1 for p in parts if p["unit_kind"] == "zona"),
            "level_mix": level_mix,
            "affected_pop": 0,
        }
        messages.append(msg)
        features.extend(parts)
    return features, messages


def compute(features: list[dict], messages: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Populează affected_pop pe fiecare mesaj și întoarce (celule × sursă, celule × mesaj)."""
    cols = ["cell_id", "source", "level_code", "level_name", "level_rank"]
    msg_cols = ["cell_id", "group_id", "source", "level_code", "level_name", "level_rank"]
    if not features:
        return pd.DataFrame(columns=cols), pd.DataFrame(columns=msg_cols)

    feats = gpd.GeoDataFrame(
        [{"fi": i, "group_id": f["group_id"], "source": f["source"],
          "level_code": f["level_code"], "level_name": f["level_name"], "level_rank": f["level_rank"]}
         for i, f in enumerate(features)],
        geometry=[f["geometry"] for f in features], crs="EPSG:3857",
    )
    pts = _cell_points()
    pairs = gpd.sjoin(pts, feats, predicate="within", how="inner")

    # populație afectată per mesaj (celule distincte în oricare geometrie a mesajului)
    per_msg = (
        pairs.drop_duplicates(["cell_id", "group_id"]).groupby("group_id")["pop_total"].sum()
    )
    for m in messages:
        m["affected_pop"] = int(per_msg.get(m["group_id"], 0))

    pairs = pairs.sort_values("level_rank")
    # per (celulă, sursă): reținem codul maxim (fără dublă numărare în cadrul unei surse)
    affected = (
        pairs.drop_duplicates(["cell_id", "source"], keep="last")[cols].reset_index(drop=True)
    )
    # per (celulă, mesaj): pentru afișarea/filtrarea distinctă a fiecărui mesaj, măsură-conștient
    cell_msg = (
        pairs.drop_duplicates(["cell_id", "group_id"], keep="last")[msg_cols].reset_index(drop=True)
    )
    return affected, cell_msg


def write_outputs(features: list[dict], messages: list[dict], affected: pd.DataFrame,
                  cell_msg: pd.DataFrame, feed_ok: dict[str, bool]) -> None:
    LIVE.mkdir(parents=True, exist_ok=True)

    cells = affected.copy()
    if not cells.empty:
        cells["cell_id"] = cells["cell_id"].astype("uint32")
        cells["level_rank"] = cells["level_rank"].astype("int8")
    cells.to_parquet(LIVE / "warnings_cells.parquet", index=False, compression="zstd")

    cm = cell_msg.copy()
    if not cm.empty:
        cm["cell_id"] = cm["cell_id"].astype("uint32")
        cm["level_rank"] = cm["level_rank"].astype("int8")
    cm.to_parquet(LIVE / "warnings_cell_msg.parquet", index=False, compression="zstd")

    def source_summary(src: str) -> dict:
        sub = affected[affected["source"] == src] if not affected.empty else affected
        levels = []
        if not sub.empty:
            grp = sub.groupby(["level_rank", "level_code", "level_name"], as_index=False).agg(
                pop=("cell_id", "count")  # placeholder; pop reală se ia din join, dar aici numărăm celule
            )
        # populația pe cod: sumăm pop_total din compute prin re-join rapid pe pop
        pop_by_level = {}
        ncell_by_level = {}
        if not sub.empty:
            merged = sub.merge(
                _cell_points()[["cell_id", "pop_total"]], on="cell_id", how="left"
            )
            g = merged.groupby(["level_rank", "level_code", "level_name"], as_index=False).agg(
                pop=("pop_total", "sum"), n=("cell_id", "count")
            )
            for _, r in g.sort_values("level_rank", ascending=False).iterrows():
                levels.append({
                    "code": r["level_code"], "name": r["level_name"],
                    "color": _level(int(r["level_rank"]))[2], "rank": int(r["level_rank"]),
                    "pop": int(r["pop"]), "n_cells": int(r["n"]),
                })
        total = int(levels_total(levels))
        msgs = [m for m in messages if m["source"] == src]
        return {"ok": feed_ok.get(src, False), "total_affected": total,
                "n_messages": len(msgs), "levels": levels,
                "messages": [_msg_public(m) for m in
                             sorted(msgs, key=lambda m: (-m["level_rank"], m.get("start") or ""))]}

    combined_total = 0
    if not affected.empty:
        merged = affected.drop_duplicates("cell_id").merge(
            _cell_points()[["cell_id", "pop_total"]], on="cell_id", how="left"
        )
        combined_total = int(merged["pop_total"].sum())

    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources_url": {"nowcasting": NOWCAST_URL, "general": GENERAL_URL},
        "combined": {"total_affected": combined_total},
        "sources": {"nowcasting": source_summary("nowcasting"), "general": source_summary("general")},
    }
    with open(LIVE / "warnings.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    _write_geojson(features)

    n = meta["sources"]
    _log(f"scris: combinat {combined_total:,} persoane · "
         f"nowcasting {n['nowcasting']['total_affected']:,} ({n['nowcasting']['n_messages']} msg) · "
         f"general {n['general']['total_affected']:,} ({n['general']['n_messages']} msg)")


def levels_total(levels: list[dict]) -> int:
    return sum(l["pop"] for l in levels)


def _msg_public(m: dict) -> dict:
    keys = ["source", "id", "group_id", "kind", "level_code", "level_name", "color", "phenomenon",
            "start", "end", "interval", "entity", "area_text", "affected_pop"]
    out = {k: m.get(k) for k in keys}
    if m["source"] == "general":
        out["counties"] = m.get("counties", [])
        out["n_zones"] = m.get("n_zones", 0)
        out["level_mix"] = m.get("level_mix", [])
    return out


def _write_geojson(features: list[dict]) -> None:
    if not features:
        (LIVE / "warnings.geojson").write_text(
            '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
        )
        return
    g = gpd.GeoDataFrame(
        [{"source": f["source"], "level_code": f["level_code"], "level_name": f["level_name"],
          "color": f["color"], "level_rank": f["level_rank"],
          "unit_cod": f.get("unit_cod", ""), "group_id": f["group_id"]} for f in features],
        geometry=[f["geometry"] for f in features], crs="EPSG:3857",
    )
    g["geometry"] = g.geometry.simplify(300)  # ~300 m, pentru fișier mic
    g = g.to_crs("EPSG:4326")
    (LIVE / "warnings.geojson").write_text(g.to_json(drop_id=True), encoding="utf-8")


def refresh() -> None:
    features, messages, feed_ok = [], [], {"nowcasting": False, "general": False}
    for src, url, parser in [
        ("nowcasting", NOWCAST_URL, parse_nowcasting),
        ("general", GENERAL_URL, parse_general),
    ]:
        try:
            f, m = parser(fetch_xml(url))
            features += f
            messages += m
            feed_ok[src] = True
        except Exception as e:
            _log(f"EROARE feed {src}: {e!r}")
    if not any(feed_ok.values()):
        _log("ambele feed-uri au eșuat — păstrez produsele anterioare")
        return
    affected, cell_msg = compute(features, messages)
    write_outputs(features, messages, affected, cell_msg, feed_ok)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    if mode == "serve":
        _log(f"pornesc bucla de avertizări (interval {INTERVAL}s)")
        while True:
            refresh()
            time.sleep(INTERVAL)
    else:
        refresh()


if __name__ == "__main__":
    main()
