"""Distanța până la cel mai apropiat curs de apă și tipul acestuia (râu / pârâu).

Sursă: cursuri_apa.gpkg, stratul `cursuri_apa` (OpenStreetMap, ODbL) — ~42.000 linii de
curs de apă. Câmpul `categorie_ro` dă tipul: „Râu" (waterway=river) sau „Pârâu" (stream).

Metodă identică cu apele stătătoare (steps/water.py), dar sursa e liniară: liniile se
rasterizează la 100 m (all_touched, ca să nu rămână goluri pe diagonale), fiecare pixel
poartă id-ul categoriei; o transformată de distanță euclidiană cu indici (EDT) dă distanța
până la cel mai apropiat pixel de curs de apă ȘI categoria acestuia. Per celulă de 1 km se ia
pixelul central (≈ centroidul), consistent cu celelalte distanțe. 0 km = pe curs de apă.
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

# id = index + 1 (0 = fără curs de apă)
CATS = ["Râu", "Pârâu"]
CAT_ID = {c: i + 1 for i, c in enumerate(CATS)}
CAT_LABELS = np.array([None, *CATS], dtype=object)


def step_watercourses() -> None:
    spec = load_spec()
    cw = pyogrio.read_dataframe(
        SRC["watercourses"], layer="cursuri_apa", columns=["categorie_ro"]
    ).to_crs(GRID_CRS)
    cw["cat_id"] = cw["categorie_ro"].map(CAT_ID).fillna(CAT_ID["Pârâu"]).astype("uint8")
    print(f"cursuri de apă: {len(cw):,} linii (OSM)")

    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)
    # burn Pârâu apoi Râu → la intersecții rare câștigă Râul (tipul mai important)
    shapes = sorted(zip(cw.geometry, cw["cat_id"]), key=lambda gv: gv[1])
    label = features.rasterize(shapes, out_shape=shape, transform=transform, fill=0,
                               all_touched=True, dtype="uint8")

    dist_m, inds = distance_transform_edt(label == 0, sampling=100.0, return_indices=True)
    nearest_cat = label[inds[0], inds[1]]

    dist_km = dist_m.reshape(spec.nrows, F, spec.ncols, F)[:, F // 2, :, F // 2] / 1000.0
    cat_c = nearest_cat.reshape(spec.nrows, F, spec.ncols, F)[:, F // 2, :, F // 2]

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_curs_km": np.round(dist_km[r, c], 2).astype(np.float32),
        "categorie_curs": CAT_LABELS[cat_c[r, c]],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "watercourses.parquet", index=False)

    near = int((out["dist_curs_km"] < 0.5).sum())
    print(f"la < 500 m de un curs de apă: {near:,} celule · "
          f"distanța maximă: {out['dist_curs_km'].max():.1f} km")
    print("categorii (celule):", out["categorie_curs"].value_counts().to_dict())
