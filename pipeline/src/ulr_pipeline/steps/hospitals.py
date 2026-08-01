"""Distanța până la cel mai apropiat spital (registrul ANMCS).

Sursa: spitale_anmcs.gpkg (puncte WGS84, ~731 unități; păstrăm doar active=1).
Metodă: cKDTree peste punctele proiectate în EPSG:3035 → distanța euclidiană de la
centroidul fiecărei celule + numele spitalului cel mai apropiat (pentru fișă).
Distanța rutieră reală se calculează separat, la cerere, de serviciul de rutare
(pgRouting) — aici e doar „în linie dreaptă", potrivită pentru filtrare la scara 1 km.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree

from ..config import DATA_OUT, GRID_CRS, SRC, STAGING
from ..grid import cell_centroids_3035, load_cells


def step_hospitals() -> None:
    hosp = pyogrio.read_dataframe(SRC["hospitals"])
    hosp = hosp[hosp["active"] == 1].copy()
    print(f"spitale ANMCS active: {len(hosp)}")

    hosp3035 = hosp.to_crs(GRID_CRS)
    pts = np.column_stack([hosp3035.geometry.x, hosp3035.geometry.y])
    tree = cKDTree(pts)

    cells = load_cells(["cell_id", "e", "n"])
    xc, yc = cell_centroids_3035(cells)
    dist_m, idx = tree.query(np.column_stack([xc, yc]), k=1)

    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_hospital_km": (dist_m / 1000.0).astype(np.float32),
        "nearest_hospital": hosp["nume"].to_numpy()[idx],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "hospitals.parquet", index=False)

    # punctele pentru hartă + pentru importul în baza de rutare (WGS84)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    export = hosp[["nume", "judet", "city", "geometry"]].to_crs("EPSG:4326")
    export.to_file(DATA_OUT / "hospitals.geojson", driver="GeoJSON")

    print(f"dist. spital [{out['dist_hospital_km'].min():.1f}, {out['dist_hospital_km'].max():.1f}] km · "
          f"hospitals.geojson: {len(export)} puncte")
