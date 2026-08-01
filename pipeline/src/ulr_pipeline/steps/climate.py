"""Agregate climatice per celulă din grilele zilnice MeteoRomania (ian–iul 2026).

Eșantionare nearest-neighbor la centroidele celulelor (grilele climatice au ~1 km,
comparabil cu grila noastră). Agregatele se calculează pe blocuri de timp pentru a
limita memoria. Se produc și serii zilnice medii pe județ pentru graficele din
aplicație.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..config import SRC, STAGING
from ..grid import load_cells

BLOCK = 32  # zile per bloc citit


def _nearest_idx(coord: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Indexul celui mai apropiat punct de grilă (coordonată 1D uniformă, orice sens)."""
    step = coord[1] - coord[0]
    idx = np.rint((values - coord[0]) / step).astype(np.int64)
    return np.clip(idx, 0, len(coord) - 1)


class Accum:
    """Acumulator online pe zile pentru un set de celule."""

    def __init__(self, n: int, thresholds: dict[str, tuple[str, float]]):
        self.sum = np.zeros(n, dtype=np.float64)
        self.cnt = np.zeros(n, dtype=np.int32)
        self.max = np.full(n, -np.inf, dtype=np.float32)
        self.thr = {k: (op, v, np.zeros(n, dtype=np.int32)) for k, (op, v) in thresholds.items()}

    def add(self, vals: np.ndarray) -> None:  # vals: (t, n)
        valid = np.isfinite(vals)
        self.sum += np.where(valid, vals, 0).sum(axis=0)
        self.cnt += valid.sum(axis=0)
        self.max = np.maximum(self.max, np.where(valid, vals, -np.inf).max(axis=0))
        for _, (op, v, acc) in self.thr.items():
            hit = (vals >= v) if op == ">=" else (vals < v)
            acc += (hit & valid).sum(axis=0)

    def mean(self) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(self.cnt > 0, self.sum / self.cnt, np.nan).astype(np.float32)


def _process(path, var: str, lons: np.ndarray, lats: np.ndarray,
             county_codes: np.ndarray, n_counties: int,
             thresholds: dict[str, tuple[str, float]]):
    ds = xr.open_dataset(path)
    da = ds[var]
    ix = _nearest_idx(da["lon"].values, lons)
    iy = _nearest_idx(da["lat"].values, lats)

    n = len(lons)
    acc = Accum(n, thresholds)
    county_rows = []
    dates = pd.to_datetime(da["time"].values).normalize()

    in_county = county_codes >= 0
    cc = county_codes[in_county]

    for start in range(0, da.sizes["time"], BLOCK):
        block = da.isel(time=slice(start, start + BLOCK)).values.astype(np.float32)
        vals = block[:, iy, ix]  # (t, n_celule)
        acc.add(vals)
        for t in range(vals.shape[0]):
            v = vals[t][in_county]
            ok = np.isfinite(v)
            s = np.bincount(cc[ok], weights=v[ok], minlength=n_counties)
            k = np.bincount(cc[ok], minlength=n_counties)
            with np.errstate(invalid="ignore", divide="ignore"):
                county_rows.append(np.where(k > 0, s / k, np.nan))
        del block, vals
    ds.close()

    county_daily = pd.DataFrame(
        np.asarray(county_rows, dtype=np.float32),
        index=pd.Index(dates, name="date"),
    )
    return acc, county_daily


def step_climate() -> None:
    cells = load_cells(["cell_id", "lon", "lat"])
    admin = pd.read_parquet(STAGING / "admin.parquet", columns=["cell_id", "county_mn"])
    cells = cells.merge(admin, on="cell_id", how="left")
    lons, lats = cells["lon"].to_numpy(), cells["lat"].to_numpy()

    county_cat = cells["county_mn"].astype("category")
    county_codes = county_cat.cat.codes.to_numpy()
    counties = list(county_cat.cat.categories)

    print("tmin…")
    acc_tmin, cd_tmin = _process(SRC["tmin"], "daily_minimum_temp", lons, lats,
                                 county_codes, len(counties),
                                 {"frost_days": ("<", 0.0), "tropical_nights": (">=", 20.0)})
    print("tmax…")
    acc_tmax, cd_tmax = _process(SRC["tmax"], "daily_maximum_temp", lons, lats,
                                 county_codes, len(counties),
                                 {"summer_days": (">=", 25.0), "hot_days": (">=", 30.0)})
    print("precipitații…")
    acc_pr, cd_pr = _process(SRC["precip"], "daily_precipitation", lons, lats,
                             county_codes, len(counties),
                             {"wet_days": (">=", 1.0)})

    # coloanele NU poartă anul în nume (anul stă în etichetă/registru) — așa actualizarea
    # zilnică și trecerea în alt an nu ating schema și nu strică preseturile
    tmin_mean, tmax_mean = acc_tmin.mean(), acc_tmax.mean()
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "tmin_mean": tmin_mean,
        "tmax_mean": tmax_mean,
        "tmean": ((tmin_mean + tmax_mean) / 2).astype(np.float32),
        "frost_days": acc_tmin.thr["frost_days"][2].astype(np.int16),
        "tropical_nights": acc_tmin.thr["tropical_nights"][2].astype(np.int16),
        "summer_days": acc_tmax.thr["summer_days"][2].astype(np.int16),
        "hot_days": acc_tmax.thr["hot_days"][2].astype(np.int16),
        "precip_total": acc_pr.sum.astype(np.float32),
        "precip_max_daily": np.where(np.isfinite(acc_pr.max), acc_pr.max, np.nan).astype(np.float32),
        "wet_days": acc_pr.thr["wet_days"][2].astype(np.int16),
        "n_days_temp": acc_tmin.cnt.astype(np.int16),
        "n_days_precip": acc_pr.cnt.astype(np.int16),
    })
    # celulele fără nicio zi validă de temperatură (în afara domeniului) → NaN la contori
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "climate.parquet", index=False)

    daily = []
    for name, frame in [("tmin", cd_tmin), ("tmax", cd_tmax), ("precip", cd_pr)]:
        frame.columns = counties
        long = frame.reset_index().melt(id_vars="date", var_name="county_mn", value_name=name)
        daily.append(long.set_index(["county_mn", "date"]))
    county_daily = pd.concat(daily, axis=1).reset_index().sort_values(["county_mn", "date"])
    county_daily.to_parquet(STAGING / "county_climate_daily.parquet", index=False)
    _update_county_annual(county_daily)

    print(f"tmean [{np.nanmin(out['tmean']):.1f}, {np.nanmax(out['tmean']):.1f}] °C · "
          f"precip total [{np.nanmin(out['precip_total']):.0f}, "
          f"{np.nanmax(out['precip_total']):.0f}] mm · "
          f"zile cu date: {int(out['n_days_temp'].max())} · "
          f"serii județene: {len(county_daily)} rânduri")


def _update_county_annual(county_daily: pd.DataFrame) -> None:
    """Înlocuiește anul curent în seria multianuală după fiecare refresh zilnic."""
    current = county_daily.assign(year=county_daily["date"].dt.year).groupby(
        ["county_mn", "year"], as_index=False, observed=True
    ).agg(
        tmin=("tmin", "mean"),
        tmax=("tmax", "mean"),
        precip=("precip", "mean"),
        n_days=("date", "nunique"),
    )
    path = STAGING / "county_climate_annual.parquet"
    if path.exists():
        history = pd.read_parquet(path)
        history = history[~history["year"].isin(current["year"])]
        current = pd.concat([history, current], ignore_index=True)
    current["year"] = current["year"].astype(np.int16)
    current["n_days"] = current["n_days"].astype(np.int16)
    for col in ["tmin", "tmax", "precip"]:
        current[col] = current[col].astype(np.float32)
    current.sort_values(["county_mn", "year"]).to_parquet(path, index=False)
