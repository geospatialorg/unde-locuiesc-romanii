"""Distanța până la cel mai apropiat corp de apă și tipul acestuia.

Sursă: osm_hidrografie_romania.gpkg, stratul `lacuri` (OpenStreetMap, ODbL) — lacuri, lacuri
de acumulare, iazuri, bălți/brațe moarte, bazine, lagune. Câmpul `categorie_ro` dă tipul.

Metodă: corpurile de apă se rasterizează la 100 m (fiecare pixel poartă id-ul categoriei);
o transformată de distanță euclidiană (EDT) dă, pentru fiecare pixel de uscat, distanța până
la cel mai apropiat pixel de apă ȘI indicele lui (deci și categoria acelui corp de apă).
Per celulă de 1 km se ia pixelul central (≈ centroidul), consistent cu celelalte distanțe din
aplicație (mare/frontieră/spital/aeroport). 0 km ⇒ centrul celulei e pe un corp de apă.
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

# ordine stabilă a categoriilor (id = index + 1; 0 = fără apă). „Alt tip" strânge categoriile
# fără denumire clară din sursă („Nespecificat") ȘI „Braț mort" (denumire neatractivă) —
# corpurile respective tot contează ca ape la calculul distanței.
OTHER = "Alt tip"
CATS = ["Lac", "Lac de acumulare", "Iaz", "Iaz piscicol", "Bazin", "Lagună", OTHER]
CAT_ID = {c: i + 1 for i, c in enumerate(CATS)}
CAT_LABELS = np.array([None, *CATS], dtype=object)


def step_water() -> None:
    spec = load_spec()
    lakes = pyogrio.read_dataframe(
        SRC["water"], layer="lacuri", columns=["categorie_ro"]
    ).to_crs(GRID_CRS)
    # sursa folosește „Nespecificat" (și „Braț mort") — ambele cad la „Alt tip" prin fillna
    lakes["cat_id"] = (lakes["categorie_ro"].map(CAT_ID)
                       .fillna(CAT_ID[OTHER]).astype("uint8"))
    print(f"corpuri de apă: {len(lakes):,} (lacuri OSM)")

    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)
    # la suprapuneri rare între corpuri, o categorie specifică învinge „Alt tip"
    shapes = sorted(zip(lakes.geometry, lakes["cat_id"]),
                    key=lambda gv: gv[1] == CAT_ID[OTHER], reverse=True)
    label = features.rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8")

    # EDT cu indici: distanța (m) + poziția celui mai apropiat pixel de apă → categoria lui
    dist_m, inds = distance_transform_edt(label == 0, sampling=100.0, return_indices=True)
    nearest_cat = label[inds[0], inds[1]]

    dist_km = dist_m.reshape(spec.nrows, F, spec.ncols, F)[:, F // 2, :, F // 2] / 1000.0
    cat_c = nearest_cat.reshape(spec.nrows, F, spec.ncols, F)[:, F // 2, :, F // 2]

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_water_km": np.round(dist_km[r, c], 2).astype(np.float32),
        "categorie_apa": CAT_LABELS[cat_c[r, c]],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "water.parquet", index=False)

    near1 = int((out["dist_water_km"] < 1).sum())
    print(f"la < 1 km de un corp de apă: {near1:,} celule · "
          f"distanța maximă: {out['dist_water_km'].max():.0f} km")
    print("categorii (celule):",
          out["categorie_apa"].value_counts().to_dict())
