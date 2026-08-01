"""Distanța până la cel mai apropiat aeroport.

Sursa: aeroporturi_romania.geojson (18 aeroporturi, OurAirports; nume, municipiu, IATA, tip).
Distanța în linie dreaptă per celulă (cKDTree în 3035) + numele scurt al aeroportului.
Distanța și timpul PE ȘOSEA se obțin la cerere, din serviciul de rutare (target „airport").
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree

from ..config import DATA_OUT, GRID_CRS, SRC, STAGING
from ..grid import cell_centroids_3035, load_cells


def _label(row) -> str:
    muni = row.get("municipality") or row.get("name") or "aeroport"
    iata = row.get("iata")
    return f"{muni} ({iata})" if iata else str(muni)


def step_airports() -> None:
    ap = pyogrio.read_dataframe(SRC["airports"])
    print(f"aeroporturi: {len(ap)}")
    ap = ap.reset_index(drop=True)
    labels = ap.apply(_label, axis=1).to_numpy()

    ap3035 = ap.to_crs(GRID_CRS)
    xy = np.column_stack([ap3035.geometry.x, ap3035.geometry.y])
    tree = cKDTree(xy)

    cells = load_cells(["cell_id", "e", "n"])
    xc, yc = cell_centroids_3035(cells)
    dist_m, idx = tree.query(np.column_stack([xc, yc]), k=1)

    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_airport_km": (dist_m / 1000.0).astype(np.float32),
        "nearest_airport": labels[idx],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "airports.parquet", index=False)

    # puncte pentru hartă + pentru importul în baza de rutare (WGS84)
    ap = ap.copy()
    ap["label"] = labels
    keep = [c for c in ["name", "label", "municipality", "iata", "airport_type_ro"] if c in ap.columns]
    ap[keep + ["geometry"]].to_crs("EPSG:4326").to_file(DATA_OUT / "airports.geojson", driver="GeoJSON")

    print(f"dist. aeroport [{out['dist_airport_km'].min():.1f}, {out['dist_airport_km'].max():.1f}] km · "
          f"airports.geojson: {len(ap)} puncte")
