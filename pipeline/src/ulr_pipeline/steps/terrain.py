"""Altitudine și pantă din FABDEM.

FABDEM (~30 m, EPSG:4326) este warp-uit pe o grilă de 100 m aliniată exact grilei
de 1 km în EPSG:3035, apoi agregat 10×10 pe celulă. Panta se calculează pe DEM-ul
de 100 m (gradient Horn) — netezită față de 30 m, dar consistentă și cantitativă
(ro_slope.tif este o vizualizare Byte+Alpha, nu o sursă de date).
"""

from __future__ import annotations

import warnings

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

from ..config import GRID_CRS, SRC, STAGING
from ..grid import load_cells, load_spec

F = 10  # subcelule de 100 m pe latura unei celule de 1 km


def _block_reduce(a: np.ndarray, nrows: int, ncols: int, fn) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # felii integral NaN (mare)
        return fn(a.reshape(nrows, F, ncols, F), axis=(1, 3))


def step_terrain() -> None:
    spec = load_spec()
    w, h = spec.ncols * F, spec.nrows * F

    with rasterio.open(SRC["fabdem"]) as src:
        with WarpedVRT(
            src, crs=GRID_CRS,
            transform=from_origin(spec.e_min, spec.n_top, 100, 100),
            width=w, height=h,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata, nodata=np.nan,
        ) as vrt:
            print(f"warp FABDEM → {w}×{h} @100 m (EPSG:3035)…")
            dem = vrt.read(1, out_dtype="float32", masked=True).filled(np.nan)

    gy, gx = np.gradient(dem, 100.0)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    del gx, gy

    cells = load_cells(["cell_id", "row", "col"])
    r, c = cells["row"].to_numpy().astype(np.int64), cells["col"].to_numpy().astype(np.int64)

    stats = {
        "alt_mean": _block_reduce(dem, spec.nrows, spec.ncols, np.nanmean),
        "alt_min": _block_reduce(dem, spec.nrows, spec.ncols, np.nanmin),
        "alt_max": _block_reduce(dem, spec.nrows, spec.ncols, np.nanmax),
        "alt_std": _block_reduce(dem, spec.nrows, spec.ncols, np.nanstd),
        "slope_mean": _block_reduce(slope, spec.nrows, spec.ncols, np.nanmean),
        "slope_max": _block_reduce(slope, spec.nrows, spec.ncols, np.nanmax),
    }
    out = cells[["cell_id"]].copy()
    for k, arr in stats.items():
        out[k] = arr[r, c].astype(np.float32)

    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "terrain.parquet", index=False)
    ok = out["alt_mean"].notna()
    print(f"acoperire altitudine: {ok.mean():.2%} · "
          f"altitudine [{out['alt_mean'].min():.0f}, {out['alt_mean'].max():.0f}] m")
