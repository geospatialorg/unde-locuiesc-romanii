"""Cubul climatic zilnic 1961–prezent → Zarr omogenizat (tmin, tmax, precip).

Sursele: data/daily_{precip,tmin,tmax}_{AAAA}.nc (+ varianta „_synop" pentru anul curent).
Domeniu-țintă: grila istorică 1961–2025 (483×972, pas 0,01°, lat descrescător).
Fișierele anului curent (synop) au domenii mai mari ȘI decalate față de laticea istorică
(~0,006°), deci se reindexează nearest cu toleranță de jumătate de pas.

Ieșire: data/out/climate.zarr — dims (time, lat, lon), un an scris o dată (append pe time),
metadate consolidate. Rulare idempotentă: store-ul se reconstruiește de la zero.
"""

from __future__ import annotations

import re
import shutil
import time as _time

import numpy as np
import xarray as xr

from ..config import DATA_IN, DATA_OUT

VARS = {  # nume scurt → (prefix fișier, numele variabilei în NetCDF)
    "tmin": ("daily_tmin", "daily_minimum_temp"),
    "tmax": ("daily_tmax", "daily_maximum_temp"),
    "precip": ("daily_precip", "daily_precipitation"),
}
ZARR = DATA_OUT / "climate.zarr"
CHUNKS = {"time": 366, "lat": 161, "lon": 162}


def _year_files() -> dict[int, dict[str, str]]:
    """an → {var: cale}; preferă varianta simplă, acceptă „_synop" pentru anul curent."""
    out: dict[int, dict[str, str]] = {}
    for p in DATA_IN.glob("daily_*.nc"):
        m = re.match(r"daily_(precip|tmin|tmax)(?:_synop)?_(\d{4})\.nc$", p.name)
        if not m:
            continue
        var, year = m.group(1), int(m.group(2))
        out.setdefault(year, {})
        # varianta fără synop are prioritate dacă există ambele
        if var not in out[year] or "_synop" not in p.name:
            out[year][var] = str(p)
    return {y: v for y, v in sorted(out.items()) if len(v) == 3}


def _open_year(paths: dict[str, str], ref: xr.Dataset | None) -> xr.Dataset:
    """Deschide cele 3 variabile ale unui an, redenumite scurt, omogenizate pe grila de referință."""
    parts = []
    for short, (_, ncvar) in VARS.items():
        ds = xr.open_dataset(paths[short])[[ncvar]].rename({ncvar: short})
        # anii recenți au ore diferite pe variabile (tmax la 18:00, tmin/precip la 06:00) —
        # normalizăm la zi ca axele să se alinieze exact
        ds = ds.assign_coords(time=ds["time"].dt.floor("D"))
        # domeniile synop diferă și ÎNTRE variabile și sunt decalate față de laticea istorică
        # (~0,006°) → fiecare variabilă se reindexează nearest pe grila-țintă, înainte de merge
        if ref is not None and not (
            np.array_equal(ds["lat"].values, ref["lat"].values)
            and np.array_equal(ds["lon"].values, ref["lon"].values)
        ):
            ds = ds.reindex(lat=ref["lat"], lon=ref["lon"], method="nearest", tolerance=0.005)
        parts.append(ds)
    ds = xr.merge(parts, join="exact")
    for v in VARS:
        ds[v] = ds[v].astype(np.float32)
    return ds


def step_climate_zarr() -> None:
    files = _year_files()
    years = list(files)
    print(f"ani cu toate cele 3 variabile: {years[0]}–{years[-1]} ({len(years)} ani)")

    if ZARR.exists():
        shutil.rmtree(ZARR)

    ref: xr.Dataset | None = None
    t0 = _time.time()
    for i, year in enumerate(years):
        ds = _open_year(files[year], ref)
        if ref is None:
            ref = ds[["lat", "lon"]].copy()
            print(f"grilă-țintă: {ds.sizes['lat']}×{ds.sizes['lon']} "
                  f"(lat {float(ds.lat.min()):.3f}…{float(ds.lat.max()):.3f})")
        if i == 0:
            enc = {v: {"chunks": (CHUNKS["time"], CHUNKS["lat"], CHUNKS["lon"])} for v in VARS}
            ds.to_zarr(ZARR, mode="w", encoding=enc, consolidated=True)
        else:
            ds.to_zarr(ZARR, append_dim="time", consolidated=True)
        ds.close()
        if (i + 1) % 10 == 0 or i == len(years) - 1:
            print(f"  {year}: {i + 1}/{len(years)} ani scriși ({_time.time() - t0:.0f}s)")

    # verificare sumară
    z = xr.open_zarr(ZARR)
    n = z.sizes
    size_gb = sum(f.stat().st_size for f in ZARR.rglob("*") if f.is_file()) / 1e9
    print(f"climate.zarr: time={n['time']} lat={n['lat']} lon={n['lon']} · {size_gb:.1f} GB pe disc")
    z.close()
