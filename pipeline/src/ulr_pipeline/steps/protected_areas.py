"""Distanța până la cea mai apropiată arie protejată (0 km în interior) — toate categoriile:
parcuri naționale, parcuri naturale, rezervații naturale, monumente ale naturii, rezervații
științifice și situri Natura 2000.

Sursă: arii-protejate.gpkg (ANANP). Geometria e deja unificată într-un singur multipoligon
pe toate categoriile — atributele per-tip nu s-au păstrat la unificare, de aceea nu distingem
tipul ariei, doar apartenența/proximitatea față de ansamblul lor.

Metodă: ariile se rasterizează la 100 m; o transformată de distanță euclidiană (EDT) dă, pentru
fiecare pixel din afara ariilor, distanța până la cel mai apropiat pixel-arie (pixelii din
interior primesc 0). Distanța per celulă de 1 km e MINIMUL pe cele 10×10 subcelule — adică
distanța de la cel mai apropiat punct al celulei la cea mai apropiată arie. Astfel 0 km ⇒
celula se INTERSECTEAZĂ cu o arie protejată (fără buffer), iar celulele care nu o ating au
distanță ≥ 0,1 km (rezoluția rasterului). Așa, un prag de 0 km selectează exact celulele care
ating aria, iar praguri > 0 adaugă o zonă de proximitate.
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

F = 10  # subcelule de 100 m pe latura unei celule de 1 km


def step_protected_areas() -> None:
    spec = load_spec()
    pa = pyogrio.read_dataframe(SRC["protected_areas"]).to_crs(GRID_CRS)
    print(f"arii protejate: {len(pa)} geometrii sursă (parcuri naționale/naturale, rezervații "
          f"naturale/științifice, monumente ale naturii, situri Natura 2000 — ANANP)")

    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)
    ras = features.rasterize(
        pa.geometry, out_shape=shape, transform=transform, fill=0, default_value=1, dtype="uint8"
    )

    # EDT: distanța (în metri, sampling=100 m) de la fiecare pixel din afara ariilor la cel mai
    # apropiat pixel-arie; pixelii din interior primesc 0.
    dist_m = distance_transform_edt(ras == 0, sampling=100.0)
    # per celulă de 1 km: minimul pe subcelule → 0 dacă celula atinge o arie (fără buffer)
    dist_km = dist_m.reshape(spec.nrows, F, spec.ncols, F).min(axis=(1, 3)) / 1000.0

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_protected_km": np.round(dist_km[r, c], 2).astype(np.float32),
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "protected_areas.parquet", index=False)

    inside = int((out["dist_protected_km"] == 0).sum())
    near1 = int((out["dist_protected_km"] <= 1).sum())
    print(f"arie protejată — în interior: {inside:,} celule · la ≤ 1 km: {near1:,} celule "
          f"· distanța maximă: {out['dist_protected_km'].max():.0f} km")
