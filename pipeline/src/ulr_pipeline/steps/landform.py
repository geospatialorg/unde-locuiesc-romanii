"""Apartenența la formele de relief (ierarhia formală, stratul v11).

lvl0 = marile unități (Carpații Orientali, Câmpia Română…), lvl1 = subdiviziuni,
type = tipul formei (munte/deal/podiș/câmpie/depresiune/vale/grind/baltă).
Golurile din lvl0 (ex. Delta) se completează în cascadă din lvl1 / nume.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pyogrio

from ..config import GRID_CRS, SRC, STAGING
from ..grid import cell_centroids_3035, load_cells

LAYER = "ro_geomorphometry_landforms_v11"
COLS = {
    "r_1name": "landform_name",
    "r_1type": "landform_type",
    "r_1j_lvl0_name": "landform_lvl0",
    "r_1j_lvl1_name": "landform_lvl1",
}


def step_landform() -> None:
    cells = load_cells(["cell_id", "e", "n"])
    xc, yc = cell_centroids_3035(cells)
    pts = gpd.GeoDataFrame(
        {"cell_id": cells["cell_id"]},
        geometry=gpd.points_from_xy(xc, yc), crs=GRID_CRS,
    )

    lf = pyogrio.read_dataframe(SRC["landforms"], layer=LAYER).to_crs(GRID_CRS)
    lf = lf[list(COLS) + ["geometry"]].rename(columns=COLS)

    joined = gpd.sjoin(pts, lf, predicate="within", how="left")
    joined = joined.drop_duplicates("cell_id", keep="first")

    missing = joined["landform_name"].isna()
    if missing.any():
        near = gpd.sjoin_nearest(
            pts[pts["cell_id"].isin(joined.loc[missing, "cell_id"])],
            lf, how="left", max_distance=5000,
        ).drop_duplicates("cell_id", keep="first")
        joined = pd.concat([joined[~missing], near], ignore_index=True)
        print(f"celule fără formă de relief la 'within': {int(missing.sum())} "
              f"(rezolvate prin cea mai apropiată: {int(near['landform_name'].notna().sum())})")

    out = joined[["cell_id", "landform_name", "landform_type", "landform_lvl0", "landform_lvl1"]].copy()
    out["landform_lvl0"] = out["landform_lvl0"].fillna(out["landform_lvl1"]).fillna(out["landform_name"])
    out["landform_lvl1"] = out["landform_lvl1"].fillna(out["landform_name"])
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "landform.parquet", index=False)
    print(f"acoperire relief: {out['landform_name'].notna().mean():.2%}")
