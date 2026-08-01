"""Apartenența administrativă a celulelor: UAT (SIRUTA), județ, regiune, statut.

Join spațial pe centroidele celulelor (EPSG:3035). Celulele al căror centroid cade
în afara poligoanelor UAT (litoral, lacuri de frontieră) primesc UAT-ul cel mai
apropiat, în limita a 5 km.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pyogrio

from ..config import GRID_CRS, SRC, STAGING
from ..grid import cell_centroids_3035, load_cells

STATUS_MAP = {
    "Comuna": "comună",
    "Oras": "oraș",
    "Municipiu resedinta de judet": "municipiu",
    "Municipiu, altul decat resedinta de judet": "municipiu",
    "Sectoarele municipiului Bucuresti": "sector București",
}


def step_admin() -> None:
    cells = load_cells(["cell_id", "e", "n"])
    xc, yc = cell_centroids_3035(cells)
    pts = gpd.GeoDataFrame(
        {"cell_id": cells["cell_id"]},
        geometry=gpd.points_from_xy(xc, yc), crs=GRID_CRS,
    )

    lau = pyogrio.read_dataframe(SRC["lau"]).to_crs(GRID_CRS)
    lau = lau[["natCode", "name", "natLevName", "countyMn", "county", "region", "geometry"]]

    joined = gpd.sjoin(pts, lau, predicate="within", how="left")
    joined = joined.drop_duplicates("cell_id", keep="first")

    missing = joined["natCode"].isna()
    if missing.any():
        near = gpd.sjoin_nearest(
            pts[pts["cell_id"].isin(joined.loc[missing, "cell_id"])],
            lau, how="left", max_distance=5000,
        ).drop_duplicates("cell_id", keep="first")
        joined = pd.concat([joined[~missing], near], ignore_index=True)
        print(f"celule fără UAT la 'within': {int(missing.sum())} "
              f"(rezolvate prin cel mai apropiat: {int(near['natCode'].notna().sum())})")

    out = pd.DataFrame({
        "cell_id": joined["cell_id"],
        "siruta": joined["natCode"].astype("Int32"),
        "uat_name": joined["name"],
        "uat_status": joined["natLevName"].map(STATUS_MAP),
        "county_mn": joined["countyMn"],
        "county_name": joined["county"],
        "region_name": joined["region"],
    })
    out["mediu"] = out["uat_status"].map(
        lambda s: "rural" if s == "comună" else ("urban" if pd.notna(s) else None)
    )
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "admin.parquet", index=False)
    print(f"acoperire UAT: {out['siruta'].notna().mean():.2%}")
