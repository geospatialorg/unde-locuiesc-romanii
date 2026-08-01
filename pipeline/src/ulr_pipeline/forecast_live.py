"""Prognoze ECMWF/CAMS publicate atomic pentru grila de recensamant.

Serviciul descarca independent prognoza meteo ECMWF si prognoza de calitate a
aerului CAMS, le agrega pe zile locale Europe/Bucharest si publica un manifest
mic, potrivit pentru consum direct din frontend:

  python -m ulr_pipeline.forecast_live once
  python -m ulr_pipeline.forecast_live serve

Fisierele de date sunt imuabile si specifice rularii modelului. Hartile dintre
celulele de recensamant si grilele native au nume stabile. ``manifest.json`` se
inlocuieste atomic numai dupa ce toate celelalte operatii de publicare s-au
terminat.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree

from .config import DATA_OUT

INTERVAL = max(60, int(os.environ.get("FORECAST_INTERVAL", "21600")))
FORECAST_DIR = DATA_OUT / "live" / "forecast"
MANIFEST_PATH = FORECAST_DIR / "manifest.json"
LOCAL_TIMEZONE = "Europe/Bucharest"
BOX = {"north": 49.0, "west": 20.0, "south": 43.0, "east": 30.0}
WEATHER_STEPS = list(range(3, 121, 3))
ADS_DATASET = "cams-europe-air-quality-forecasts"
ADS_DEFAULT_URL = "https://ads.atmosphere.copernicus.eu/api"
ADS_CATALOGUE_TIMEOUT = 20
USER_AGENT = "unde-locuiesc-romanii/0.1 (prognoze publice ECMWF si CAMS)"

POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2")
AIR_FIELDS = {
    "pm25": "pm25_max",
    "pm10": "pm10_max",
    "no2": "no2_max",
    "o3": "o3_max",
    "so2": "so2_max",
}
AQI_THRESHOLDS = {
    "pm25": (10.0, 20.0, 25.0, 50.0, 75.0),
    "pm10": (20.0, 40.0, 50.0, 100.0, 150.0),
    "no2": (40.0, 90.0, 120.0, 230.0, 340.0),
    "o3": (50.0, 100.0, 130.0, 240.0, 380.0),
    "so2": (100.0, 200.0, 350.0, 500.0, 750.0),
}

SOURCE_META = {
    "weather": {
        "provider": "ECMWF Open Data",
        "model": "IFS 0.25° deterministic",
        "resolution": "0.25°",
        "attribution": "ECMWF Open Data, CC BY 4.0",
    },
    "air": {
        "provider": "Copernicus Atmosphere Monitoring Service (CAMS)",
        "model": "CAMS Europe air-quality ensemble",
        "resolution": "0.1°",
        "attribution": "Copernicus Atmosphere Monitoring Service (CAMS), CC BY 4.0",
    },
}

# Produsele meteo se construiesc DINAMIC la fiecare rulare, în funcție de prognoză:
# nu are sens „ger sub -10°C" în plină caniculă. Pragul urcă/coboară pe trepte standard,
# la cea mai severă atinsă de prognoză pe orizont; produsul irelevant devine `active: False`
# (frontend-ul îl ascunde). Aerul rămâne fix (activ când sursa CAMS e disponibilă).
HEAT_LADDER = [30, 32, 35, 38, 40]   # °C — se alege cea mai mare treaptă ≤ maximul național
COLD_LADDER = [0, -5, -10, -15, -20]  # °C — se alege cea mai joasă treaptă ≥ minimul național

AIR_PRODUCT = {
    "source": "air",
    "field": "aqi_rank",
    "reducer": "max",
    "operator": ">=",
    "threshold": 3,
    "unit": "rang AQI european (0-5)",
    "label": "Aer slab prognozat",
    "question": "Câți români vor fi potențial expuși la o calitate slabă a aerului sau mai rea?",
    "definition": "Cea mai rea categorie zilnică dintre PM2.5, PM10, NO₂, O₃ și SO₂.",
    "color": "#8c2d84",
}


def _fmt_c(value: float) -> str:
    return f"{value:g}°C"


def _heat_product(threshold: float, active: bool) -> dict[str, Any]:
    return {
        "source": "weather", "field": "tmax", "reducer": "max", "operator": ">=",
        "threshold": threshold, "unit": "°C", "label": "Caniculă prognozată",
        "question": f"Câți români vor fi potențial expuși la temperaturi de cel puțin {_fmt_c(threshold)}?",
        "definition": "Maximul zilnic al intervalelor ECMWF de temperatură la 2 m.",
        "color": "#d7301f", "active": active,
    }


def _cold_product(threshold: float, active: bool) -> dict[str, Any]:
    return {
        "source": "weather", "field": "tmin", "reducer": "min", "operator": "<=",
        "threshold": threshold, "unit": "°C", "label": "Ger prognozat",
        "question": f"Câți români vor fi potențial expuși la temperaturi de cel mult {_fmt_c(threshold)}?",
        "definition": "Minimul zilnic al intervalelor ECMWF de temperatură la 2 m.",
        "color": "#2b8cbe", "active": active,
    }


# o întrebare e „rezonabilă" dacă expune cel puțin această pondere din populație
POP_FLOOR_FRACTION = 0.005  # 0,5%


def _cell_forecast(sources: dict[str, Any]) -> "pd.DataFrame | None":
    """Prognoza pe celulele locuite: tmax/tmin interpolate pe cele 4 noduri vecine (exact ca
    în aplicație) + populația din core.parquet. Astfel pragul se alege după oamenii chiar
    expuși, nu după un vârf izolat al grilei brute. None dacă datele lipsesc."""
    weather = sources.get("weather", {})
    data_file = weather.get("data_file")
    map_file = weather.get("map_file")
    if not weather.get("ok") or not data_file or not map_file:
        return None
    try:
        wd = pd.read_parquet(DATA_OUT / data_file, columns=["grid_id", "tmin", "tmax"])
        mp = pd.read_parquet(DATA_OUT / map_file)
        core = pd.read_parquet(DATA_OUT / "core.parquet", columns=["cell_id", "pop_total"])
    except Exception:
        return None
    if wd.empty or mp.empty or core.empty:
        return None
    grp = wd.groupby("grid_id").agg(tmax=("tmax", "max"), tmin=("tmin", "min"))

    def _interp(series: pd.Series) -> np.ndarray:
        vals = np.stack([mp[f"grid_id_{s}"].map(series).to_numpy(dtype=float) for s in "abcd"], axis=1)
        wts = np.stack([mp[f"weight_{s}"].to_numpy(dtype=float) for s in "abcd"], axis=1)
        ok = np.isfinite(vals)
        num = np.where(ok, wts * vals, 0.0).sum(axis=1)
        den = np.where(ok, wts, 0.0).sum(axis=1)
        return np.where(den > 0, num / den, np.nan)

    cells = pd.DataFrame({
        "cell_id": mp["cell_id"].to_numpy(),
        "tmax": _interp(grp["tmax"]),
        "tmin": _interp(grp["tmin"]),
    }).merge(core, on="cell_id", how="inner")
    return cells


def _pick_threshold(
    cells: "pd.DataFrame", ladder: list[int], field: str, op: str, floor: float
) -> tuple[int | None, bool]:
    """Pragul cel mai sever care expune ≥ floor oameni; dacă niciunul nu-l atinge, treapta cu
    cea mai mare populație expusă (>0). (prag, activ); (None, False) dacă nimeni nu e expus."""
    def exposed(thr: int) -> int:
        mask = cells[field] >= thr if op == ">=" else cells[field] <= thr
        return int(cells.loc[mask, "pop_total"].sum())

    counts = [(band, exposed(band)) for band in ladder]
    reachable = [band for band, pop in counts if pop > 0]
    if not reachable:
        return None, False
    meeting = [band for band, pop in counts if pop >= floor]
    if meeting:
        return (max(meeting) if op == ">=" else min(meeting)), True
    return max(counts, key=lambda bp: bp[1])[0], True


def _build_products(sources: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Produsele meteo, adaptate la prognoza curentă (praguri rezonabile + relevanță)."""
    cells = _cell_forecast(sources)
    if cells is None or cells.empty:
        heat_thr, heat_active, cold_thr, cold_active = 35, False, -10, False
    else:
        floor = float(cells["pop_total"].sum()) * POP_FLOOR_FRACTION
        heat_thr, heat_active = _pick_threshold(cells, HEAT_LADDER, "tmax", ">=", floor)
        cold_thr, cold_active = _pick_threshold(cells, COLD_LADDER, "tmin", "<=", floor)
        heat_thr = 35 if heat_thr is None else heat_thr
        cold_thr = -10 if cold_thr is None else cold_thr
    air = dict(AIR_PRODUCT)
    air["active"] = bool(sources.get("air", {}).get("ok"))
    return {
        "heat": _heat_product(heat_thr, heat_active),
        "cold": _cold_product(cold_thr, cold_active),
        "air_poor": air,
    }


class SourceError(RuntimeError):
    """Eroare controlata, cu mesaj sigur pentru manifest."""


@dataclass(frozen=True)
class SpatialCube:
    values: np.ndarray
    times: np.ndarray
    grid_ids: np.ndarray
    lon: np.ndarray
    lat: np.ndarray


def _log(message: str) -> None:
    print(f"[forecast {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {message}", flush=True)


def _utc(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def _iso_utc(value: Any) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run_token(value: Any) -> str:
    return _utc(value).strftime("%Y%m%dT%H%M%SZ")


def local_date_labels(valid_times: Any) -> np.ndarray:
    """Transforma momente UTC in etichete de data Europe/Bucharest."""
    index = pd.to_datetime(np.asarray(valid_times).reshape(-1), utc=True, errors="raise")
    return index.tz_convert(LOCAL_TIMEZONE).strftime("%Y-%m-%d").to_numpy()


def _daily_reduce(values: np.ndarray, valid_times: Any, reducer: str) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("valorile trebuie sa aiba forma timp x grila")
    labels = local_date_labels(valid_times)
    if len(labels) != values.shape[0]:
        raise ValueError("numarul momentelor nu corespunde valorilor")
    days = np.unique(labels)
    operation = np.fmin.reduce if reducer == "min" else np.fmax.reduce
    result = np.stack([operation(values[labels == day], axis=0) for day in days])
    return days, result


def _shift_times(valid_times: Any, minutes: int) -> np.ndarray:
    values = pd.to_datetime(np.asarray(valid_times), utc=True)
    return (values + pd.Timedelta(minutes=minutes)).to_numpy(dtype="datetime64[ns]")


def complete_local_days(valid_times: Any, interval_hours: int, shift_minutes: int = 0) -> np.ndarray:
    """Zile locale acoperite integral de seria regulată, inclusiv la schimbarea orei."""
    labels = local_date_labels(_shift_times(valid_times, shift_minutes))
    complete = []
    for day in np.unique(labels):
        start = pd.Timestamp(day, tz=LOCAL_TIMEZONE)
        end = start + pd.DateOffset(days=1)
        hours = (end.tz_convert("UTC") - start.tz_convert("UTC")).total_seconds() / 3600
        expected = max(1, round(hours / interval_hours))
        if int((labels == day).sum()) >= expected:
            complete.append(day)
    return np.asarray(complete)


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Medie mobilă strictă: fereastra este validă numai cu toate valorile finite."""
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or window < 1:
        raise ValueError("fereastră mobilă invalidă")
    result = np.full(values.shape, np.nan, dtype=np.float64)
    if values.shape[0] < window:
        return result
    valid = np.isfinite(values)
    sums = np.vstack([np.zeros((1, values.shape[1])), np.cumsum(np.where(valid, values, 0), axis=0)])
    counts = np.vstack([
        np.zeros((1, values.shape[1]), dtype=np.int32),
        np.cumsum(valid, axis=0),
    ])
    window_sums = sums[window:] - sums[:-window]
    window_counts = counts[window:] - counts[:-window]
    result[window - 1:] = np.where(window_counts == window, window_sums / window, np.nan)
    return result


def aggregate_weather_daily(
    interval_min_k: np.ndarray, interval_max_k: np.ndarray, valid_times: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Agrega extremele intervalelor ECMWF si converteste Kelvin in Celsius."""
    interval_min_k = np.asarray(interval_min_k, dtype=np.float64)
    interval_max_k = np.asarray(interval_max_k, dtype=np.float64)
    if interval_min_k.shape != interval_max_k.shape:
        raise ValueError("campurile minime si maxime au forme diferite")
    # Câmpul descrie intervalul precedent de 3 ore; data mijlocului intervalului
    # evită atribuirea segmentului 21–24 zilei următoare.
    interval_midpoints = _shift_times(valid_times, -90)
    days_min, daily_min = _daily_reduce(interval_min_k - 273.15, interval_midpoints, "min")
    days_max, daily_max = _daily_reduce(interval_max_k - 273.15, interval_midpoints, "max")
    if not np.array_equal(days_min, days_max):
        raise ValueError("zilele campurilor minime si maxime difera")
    return days_min, daily_min, daily_max


def aqi_rank(values: Any, pollutant: str) -> np.ndarray:
    """Returneaza rangul european 0..5; valorile lipsa primesc -1."""
    if pollutant not in AQI_THRESHOLDS:
        raise ValueError(f"poluant necunoscut: {pollutant}")
    array = np.asarray(values, dtype=np.float64)
    rank = np.full(array.shape, -1, dtype=np.int8)
    valid = np.isfinite(array)
    rank[valid] = np.searchsorted(AQI_THRESHOLDS[pollutant], array[valid], side="left").astype(
        np.int8
    )
    return rank


def aggregate_air_daily(
    series: dict[str, tuple[np.ndarray, Any]],
) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]:
    """Agrega maxime orare si calculeaza cea mai rea categorie dintre poluanti."""
    if not series:
        raise ValueError("nu exista serii de poluare")
    daily: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    daily_ranks: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    ngrid: int | None = None
    for pollutant, (values, times) in series.items():
        values = np.asarray(values, dtype=np.float64)
        if ngrid is None:
            ngrid = values.shape[1]
        elif values.shape[1] != ngrid:
            raise ValueError("grilele poluantilor au dimensiuni diferite")
        daily[pollutant] = _daily_reduce(values, times, "max")
        rank_basis = rolling_mean(values, 24) if pollutant in {"pm25", "pm10"} else values
        daily_ranks[pollutant] = _daily_reduce(
            aqi_rank(rank_basis, pollutant).astype(np.float64), times, "max"
        )

    all_days = np.unique(np.concatenate([item[0] for item in daily.values()]))
    maxima: dict[str, np.ndarray] = {}
    assert ngrid is not None
    for pollutant in series:
        days, values = daily[pollutant]
        aligned = np.full((len(all_days), ngrid), np.nan, dtype=np.float64)
        positions = np.searchsorted(all_days, days)
        aligned[positions] = values
        maxima[pollutant] = aligned

    aligned_ranks = []
    for pollutant in series:
        days, values = daily_ranks[pollutant]
        aligned = np.full((len(all_days), ngrid), -1, dtype=np.int8)
        aligned[np.searchsorted(all_days, days)] = values.astype(np.int8)
        aligned_ranks.append(aligned)
    worst = np.stack(aligned_ranks).max(axis=0).astype(np.int8)
    return all_days, maxima, worst


def nearest_grid_map(
    cell_ids: Any,
    cell_lon: Any,
    cell_lat: Any,
    grid_ids: Any,
    grid_lon: Any,
    grid_lat: Any,
) -> pd.DataFrame:
    """Asociaza centroizii cu cel mai apropiat nod folosind distante pe sfera."""

    def unit_xyz(lon: Any, lat: Any) -> np.ndarray:
        lon_rad = np.deg2rad(np.asarray(lon, dtype=np.float64))
        lat_rad = np.deg2rad(np.asarray(lat, dtype=np.float64))
        cos_lat = np.cos(lat_rad)
        return np.column_stack(
            (cos_lat * np.cos(lon_rad), cos_lat * np.sin(lon_rad), np.sin(lat_rad))
        )

    grid_ids = np.asarray(grid_ids)
    if len(grid_ids) == 0:
        raise ValueError("grila sursei este goala")
    distances, positions = cKDTree(unit_xyz(grid_lon, grid_lat)).query(
        unit_xyz(cell_lon, cell_lat), k=1
    )
    if float(np.max(distances)) > 0.02:
        raise ValueError("unele celule sunt prea departe de grila sursei")
    result = pd.DataFrame(
        {
            "cell_id": np.asarray(cell_ids, dtype=np.uint32),
            "grid_id": grid_ids[np.asarray(positions)].astype(np.uint32),
        }
    )
    if result["cell_id"].duplicated().any():
        raise ValueError("cell_id nu este unic in core.parquet")
    return result.sort_values("cell_id", ignore_index=True)


def interpolated_grid_map(
    cell_ids: Any,
    cell_lon: Any,
    cell_lat: Any,
    grid_ids: Any,
    grid_lon: Any,
    grid_lat: Any,
) -> pd.DataFrame:
    """Asociaza fiecare celula cu nodul nativ cel mai apropiat (``grid_id``, ca
    pana acum) si, suplimentar, cu cele patru noduri vecine + ponderile de
    interpolare biliniara (``grid_id_a..d`` / ``weight_a..d``).

    Grila nativa ECMWF/CAMS e rara (~0.1-0.25 grade fata de grila de 1 km a
    recensamantului), asa ca a atribui fiecarei celule doar cea mai apropiata
    valoare produce pete dreptunghiulare mari (marginile celulelor Voronoi ale
    grilei native), vizibile mai ales la pragurile de caniculă/ger. Interpolarea
    biliniara netezeste tranzitia intre celulele de 1 km.

    Daca grila native nu e un dreptunghi complet (gauri, margine neregulata),
    revine sigur la comportamentul de dinainte: doar cel mai apropiat nod,
    pondere 1.
    """
    cell_ids = np.asarray(cell_ids, dtype=np.uint32)
    cell_lon = np.asarray(cell_lon, dtype=np.float64)
    cell_lat = np.asarray(cell_lat, dtype=np.float64)
    grid_ids = np.asarray(grid_ids, dtype=np.uint32)
    grid_lon = np.asarray(grid_lon, dtype=np.float64)
    grid_lat = np.asarray(grid_lat, dtype=np.float64)

    nearest = nearest_grid_map(cell_ids, cell_lon, cell_lat, grid_ids, grid_lon, grid_lat)
    nearest_by_cell = nearest.set_index("cell_id")["grid_id"].reindex(cell_ids).to_numpy()

    lons_unique = np.unique(grid_lon)
    lats_unique = np.unique(grid_lat)
    rectangular = len(lons_unique) * len(lats_unique) == len(grid_ids) and len(lons_unique) >= 2 and len(lats_unique) >= 2
    if rectangular:
        id_grid = np.full((len(lats_unique), len(lons_unique)), -1, dtype=np.int64)
        id_grid[np.searchsorted(lats_unique, grid_lat), np.searchsorted(lons_unique, grid_lon)] = grid_ids
        rectangular = bool(np.all(id_grid >= 0))

    if rectangular:
        dlon = float(lons_unique[1] - lons_unique[0])
        dlat = float(lats_unique[1] - lats_unique[0])
        lon_f = np.clip((cell_lon - lons_unique[0]) / dlon, 0.0, len(lons_unique) - 1.0)
        lat_f = np.clip((cell_lat - lats_unique[0]) / dlat, 0.0, len(lats_unique) - 1.0)
        j0 = np.clip(np.floor(lon_f).astype(np.int64), 0, len(lons_unique) - 2)
        i0 = np.clip(np.floor(lat_f).astype(np.int64), 0, len(lats_unique) - 2)
        wj = np.clip(lon_f - j0, 0.0, 1.0)
        wi = np.clip(lat_f - i0, 0.0, 1.0)

        gid_a, gid_b = id_grid[i0, j0], id_grid[i0, j0 + 1]
        gid_c, gid_d = id_grid[i0 + 1, j0], id_grid[i0 + 1, j0 + 1]
        w_a, w_b = (1 - wi) * (1 - wj), (1 - wi) * wj
        w_c, w_d = wi * (1 - wj), wi * wj
    else:
        gid_a = gid_b = gid_c = gid_d = nearest_by_cell.astype(np.int64)
        w_a = np.ones_like(cell_lon)
        w_b = w_c = w_d = np.zeros_like(cell_lon)

    result = pd.DataFrame(
        {
            "cell_id": cell_ids,
            "grid_id": nearest_by_cell.astype(np.uint32),
            "grid_id_a": np.asarray(gid_a, dtype=np.uint32),
            "grid_id_b": np.asarray(gid_b, dtype=np.uint32),
            "grid_id_c": np.asarray(gid_c, dtype=np.uint32),
            "grid_id_d": np.asarray(gid_d, dtype=np.uint32),
            "weight_a": np.asarray(w_a, dtype=np.float32),
            "weight_b": np.asarray(w_b, dtype=np.float32),
            "weight_c": np.asarray(w_c, dtype=np.float32),
            "weight_d": np.asarray(w_d, dtype=np.float32),
        }
    )
    if result["cell_id"].duplicated().any():
        raise ValueError("cell_id nu este unic in core.parquet")
    return result.sort_values("cell_id", ignore_index=True)


def air_candidate_dates(today: date, catalogue_latest: date | None, count: int = 3) -> list[date]:
    """Date CAMS de incercat, in ordine descrescatoare, fara date viitoare."""
    latest = min(today, catalogue_latest) if catalogue_latest else today - timedelta(days=1)
    return [latest - timedelta(days=offset) for offset in range(count)]


def _normal(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _find_coordinate(ds: xr.Dataset, kind: str) -> xr.DataArray:
    preferred = ("latitude", "lat", "navlat") if kind == "lat" else ("longitude", "lon", "navlon")
    variables = list(ds.coords) + [name for name in ds.variables if name not in ds.coords]
    for wanted in preferred:
        for name in variables:
            if _normal(name) == wanted:
                return ds[name]
    for name in variables:
        variable = ds[name]
        attrs = " ".join(
            str(variable.attrs.get(key, "")) for key in ("standard_name", "long_name", "axis", "units")
        ).lower()
        if kind == "lat" and ("latitude" in attrs or "degrees_north" in attrs):
            return variable
        if kind == "lon" and ("longitude" in attrs or "degrees_east" in attrs):
            return variable
    raise ValueError(f"coordonata {kind} lipseste")


def _normal_lon(values: Any) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return (values + 180.0) % 360.0 - 180.0


def _crop_rectilinear(ds: xr.Dataset) -> xr.Dataset:
    """Taie devreme grilele 1D, ca GRIB-ul global sa nu fie incarcat integral."""
    lat = _find_coordinate(ds, "lat")
    lon = _find_coordinate(ds, "lon")
    if lat.ndim != 1 or lon.ndim != 1 or lat.dims[0] == lon.dims[0]:
        return ds
    lat_values = np.asarray(lat.values, dtype=np.float64)
    lon_values = _normal_lon(lon.values)
    lat_index = np.flatnonzero((lat_values >= BOX["south"]) & (lat_values <= BOX["north"]))
    lon_index = np.flatnonzero((lon_values >= BOX["west"]) & (lon_values <= BOX["east"]))
    if len(lat_index) == 0 or len(lon_index) == 0:
        raise ValueError("grila nu intersecteaza caseta Romaniei")
    return ds.isel({lat.dims[0]: lat_index, lon.dims[0]: lon_index})


def _datetime_array(values: Any) -> np.ndarray | None:
    array = np.asarray(values)
    if array.dtype.kind not in "MmOU":
        return None
    try:
        parsed = pd.to_datetime(array.reshape(-1), utc=True, errors="raise")
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.tz_convert(None).to_numpy(dtype="datetime64[ns]").reshape(array.shape)


def _time_axis(
    da: xr.DataArray,
    ds: xr.Dataset,
    spatial_dims: tuple[str, ...],
    fallback_base: datetime | None = None,
) -> tuple[str | None, np.ndarray]:
    candidates: list[tuple[str, xr.DataArray]] = []
    for name in ("valid_time", "validtime", "forecast_time", "time", "datetime"):
        if name in da.coords:
            candidates.append((name, da.coords[name]))
        elif name in ds.coords:
            candidates.append((name, ds.coords[name]))
    candidates.extend((name, coord) for name, coord in da.coords.items() if name not in {x[0] for x in candidates})

    scalar_base: np.datetime64 | None = None
    for _, coord in candidates:
        parsed = _datetime_array(coord.values)
        if parsed is None:
            continue
        varying_dims = [
            dim
            for dim in coord.dims
            if dim in da.dims and dim not in spatial_dims and da.sizes[dim] > 1
        ]
        if len(varying_dims) == 1 and all(
            dim == varying_dims[0] or da.sizes.get(dim, 1) == 1 for dim in coord.dims
        ):
            return varying_dims[0], parsed.reshape(-1)
        if coord.ndim == 0 or all(da.sizes.get(dim, 1) == 1 for dim in coord.dims):
            scalar_base = parsed.reshape(-1)[0]

    if scalar_base is None and fallback_base is not None:
        scalar_base = np.datetime64(_utc(fallback_base).replace(tzinfo=None), "ns")

    non_spatial = [dim for dim in da.dims if dim not in spatial_dims]
    for dim in non_spatial:
        coord = da.coords.get(dim, ds.coords.get(dim))
        if coord is None or coord.ndim != 1:
            continue
        name = _normal(dim)
        units = str(coord.attrs.get("units", "")).lower()
        values = np.asarray(coord.values)
        if values.dtype.kind == "m":
            if scalar_base is None:
                continue
            return dim, scalar_base + values.astype("timedelta64[ns]")
        if scalar_base is not None and (name in {"step", "leadtime", "leadtimehour", "forecastperiod"} or "hour" in units):
            hours = values.astype(np.float64)
            return dim, scalar_base + (hours * 3_600_000_000_000).astype("timedelta64[ns]")

    if scalar_base is not None and all(da.sizes[dim] == 1 for dim in non_spatial):
        return None, np.asarray([scalar_base], dtype="datetime64[ns]")
    raise ValueError(f"axa timp nu poate fi identificata pentru {da.name}")


def _spatial_cube(
    da: xr.DataArray, ds: xr.Dataset, fallback_base: datetime | None = None
) -> SpatialCube:
    lat_coord = _find_coordinate(ds, "lat")
    lon_coord = _find_coordinate(ds, "lon")
    if lat_coord.ndim == lon_coord.ndim == 1 and lat_coord.dims[0] != lon_coord.dims[0]:
        spatial_dims = (lat_coord.dims[0], lon_coord.dims[0])
        lon_grid, lat_grid = np.meshgrid(_normal_lon(lon_coord.values), lat_coord.values)
    elif lat_coord.ndim == lon_coord.ndim == 1 and lat_coord.dims == lon_coord.dims:
        spatial_dims = lat_coord.dims
        lat_grid = np.asarray(lat_coord.values)
        lon_grid = _normal_lon(lon_coord.values)
    elif lat_coord.ndim == lon_coord.ndim == 2 and lat_coord.dims == lon_coord.dims:
        spatial_dims = lat_coord.dims
        lat_grid = np.asarray(lat_coord.values)
        lon_grid = _normal_lon(lon_coord.values)
    else:
        raise ValueError("conventia coordonatelor spatiale nu este suportata")
    if any(dim not in da.dims for dim in spatial_dims):
        raise ValueError(f"{da.name} nu foloseste dimensiunile grilei")

    time_dim, times = _time_axis(da, ds, spatial_dims, fallback_base)
    for dim in tuple(da.dims):
        if dim not in spatial_dims and dim != time_dim:
            if da.sizes[dim] != 1:
                raise ValueError(f"dimensiune neasteptata {dim}={da.sizes[dim]} pentru {da.name}")
            da = da.isel({dim: 0}, drop=True)

    if time_dim is None:
        values = np.asarray(da.transpose(*spatial_dims).values, dtype=np.float64)[None, ...]
    else:
        values = np.asarray(da.transpose(time_dim, *spatial_dims).values, dtype=np.float64)
    values = values.reshape(values.shape[0], -1)
    lon_flat = np.asarray(lon_grid, dtype=np.float64).reshape(-1)
    lat_flat = np.asarray(lat_grid, dtype=np.float64).reshape(-1)
    inside = (
        (lat_flat >= BOX["south"])
        & (lat_flat <= BOX["north"])
        & (lon_flat >= BOX["west"])
        & (lon_flat <= BOX["east"])
    )
    if not inside.any():
        raise ValueError("grila nu contine puncte in caseta Romaniei")
    values = values[:, inside]
    lon_flat = lon_flat[inside]
    lat_flat = lat_flat[inside]

    # Ordinea canonica face grid_id stabil chiar daca fisierele inverseaza axele.
    order = np.lexsort((np.round(lon_flat, 7), -np.round(lat_flat, 7)))
    lon_flat = lon_flat[order]
    lat_flat = lat_flat[order]
    values = values[:, order]
    coordinates = np.column_stack((np.round(lon_flat, 7), np.round(lat_flat, 7)))
    if len(np.unique(coordinates, axis=0)) != len(coordinates):
        raise ValueError("grila contine coordonate duplicate")
    return SpatialCube(
        values=values,
        times=np.asarray(times, dtype="datetime64[ns]"),
        grid_ids=np.arange(len(lon_flat), dtype=np.uint32),
        lon=lon_flat,
        lat=lat_flat,
    )


def _find_data_var(ds: xr.Dataset, aliases: set[str]) -> xr.DataArray:
    normalized = {_normal(alias) for alias in aliases}
    for name, variable in ds.data_vars.items():
        names = {
            _normal(name),
            _normal(variable.attrs.get("GRIB_shortName", "")),
            _normal(variable.attrs.get("short_name", "")),
            _normal(variable.attrs.get("standard_name", "")),
        }
        if names & normalized:
            return variable
    raise ValueError(f"niciuna dintre variabilele {sorted(aliases)} nu exista")


def _same_grid(first: SpatialCube, second: SpatialCube) -> bool:
    return (
        np.array_equal(first.grid_ids, second.grid_ids)
        and np.allclose(first.lon, second.lon, rtol=0, atol=1e-7)
        and np.allclose(first.lat, second.lat, rtol=0, atol=1e-7)
    )


def _require_coverage(times: Any, expected: pd.DatetimeIndex, label: str) -> None:
    actual = pd.to_datetime(np.asarray(times), utc=True)
    # Pandas 3 păstrează rezoluția sursei (secunde/microsecunde/nanosecunde) în
    # `asi8`; normalizăm explicit înainte de comparație.
    actual_ns = set(actual.to_numpy(dtype="datetime64[ns]").astype(np.int64).tolist())
    expected_ns = expected.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    missing = sum(int(value) not in actual_ns for value in expected_ns)
    if missing:
        raise ValueError(f"{label}: lipsesc {missing} momente din prognoza")


def _weather_from_grib(path: Path, run_utc: datetime) -> tuple[pd.DataFrame, SpatialCube]:
    import cfgrib

    datasets = cfgrib.open_datasets(
        str(path), backend_kwargs={"indexpath": ""}, decode_timedelta=True
    )
    minimum: SpatialCube | None = None
    maximum: SpatialCube | None = None
    minimum_units = ""
    maximum_units = ""
    try:
        for raw in datasets:
            ds = _crop_rectilinear(raw)
            if minimum is None:
                try:
                    variable = _find_data_var(
                        ds,
                        {
                            "mn2t3",
                            "mn2t",
                            "minimum_2m_temperature_since_previous_post_processing",
                        },
                    )
                    minimum = _spatial_cube(variable, ds)
                    minimum_units = _normal(variable.attrs.get("units", ""))
                except ValueError:
                    pass
            if maximum is None:
                try:
                    variable = _find_data_var(
                        ds,
                        {
                            "mx2t3",
                            "mx2t",
                            "maximum_2m_temperature_since_previous_post_processing",
                        },
                    )
                    maximum = _spatial_cube(variable, ds)
                    maximum_units = _normal(variable.attrs.get("units", ""))
                except ValueError:
                    pass
    finally:
        for dataset in datasets:
            dataset.close()

    if minimum is None or maximum is None:
        raise ValueError("campurile ECMWF mn2t3/mx2t3 lipsesc din GRIB")

    if not _same_grid(minimum, maximum) or not np.array_equal(minimum.times, maximum.times):
        raise ValueError("campurile ECMWF min/max nu sunt aliniate")
    for units in (minimum_units, maximum_units):
        if units not in {"k", "kelvin"}:
            raise ValueError("unitatea temperaturii ECMWF nu este Kelvin")
    expected = pd.date_range(_utc(run_utc), periods=len(WEATHER_STEPS), freq="3h")
    expected = expected + pd.Timedelta(hours=3)
    _require_coverage(minimum.times, expected, "ECMWF")

    days, daily_min, daily_max = aggregate_weather_daily(
        minimum.values, maximum.values, minimum.times
    )
    complete = set(complete_local_days(minimum.times, 3, -90).tolist())
    keep = np.asarray([day in complete for day in days])
    days, daily_min, daily_max = days[keep], daily_min[keep], daily_max[keep]
    if len(days) == 0:
        raise ValueError("ECMWF nu conține nicio zi locală completă")
    ngrid = len(minimum.grid_ids)
    frame = pd.DataFrame(
        {
            "grid_id": np.tile(minimum.grid_ids, len(days)).astype(np.uint32),
            "valid_date": np.asarray(
                [date.fromisoformat(day) for day in np.repeat(days, ngrid)], dtype=object
            ),
            "tmin": daily_min.reshape(-1).astype(np.float32),
            "tmax": daily_max.reshape(-1).astype(np.float32),
        }
    )
    if frame.empty or (frame["tmin"] > frame["tmax"]).any():
        raise ValueError("agregarea temperaturii este invalida")
    return frame, minimum


POLLUTANT_ALIASES = {
    "pm25": {
        "pm2p5", "pm25", "pm2p5conc", "pm25conc", "particulatematter25um",
        "particulatematterlessthan25um",
    },
    "pm10": {"pm10", "pm10conc", "particulatematter10um", "particulatematterlessthan10um"},
    "no2": {"no2", "no2conc", "nitrogendioxide", "nitrogendioxideconc"},
    "o3": {"o3", "o3conc", "ozone", "ozoneconc"},
    "so2": {"so2", "so2conc", "sulfurdioxide", "sulphurdioxide", "sulphurdioxideconc"},
}


def _pollutant_for_var(name: str, variable: xr.DataArray, filename: str) -> str | None:
    pieces = [
        name,
        variable.attrs.get("standard_name", ""),
        variable.attrs.get("long_name", ""),
        variable.attrs.get("species", ""),
        Path(filename).stem,
    ]
    normalized = [_normal(piece) for piece in pieces if piece]
    if any(marker in item for item in normalized for marker in ("uncertainty", "spread", "stddev")):
        return None
    for pollutant, aliases in POLLUTANT_ALIASES.items():
        for alias in aliases:
            if any(item == alias or alias in item for item in normalized):
                return pollutant
    return None


def _concentration_factor(units: Any) -> float:
    text = str(units).lower().replace("µ", "u").replace("μ", "u").replace("³", "3")
    compact = re.sub(r"[\s*^{}()]+", "", text).replace("per", "/")
    if compact in {"ug/m3", "ugm-3", "ugm3", "microgram/m3", "microgramm-3", "microgrammes/m3"}:
        return 1.0
    if compact in {"mg/m3", "mgm-3", "mgm3"}:
        return 1_000.0
    if compact in {"g/m3", "gm-3", "gm3"}:
        return 1_000_000.0
    if compact in {"kg/m3", "kgm-3", "kgm3"}:
        return 1_000_000_000.0
    raise ValueError(f"unitate de concentratie nesuportata: {units!s}")


def _netcdf_files(archive: Path, directory: Path) -> list[Path]:
    if archive.stat().st_size > 500_000_000:
        raise ValueError("arhiva ADS depășește limita de 500 MB")
    if not zipfile.is_zipfile(archive):
        target = directory / "air.nc"
        shutil.copyfile(archive, target)
        return [target]
    files: list[Path] = []
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 100 or sum(info.file_size for info in members) > 1_000_000_000:
            raise ValueError("conținutul arhivei ADS depășește limitele de siguranță")
        for index, info in enumerate(members):
            suffix = Path(info.filename).suffix.lower()
            if info.is_dir() or suffix not in {".nc", ".nc4", ".cdf"}:
                continue
            target = directory / f"{index:03d}_{Path(info.filename).name}"
            with bundle.open(info) as source, open(target, "wb") as destination:
                shutil.copyfileobj(source, destination)
            files.append(target)
    if not files:
        raise ValueError("arhiva ADS nu contine fisiere NetCDF")
    return files


def _air_from_archive(
    archive: Path, run_utc: datetime
) -> tuple[pd.DataFrame, SpatialCube]:
    chunks: dict[str, list[SpatialCube]] = {pollutant: [] for pollutant in POLLUTANTS}
    reference: SpatialCube | None = None
    with tempfile.TemporaryDirectory(prefix="ulr_air_extract_") as temporary:
        for path in _netcdf_files(archive, Path(temporary)):
            with xr.open_dataset(path, decode_times=True) as raw:
                ds = _crop_rectilinear(raw)
                for name, variable in ds.data_vars.items():
                    pollutant = _pollutant_for_var(name, variable, path.name)
                    if pollutant is None or variable.ndim < 2:
                        continue
                    cube = _spatial_cube(variable, ds, run_utc)
                    factor = _concentration_factor(variable.attrs.get("units", ""))
                    values = np.maximum(cube.values * factor, 0.0)
                    cube = SpatialCube(values, cube.times, cube.grid_ids, cube.lon, cube.lat)
                    if reference is None:
                        reference = cube
                    elif not _same_grid(reference, cube):
                        raise ValueError("grilele NetCDF CAMS nu sunt aliniate")
                    chunks[pollutant].append(cube)

    missing_pollutants = [pollutant for pollutant, items in chunks.items() if not items]
    if missing_pollutants:
        raise ValueError(f"poluanti CAMS lipsa: {', '.join(missing_pollutants)}")
    assert reference is not None
    expected = pd.date_range(_utc(run_utc), periods=97, freq="h")
    series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for pollutant, items in chunks.items():
        values = np.concatenate([item.values for item in items], axis=0)
        times = np.concatenate([item.times for item in items])
        _require_coverage(times, expected, f"CAMS {pollutant}")
        series[pollutant] = (values, times)

    days, maxima, worst = aggregate_air_daily(series)
    complete = set(complete_local_days(reference.times, 1).tolist())
    keep = np.asarray([day in complete for day in days])
    days = days[keep]
    maxima = {pollutant: values[keep] for pollutant, values in maxima.items()}
    worst = worst[keep]
    if len(days) == 0:
        raise ValueError("CAMS nu conține nicio zi locală completă")
    ngrid = len(reference.grid_ids)
    valid = np.any(
        np.stack([np.isfinite(maxima[pollutant]) for pollutant in POLLUTANTS]), axis=0
    )
    rows = valid.reshape(-1)
    data: dict[str, Any] = {
        "grid_id": np.tile(reference.grid_ids, len(days))[rows].astype(np.uint32),
        "valid_date": np.asarray(
            [date.fromisoformat(day) for day in np.repeat(days, ngrid)], dtype=object
        )[rows],
        "aqi_rank": worst.reshape(-1)[rows].astype(np.int8),
    }
    for pollutant in POLLUTANTS:
        data[AIR_FIELDS[pollutant]] = maxima[pollutant].reshape(-1)[rows].astype(np.float32)
    frame = pd.DataFrame(data)
    if frame.empty or not frame["aqi_rank"].between(0, 5).all():
        raise ValueError("agregarea AQI este invalida")
    return frame, reference


def _load_core() -> pd.DataFrame:
    path = DATA_OUT / "core.parquet"
    if not path.exists():
        raise SourceError("Lipsește core.parquet; rulați mai întâi pipeline-ul ETL.")
    core = pd.read_parquet(path, columns=["cell_id", "lon", "lat"])
    if core.empty or core["cell_id"].duplicated().any():
        raise SourceError("core.parquet nu conține o grilă validă.")
    if not np.isfinite(core[["lon", "lat"]].to_numpy()).all():
        raise SourceError("core.parquet conține centroizi nevalizi.")
    return core


def _relative(path: Path) -> str:
    return path.relative_to(DATA_OUT).as_posix()


def _write_parquet_temp(frame: pd.DataFrame) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".parquet.part", prefix=".", dir=FORECAST_DIR, delete=False
    )
    path = Path(handle.name)
    handle.close()
    try:
        frame.to_parquet(path, index=False, compression="zstd")
        with open(path, "rb") as stream:
            os.fsync(stream.fileno())
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _publish_immutable_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = _write_parquet_temp(frame)
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = pd.read_parquet(path)
            if (
                list(existing.columns) != list(frame.columns)
                or len(existing) != len(frame)
                or not existing.equals(frame)
            ):
                raise SourceError(f"Fișierul imuabil existent {path.name} nu corespunde rulării.")
    finally:
        temporary.unlink(missing_ok=True)


def _mapping(core: pd.DataFrame, cube: SpatialCube, source: str) -> Path:
    mapping = interpolated_grid_map(
        core["cell_id"], core["lon"], core["lat"], cube.grid_ids, cube.lon, cube.lat
    )
    fingerprint = hashlib.sha256()
    fingerprint.update(core["cell_id"].to_numpy(dtype=np.uint32).tobytes())
    fingerprint.update(np.round(cube.lon, 7).astype(np.float64).tobytes())
    fingerprint.update(np.round(cube.lat, 7).astype(np.float64).tobytes())
    # prefix distinct de vechiul "_map_" (schema veche, doar nearest-neighbor) ca
    # sa nu se refoloseasca din greseala un fisier imuabil cu schema veche.
    path = FORECAST_DIR / f"{source}_bimap_{fingerprint.hexdigest()[:12]}.parquet"
    if not path.exists():
        _publish_immutable_parquet(mapping, path)
    return path


def _source_entry(source: str, run_utc: datetime, data_path: Path, map_path: Path, frame: pd.DataFrame) -> dict:
    metadata = SOURCE_META[source]
    today = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).date()
    days = sorted({value.isoformat() for value in frame["valid_date"] if value >= today})
    if not days:
        raise SourceError(f"Rularea {source} nu mai conține zile curente sau viitoare.")
    return {
        "ok": True,
        "provider": metadata["provider"],
        "model": metadata["model"],
        "run_utc": _iso_utc(run_utc),
        "data_file": _relative(data_path),
        "map_file": _relative(map_path),
        "days": days,
        "resolution": metadata["resolution"],
        "attribution": metadata["attribution"],
    }


def _refresh_weather(core: pd.DataFrame) -> dict:
    from ecmwf.opendata import Client

    handle = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".grib2", prefix="ulr_weather_", delete=False
    )
    grib_path = Path(handle.name)
    handle.close()
    try:
        client = Client(source="ecmwf", model="ifs", resol="0p25")
        original_get, original_head = client.session.get, client.session.head
        client.session.get = lambda *args, **kwargs: original_get(
            *args, timeout=kwargs.pop("timeout", (20, 180)), **kwargs
        )
        client.session.head = lambda *args, **kwargs: original_head(
            *args, timeout=kwargs.pop("timeout", (20, 180)), **kwargs
        )
        result = client.retrieve(
            stream="oper",
            type="fc",
            levtype="sfc",
            step=WEATHER_STEPS,
            param=["mn2t3", "mx2t3"],
            target=str(grib_path),
        )
        run_utc = _utc(result.datetime)
        frame, cube = _weather_from_grib(grib_path, run_utc)
        map_path = _mapping(core, cube, "weather")
        data_path = FORECAST_DIR / f"weather_{_run_token(run_utc)}_daily2.parquet"
        _publish_immutable_parquet(frame, data_path)
        return _source_entry("weather", run_utc, data_path, map_path, frame)
    finally:
        grib_path.unlink(missing_ok=True)


def _catalogue_latest_air_date(ads_url: str) -> date | None:
    url = (
        ads_url.rstrip("/")
        + f"/catalogue/v1/collections/{ADS_DATASET}"
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=ADS_CATALOGUE_TIMEOUT) as response:
            payload = json.load(response)
        end = payload["extent"]["temporal"]["interval"][0][1]
        return _utc(end).date()
    except Exception:
        return None


def _ads_request(run_date: date) -> dict[str, Any]:
    return {
        "variable": [
            "particulate_matter_2.5um",
            "particulate_matter_10um",
            "nitrogen_dioxide",
            "ozone",
            "sulphur_dioxide",
        ],
        "model": ["ensemble"],
        "level": ["0"],
        "date": [run_date.isoformat()],
        "type": ["forecast"],
        "time": ["00:00"],
        "leadtime_hour": [str(hour) for hour in range(97)],
        "data_format": "netcdf_zip",
        "area": [BOX["north"], BOX["west"], BOX["south"], BOX["east"]],
    }


def _refresh_air(core: pd.DataFrame) -> dict:
    key = os.environ.get("ADS_API_KEY", "").strip()
    if not key:
        raise SourceError("ADS_API_KEY lipsește; produsul de aer anterior a fost păstrat.")
    ads_url = os.environ.get("ADS_API_URL", ADS_DEFAULT_URL).strip() or ADS_DEFAULT_URL
    parsed_url = urlparse(ads_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise SourceError("ADS_API_URL trebuie să fie un URL HTTPS valid.")

    import cdsapi

    client = cdsapi.Client(
        url=ads_url,
        key=key,
        quiet=True,
        progress=False,
        timeout=180,
        retry_max=3,
        sleep_max=20,
    )
    latest = _catalogue_latest_air_date(ads_url)
    for candidate in air_candidate_dates(datetime.now(timezone.utc).date(), latest):
        handle = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".netcdf.zip", prefix="ulr_air_", delete=False
        )
        archive = Path(handle.name)
        handle.close()
        try:
            client.retrieve(ADS_DATASET, _ads_request(candidate), str(archive))
            run_utc = datetime(candidate.year, candidate.month, candidate.day, tzinfo=timezone.utc)
            frame, cube = _air_from_archive(archive, run_utc)
            map_path = _mapping(core, cube, "air")
            data_path = FORECAST_DIR / f"air_{_run_token(run_utc)}_aqi2.parquet"
            _publish_immutable_parquet(frame, data_path)
            return _source_entry("air", run_utc, data_path, map_path, frame)
        except SourceError:
            raise
        except Exception:
            # Mesajele ADS pot include detalii de autentificare; nu le propagam.
            continue
        finally:
            archive.unlink(missing_ok=True)
    raise SourceError("ADS nu a furnizat o rulare CAMS validă; produsul anterior a fost păstrat.")


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return payload if payload.get("schema_version") == 1 else {}
    except (OSError, ValueError, TypeError):
        return {}


def _valid_relative_file(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    return (DATA_OUT / path).is_file()


def _failed_source(source: str, previous: dict[str, Any], error: str) -> dict[str, Any]:
    old = previous.get("sources", {}).get(source, {})
    if _valid_relative_file(old.get("data_file")) and _valid_relative_file(old.get("map_file")):
        entry = dict(old)
    else:
        metadata = SOURCE_META[source]
        entry = {
            "provider": metadata["provider"],
            "model": metadata["model"],
            "run_utc": None,
            "data_file": None,
            "map_file": None,
            "days": [],
            "resolution": metadata["resolution"],
            "attribution": metadata["attribution"],
        }
    entry["ok"] = False
    entry["error"] = error
    today = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()
    entry["days"] = [day for day in entry.get("days", []) if day >= today]
    return entry


def _previous_data_path(previous: dict[str, Any], source: str) -> Path | None:
    value = previous.get("sources", {}).get(source, {}).get("data_file")
    return DATA_OUT / value if _valid_relative_file(value) else None


def _prune_runs(source: str, protected: set[Path]) -> None:
    candidates = sorted(FORECAST_DIR.glob(f"{source}_[0-9]*.parquet"), reverse=True)
    protected = {path.resolve() for path in protected}
    keep = [path for path in candidates if path.resolve() in protected]
    keep.extend(path for path in candidates if path not in keep and len(keep) < 4)
    keep_set = {path.resolve() for path in keep[:4]}
    for path in candidates:
        if path.resolve() not in keep_set:
            path.unlink(missing_ok=True)


def _atomic_manifest(payload: dict[str, Any]) -> None:
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json.part", prefix=".manifest_",
        dir=FORECAST_DIR, delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, MANIFEST_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def _refresh_locked() -> bool:
    previous = _load_manifest()
    sources: dict[str, dict[str, Any]] = {}
    for source in SOURCE_META:
        old = previous.get("sources", {}).get(source, {})
        if _valid_relative_file(old.get("data_file")) and _valid_relative_file(old.get("map_file")):
            sources[source] = dict(old)
        else:
            sources[source] = _failed_source(source, previous, "Actualizarea sursei este în curs.")
    try:
        core = _load_core()
    except Exception:
        core = None
    updated = False

    def run_source(source: str, refresher):
        if core is None:
            raise SourceError("core.parquet nu poate fi citit; produsul anterior a fost păstrat.")
        return refresher(core)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="forecast") as executor:
        jobs = {
            executor.submit(run_source, source, refresher): source
            for source, refresher in (("weather", _refresh_weather), ("air", _refresh_air))
        }
        for job in as_completed(jobs):
            source = jobs[job]
            try:
                next_entry = job.result()
                old_run = previous.get("sources", {}).get(source, {}).get("run_utc")
                if old_run and next_entry.get("run_utc") and _utc(next_entry["run_utc"]) < _utc(old_run):
                    raise SourceError(f"Rularea {source} disponibilă este mai veche decât produsul publicat.")
                sources[source] = next_entry
                updated = True
                _log(
                    f"{source}: rulare {sources[source]['run_utc']}, "
                    f"{len(sources[source]['days'])} zile"
                )
                new_path = DATA_OUT / sources[source]["data_file"]
                old_path = _previous_data_path(previous, source)
                protected = {new_path} | ({old_path} if old_path is not None else set())
                try:
                    _prune_runs(source, protected)
                except OSError:
                    _log(f"{source}: fișierele vechi nu au putut fi curățate")
            except SourceError as error:
                sources[source] = _failed_source(source, previous, str(error))
                _log(f"{source}: {error}")
            except Exception as error:
                message = f"Actualizarea {source} a eșuat; produsul anterior a fost păstrat."
                sources[source] = _failed_source(source, previous, message)
                detail = f" ({type(error).__name__}: {error})" if source == "weather" else ""
                _log(message + detail)

            # Fiecare sursă terminată devine vizibilă fără să aștepte cealaltă.
            _atomic_manifest({
                "schema_version": 1,
                "generated_utc": _iso_utc(datetime.now(timezone.utc)),
                "sources": sources,
                "products": _build_products(sources),
            })

    _log("manifest.json publicat atomic")
    return updated


def refresh() -> bool:
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_OUT / "live" / ".forecast-refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _log("există deja o actualizare în curs; această rulare este omisă")
            return False
        return _refresh_locked()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    if mode not in {"once", "serve"}:
        sys.exit("folosire: python -m ulr_pipeline.forecast_live [once|serve]")
    if mode == "once":
        if not refresh():
            sys.exit(1)
        return
    _log(f"pornesc bucla de prognoze (interval {INTERVAL}s)")
    current = _load_manifest()
    sources = current.get("sources", {})
    if current.get("generated_utc") and all(
        _valid_relative_file(sources.get(source, {}).get("data_file")) for source in SOURCE_META
    ):
        age = (datetime.now(timezone.utc) - _utc(current["generated_utc"])).total_seconds()
        wait = max(0, INTERVAL - int(age))
        if wait:
            _log(f"produsele sunt recente; următoarea actualizare peste {wait}s")
            time.sleep(wait)
    while True:
        try:
            refresh()
        except Exception:
            _log("actualizarea internă a eșuat; reîncerc la următorul interval")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
