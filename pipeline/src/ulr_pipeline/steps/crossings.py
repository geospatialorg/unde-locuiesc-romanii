"""Distanța până la cel mai apropiat punct de trecere a frontierei (unde se poate ieși din țară).

Sursa: puncte_trecere_frontiera.geojson (puncte auto, Poliția de Frontieră). Spre deosebire de
`dist_border_km` (distanța până la LINIA de frontieră — util pentru „zona de frontieră"), aici
ținta e un punct real de trecere. Distanța în linie dreaptă se calculează per celulă (cKDTree);
distanța și timpul PE ȘOSEA se obțin la cerere, din serviciul de rutare (target „crossing").
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree

from ..config import DATA_OUT, GRID_CRS, SRC, STAGING
from ..grid import cell_centroids_3035, load_cells


def step_crossings() -> None:
    pts = pyogrio.read_dataframe(SRC["crossings"])
    print(f"puncte de trecere a frontierei: {len(pts)}")

    pts3035 = pts.to_crs(GRID_CRS)
    xy = np.column_stack([pts3035.geometry.x, pts3035.geometry.y])
    tree = cKDTree(xy)

    cells = load_cells(["cell_id", "e", "n"])
    xc, yc = cell_centroids_3035(cells)
    dist_m, idx = tree.query(np.column_stack([xc, yc]), k=1)

    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_crossing_km": (dist_m / 1000.0).astype(np.float32),
        "nearest_crossing": pts["name"].to_numpy()[idx],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "crossings.parquet", index=False)

    # puncte pentru hartă + pentru importul în baza de rutare (WGS84)
    keep = [c for c in ["name", "waiting_time_min", "direction"] if c in pts.columns]
    export = pts[keep + ["geometry"]].to_crs("EPSG:4326")
    export.to_file(DATA_OUT / "crossings.geojson", driver="GeoJSON")

    print(f"dist. punct de trecere [{out['dist_crossing_km'].min():.1f}, "
          f"{out['dist_crossing_km'].max():.1f}] km · crossings.geojson: {len(export)} puncte")
