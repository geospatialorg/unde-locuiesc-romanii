"""Distanțe la frontiera de stat și la litoral.

Metodă: segmentele de frontieră (dizolvate pe vecin) sunt rasterizate pe grila de
1 km, apoi transformata euclidiană de distanță (EDT) dă distanța fiecărei celule.
Precizie: ±~0,7 km — suficientă pentru „zona de frontieră” (prag implicit 30 km);
documentat în registru. Segmentul RO.RO este litoralul Mării Negre (verificat
prin poziție), folosit pentru „la mare”.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyogrio
from rasterio import features
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt

from ..config import GRID_CRS, SRC, STAGING
from ..grid import load_cells, load_spec


def step_border() -> None:
    spec = load_spec()
    lines = pyogrio.read_dataframe(SRC["country_line"]).to_crs(GRID_CRS)
    groups = lines.dissolve(by="border").reset_index()

    transform = from_origin(spec.e_min, spec.n_top, spec.res, spec.res)
    shape = (spec.nrows, spec.ncols)

    def dist_km(geom) -> np.ndarray:
        mask = features.rasterize([(geom, 1)], out_shape=shape, transform=transform,
                                  all_touched=True, dtype="uint8")
        return (distance_transform_edt(mask == 0, sampling=spec.res) / 1000.0).astype(np.float32)

    coast_row = groups[groups["border"] == "RO.RO"]
    assert len(coast_row) == 1, "aștept un singur segment RO.RO (litoralul)"
    coast_c = coast_row.geometry.iloc[0].centroid
    coast_ll = pyogrio.read_dataframe(SRC["country_line"]).to_crs("EPSG:4326")
    coast_lon = coast_ll[coast_ll["border"] == "RO.RO"].geometry.union_all().centroid.x
    assert coast_lon > 28.0, f"RO.RO nu pare a fi litoralul (lon centroid={coast_lon:.2f})"
    dist_coast = dist_km(coast_row.geometry.iloc[0])

    neighbors = groups[groups["border"] != "RO.RO"]
    codes = [b.split(".")[1] for b in neighbors["border"]]
    dists = np.stack([dist_km(g) for g in neighbors.geometry])  # (n_vecini, nrows, ncols)
    nearest = dists.argmin(axis=0)
    dist_border = dists.min(axis=0)

    cells = load_cells(["cell_id", "row", "col"])
    r, c = cells["row"].to_numpy().astype(np.int64), cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_border_km": dist_border[r, c],
        "border_neighbor": pd.Categorical.from_codes(nearest[r, c], categories=codes),
        "dist_coast_km": dist_coast[r, c],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "border.parquet", index=False)
    print(f"dist. frontieră [{out['dist_border_km'].min():.0f}, {out['dist_border_km'].max():.0f}] km · "
          f"dist. litoral [{out['dist_coast_km'].min():.0f}, {out['dist_coast_km'].max():.0f}] km")
