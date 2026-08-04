"""Asamblarea produselor publicate: parquet-uri tematice, registru, limite."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd
import pyogrio

from .config import CLIMATE_YEAR, DATA_OUT, SRC, STAGING
from .registry_def import GROUPS, MEASURES, V

F32 = ["lon", "lat"]


def _write(df: pd.DataFrame, name: str) -> None:
    path = DATA_OUT / name
    df.to_parquet(path, index=False, engine="pyarrow", compression="zstd", row_group_size=32768)
    print(f"  {name}: {len(df):,} rânduri, {path.stat().st_size / 1e6:.1f} MB")


def _cat(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = df[c].astype("category")
    return df


def step_export() -> None:
    cells = pd.read_parquet(STAGING / "cells.parquet")
    admin = pd.read_parquet(STAGING / "admin.parquet")
    landform = pd.read_parquet(STAGING / "landform.parquet")
    intravilan = pd.read_parquet(STAGING / "intravilan.parquet")
    protected_areas = pd.read_parquet(STAGING / "protected_areas.parquet")
    water = pd.read_parquet(STAGING / "water.parquet")
    watercourses = pd.read_parquet(STAGING / "watercourses.parquet")
    floods = pd.read_parquet(STAGING / "floods.parquet")
    bear = pd.read_parquet(STAGING / "bear.parquet")
    hospitals = pd.read_parquet(STAGING / "hospitals.parquet")
    crossings = pd.read_parquet(STAGING / "crossings.parquet")
    airports = pd.read_parquet(STAGING / "airports.parquet")
    terrain = pd.read_parquet(STAGING / "terrain.parquet")
    border = pd.read_parquet(STAGING / "border.parquet")
    climate = pd.read_parquet(STAGING / "climate.parquet")
    hist_path = STAGING / "climate_hist.parquet"
    if hist_path.exists():  # analiza multianuală (climate_history) — opțională la primele rulări
        climate = climate.merge(pd.read_parquet(hist_path), on="cell_id", how="left")

    core = cells.drop(columns=["grid_id", "e", "n", "pop_2021_eurostat", "pop_2018"]).copy()
    for c in F32:
        core[c] = core[c].astype(np.float32)

    env = (admin.merge(landform, on="cell_id").merge(intravilan, on="cell_id")
           .merge(protected_areas, on="cell_id").merge(water, on="cell_id")
           .merge(watercourses, on="cell_id").merge(floods, on="cell_id").merge(bear, on="cell_id")
           .merge(hospitals, on="cell_id").merge(crossings, on="cell_id").merge(airports, on="cell_id")
           .merge(terrain, on="cell_id").merge(border, on="cell_id"))
    env = _cat(env, ["uat_name", "uat_status", "county_mn", "county_name", "region_name", "mediu",
                     "intravilan", "acces_gaz", "categorie_apa", "categorie_curs", "scenariu_inundatii",
                     "risc_urs",
                     "nearest_hospital", "nearest_crossing", "nearest_airport",
                     "landform_name", "landform_type", "landform_lvl0", "landform_lvl1",
                     "border_neighbor"])

    core = core.sort_values("cell_id", ignore_index=True)
    env = env.sort_values("cell_id", ignore_index=True)
    climate = climate.sort_values("cell_id", ignore_index=True)

    print("scriu parquet-urile:")
    _write(core, "core.parquet")
    _write(env, "env.parquet")
    _write(climate, "climate.parquet")

    county_daily = pd.read_parquet(STAGING / "county_climate_daily.parquet")
    _write(county_daily, "county_climate_daily.parquet")
    county_annual = pd.read_parquet(STAGING / "county_climate_annual.parquet")
    _write(county_annual, "county_climate_annual.parquet")

    shutil.copy(STAGING / "gridspec.json", DATA_OUT / "gridspec.json")

    _export_boundaries()
    _export_gazetteer()
    _build_registry(core, env, climate)


def _export_boundaries() -> None:
    counties = pyogrio.read_dataframe(SRC["county"])
    counties["geometry"] = counties.geometry.simplify(100)
    counties = counties.rename(columns={"mnemonic": "countyMn"})
    counties = counties.to_crs("EPSG:4326")[["countyMn", "name", "region", "geometry"]]
    counties.to_file(DATA_OUT / "county.geojson", driver="GeoJSON")

    line = pyogrio.read_dataframe(SRC["country_line"])
    line["geometry"] = line.geometry.simplify(100)
    line = line.to_crs("EPSG:4326")[["border", "geometry"]]
    line.to_file(DATA_OUT / "country_line.geojson", driver="GeoJSON")
    print("  county.geojson + country_line.geojson scrise")


def _export_gazetteer() -> None:
    """gazetteer.json — indexul de căutare: UAT-uri (LAU) + localități (intravilan).

    Rând compact: {k: 'u'|'l', n: nume, t: tip, j: județ, b: [minx,miny,maxx,maxy] în WGS84}.
    Normalizarea fără diacritice se face în client (aceeași regulă la indexare și interogare).
    """
    from .steps.admin import STATUS_MAP

    def _strip(s: str) -> str:
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))

    rows: list[dict] = []

    lau = pyogrio.read_dataframe(
        SRC["lau"], columns=["natCode", "name", "natLevName", "county"]
    ).to_crs("EPSG:4326")
    lb = lau.geometry.bounds.round(4)
    for i, r in enumerate(lau.itertuples()):
        rows.append({
            "k": "u", "n": r.name, "t": STATUS_MAP.get(r.natLevName, "UAT"), "j": r.county,
            "b": [lb.minx.iloc[i], lb.miny.iloc[i], lb.maxx.iloc[i], lb.maxy.iloc[i]],
        })
    # județ afișat cu diacritice și pentru localități: LAU are numele corecte
    county_lookup = {_strip(c).upper(): c for c in lau["county"].dropna().unique()}

    iv = pyogrio.read_dataframe(
        SRC["intravilan"], columns=["DENUMIRE", "SIRUTA", "TipLocalitate", "JUDET"]
    ).to_crs("EPSG:4326")
    ib = iv.geometry.bounds
    df = pd.concat([iv.drop(columns="geometry"), ib], axis=1)
    grp = df.groupby("SIRUTA", as_index=False).agg(
        n=("DENUMIRE", "first"), tip=("TipLocalitate", "first"), j=("JUDET", "first"),
        minx=("minx", "min"), miny=("miny", "min"), maxx=("maxx", "max"), maxy=("maxy", "max"),
    )
    for r in grp.itertuples():
        tip = r.tip or ""
        t = "sat" if tip.startswith("Sat") else ("sector" if tip.startswith("Sector") else "localitate urbană")
        j = county_lookup.get(str(r.j).upper(), str(r.j).title())
        rows.append({
            "k": "l", "n": r.n, "t": t, "j": j,
            "b": [round(r.minx, 4), round(r.miny, 4), round(r.maxx, 4), round(r.maxy, 4)],
        })

    path = DATA_OUT / "gazetteer.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    n_uat = sum(1 for r in rows if r["k"] == "u")
    print(f"  gazetteer.json: {n_uat:,} UAT-uri + {len(rows) - n_uat:,} localități, "
          f"{path.stat().st_size / 1e6:.1f} MB")


def _build_registry(core: pd.DataFrame, env: pd.DataFrame, climate: pd.DataFrame) -> None:
    con = duckdb.connect()
    con.register("core", core)
    con.register("env", env)
    con.register("climate", climate)

    variables = []
    for vdef in V:
        v = dict(vdef)
        t, col = v["table"], v["id"]
        if v["dtype"] in ("int", "float"):
            row = con.execute(
                f'SELECT min("{col}"), max("{col}"), '
                f'quantile_cont("{col}", 0.02), quantile_cont("{col}", 0.5), '
                f'quantile_cont("{col}", 0.98), count(*) - count("{col}") FROM {t}'
            ).fetchone()
            v["stats"] = {
                "min": _num(row[0]), "max": _num(row[1]),
                "p02": _num(row[2]), "p50": _num(row[3]), "p98": _num(row[4]),
                "nulls": int(row[5]),
            }
        else:
            cats = con.execute(
                f'SELECT "{col}", count(*) FROM {t} WHERE "{col}" IS NOT NULL '
                f"GROUP BY 1 ORDER BY count(*) DESC LIMIT 200"
            ).fetchall()
            v["categories"] = [{"value": c, "count": int(n)} for c, n in cats]
        variables.append(v)

    # etichete pentru județe (mnemonic → nume)
    county_labels = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT DISTINCT county_mn, county_name FROM env WHERE county_mn IS NOT NULL"
        ).fetchall()
    }

    national = {
        m["id"]: int(con.execute(f'SELECT sum("{m["id"]}") FROM core').fetchone()[0])
        for m in MEASURES
    }

    registry = {
        "version": "v0",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataNote": "Câți români locuiesc într-un loc și cum arată viața acolo",
        "climateYear": CLIMATE_YEAR,
        "tables": {"core": "core.parquet", "env": "env.parquet", "climate": "climate.parquet"},
        "groups": GROUPS,
        "measures": MEASURES,
        "national": national,
        "countyLabels": county_labels,
        "variables": variables,
    }
    with open(DATA_OUT / "registry.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=1)
    print(f"  registry.json: {len(variables)} variabile, total național {national['pop_total']:,}")


def _num(x):
    if x is None:
        return None
    x = float(x)
    return round(x, 3) if not float(x).is_integer() else int(x)
