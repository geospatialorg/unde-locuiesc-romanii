"""Caracterizare climatică multianuală 1961–2025, per celulă (în spiritul analizelor ANM
„caracterizare multianuală"): normale climatologice, încălzirea între normale, tendința
de temperatură, schimbarea precipitațiilor, anomalia ultimului an încheiat.

Produce și seria anuală pe județ 1961–prezent folosită de graficul din aplicație.

Sursa: cubul omogenizat data/out/climate.zarr (pasul climate_zarr).
Metodă: medii/sume anuale per pixel pe grila nativă (~1 km), apoi:
  - normala 1961–1990 și 1991–2020 (tmean, precipitații anuale)
  - încălzirea = normala 1991–2020 − normala 1961–1990
  - tendința liniară a temperaturii medii anuale 1961–2025 (°C/deceniu, OLS)
  - schimbarea precipitațiilor (%) între cele două normale
  - anomalia anului 2025 față de 1991–2020
Valorile se eșantionează la centroidele celulelor (nearest — grilele au același pas).
Anul curent (parțial) NU intră în analiza multianuală.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from ..config import DATA_OUT, STAGING
from ..grid import load_cells

ZARR = DATA_OUT / "climate.zarr"
Y0, Y1 = 1961, 2025  # perioada analizei (ani compleți)


def _nearest_idx(coord: np.ndarray, values: np.ndarray) -> np.ndarray:
    step = coord[1] - coord[0]
    idx = np.rint((values - coord[0]) / step).astype(np.int64)
    return np.clip(idx, 0, len(coord) - 1)


def step_climate_history() -> None:
    z = xr.open_zarr(ZARR)
    years_all = z["time"].dt.year.values
    years = np.arange(Y0, Y1 + 1)
    ny = len(years)
    chart_years = np.arange(Y0, int(years_all.max()) + 1)
    nlat, nlon = z.sizes["lat"], z.sizes["lon"]
    print(f"analiză {Y0}–{Y1} ({ny} ani) pe grila {nlat}×{nlon}…")

    ann_tmean = np.full((ny, nlat, nlon), np.nan, dtype=np.float32)
    ann_prec = np.full((ny, nlat, nlon), np.nan, dtype=np.float32)

    cells = load_cells(["cell_id", "lon", "lat"])
    admin = pd.read_parquet(STAGING / "admin.parquet", columns=["cell_id", "county_mn"])
    cells = cells.merge(admin, on="cell_id", how="left")
    ix = _nearest_idx(z["lon"].values, cells["lon"].to_numpy())
    iy = _nearest_idx(z["lat"].values, cells["lat"].to_numpy())
    county_cat = cells["county_mn"].astype("category")
    county_codes = county_cat.cat.codes.to_numpy()
    counties = list(county_cat.cat.categories)
    in_county = county_codes >= 0

    def county_mean(a: np.ndarray) -> np.ndarray:
        vals = a[iy, ix]
        ok = in_county & np.isfinite(vals)
        sums = np.bincount(county_codes[ok], weights=vals[ok], minlength=len(counties))
        counts = np.bincount(county_codes[ok], minlength=len(counties))
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(counts > 0, sums / counts, np.nan).astype(np.float32)

    county_annual = []
    for chart_i, y in enumerate(chart_years):
        sel = np.nonzero(years_all == y)[0]
        sl = slice(int(sel[0]), int(sel[-1]) + 1)
        tmin = z["tmin"].isel(time=sl).values
        tmax = z["tmax"].isel(time=sl).values
        with np.errstate(invalid="ignore"):
            year_tmin = np.nanmean(tmin, axis=0)
            year_tmax = np.nanmean(tmax, axis=0)
            year_tmean = (year_tmin + year_tmax) * 0.5
        del tmin, tmax
        pr = z["precip"].isel(time=sl).values
        valid = np.isfinite(pr).sum(axis=0)
        total = np.nansum(pr, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            year_precip_mean = np.where(valid > 0, total / valid, np.nan)

        if y <= Y1:
            i = y - Y0
            ann_tmean[i] = year_tmean
            ann_prec[i] = np.where(valid > 300, total, np.nan)  # an incomplet → NaN

        county_annual.append(pd.DataFrame({
            "county_mn": counties,
            "year": np.int16(y),
            "tmin": county_mean(year_tmin),
            "tmax": county_mean(year_tmax),
            "precip": county_mean(year_precip_mean),
            "n_days": np.int16(len(sel)),
        }))
        del year_tmin, year_tmax, year_tmean, year_precip_mean, total, valid
        del pr
        if (chart_i + 1) % 13 == 0 or chart_i == len(chart_years) - 1:
            print(f"  {y}: {chart_i + 1}/{len(chart_years)} ani agregați")

    county_annual_df = pd.concat(county_annual, ignore_index=True)
    county_annual_df.sort_values(["county_mn", "year"]).to_parquet(
        STAGING / "county_climate_annual.parquet", index=False
    )

    i6190 = (years >= 1961) & (years <= 1990)
    i9120 = (years >= 1991) & (years <= 2020)
    with np.errstate(invalid="ignore"):
        t6190 = np.nanmean(ann_tmean[i6190], axis=0)
        t9120 = np.nanmean(ann_tmean[i9120], axis=0)
        p6190 = np.nanmean(ann_prec[i6190], axis=0)
        p9120 = np.nanmean(ann_prec[i9120], axis=0)
        warming = t9120 - t6190
        prec_change = 100.0 * (p9120 - p6190) / np.where(p6190 > 0, p6190, np.nan)
        anom_2025 = ann_tmean[years == 2025][0] - t9120

        # tendința OLS per pixel, °C/deceniu; validă doar unde toți anii sunt prezenți
        t = (years - years.mean()).astype(np.float32)
        all_valid = np.isfinite(ann_tmean).all(axis=0)
        y_anom = ann_tmean - np.nanmean(ann_tmean, axis=0, keepdims=True)
        slope = np.einsum("t,tij->ij", t, np.where(np.isfinite(y_anom), y_anom, 0)) / (t * t).sum()
        trend_dec = np.where(all_valid, slope * 10.0, np.nan).astype(np.float32)

    def s(a: np.ndarray) -> np.ndarray:
        return a[iy, ix].astype(np.float32)

    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "tmean_norm_6190": s(t6190),
        "tmean_norm_9120": s(t9120),
        "warming_deg": s(warming),
        "tmean_trend_dec": s(trend_dec),
        "tmean_anom_2025": s(anom_2025),
        "prec_norm_6190": s(p6190),
        "prec_norm_9120": s(p9120),
        "prec_change_pct": s(prec_change),
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "climate_hist.parquet", index=False)
    z.close()

    q = lambda c: (np.nanmin(out[c]), np.nanmedian(out[c]), np.nanmax(out[c]))
    print(f"normala tmean 1991–2020: [{q('tmean_norm_9120')[0]:.1f}, {q('tmean_norm_9120')[2]:.1f}] °C")
    print(f"încălzire 91–20 vs 61–90: min {q('warming_deg')[0]:.2f} · median {q('warming_deg')[1]:.2f} · max {q('warming_deg')[2]:.2f} °C")
    print(f"tendință: median {q('tmean_trend_dec')[1]:.2f} °C/deceniu · anomalia 2025: median {q('tmean_anom_2025')[1]:.2f} °C")
    print(f"schimbare precipitații: median {q('prec_change_pct')[1]:.1f}%")
    print(f"serii anuale județene {chart_years[0]}–{chart_years[-1]}: {len(county_annual_df)} rânduri")
