"""Distanța până la cea mai apropiată zonă cu hazard de inundații și scenariul acesteia.

Surse: hărțile de hazard la inundații, dizolvate pe scenariu de probabilitate anuală:
  - 10%  (perioadă de revenire ~10 ani)     → cel mai frecvent, cea mai mică întindere
  - 1%   (~100 ani)
  - 0,1% (~1.000 ani)                         → extrem, cea mai mare întindere
Zonele sunt (aproape) imbricate: 10% ⊂ 1% ⊂ 0,1%. „Combinat" = uniunea celor trei.

Metodă (ca la ariile protejate/apă): scenariile se rasterizează la 100 m; se ard de la cel
mai RAR (0,1%, id 3) la cel mai FRECVENT (10%, id 1), deci fiecare pixel poartă scenariul cel
mai frecvent care îl atinge. O transformată de distanță euclidiană cu indici (EDT) dă distanța
și scenariul celui mai apropiat pixel inundabil. Per celulă de 1 km:
  - distanța = MINIMUL pe bloc (0 km ⇔ celula intersectează o zonă inundabilă, nu doar centrul),
  - scenariul = cel mai frecvent scenariu prezent în bloc; dacă celula nu atinge nicio zonă,
    scenariul celui mai apropiat pixel inundabil.
Bifând un scenariu în filtre alegi banda lui; fără bifă = toate scenariile (combinat).
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

# scenarii, de la cel mai frecvent (id 1) la cel mai rar (id 3)
SCENARIOS = [
    ("flood_p10", 1, "10% (~10 ani)"),
    ("flood_p1", 2, "1% (~100 ani)"),
    ("flood_p01", 3, "0,1% (~1.000 ani)"),
]
SCEN_LABELS = np.array([None, "10% (~10 ani)", "1% (~100 ani)", "0,1% (~1.000 ani)"], dtype=object)


def step_floods() -> None:
    spec = load_spec()
    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)

    # fiecare scenariu se rasterizează separat; păstrăm per pixel scenariul CEL MAI FRECVENT
    # (id-ul cel mai mic) care îl atinge — un pixel în zona de 10% rămâne 10%, chiar dacă e și
    # în 1% / 0,1%. Astfel benzile sunt exclusive și 10% ⊂ 1% ⊂ 0,1% se respectă.
    label = np.zeros(shape, dtype="uint8")
    for src_key, scen_id, scen_label in SCENARIOS:
        gdf = pyogrio.read_dataframe(SRC[src_key], columns=[]).to_crs(GRID_CRS)
        burned = features.rasterize(
            ((geom, 1) for geom in gdf.geometry),
            out_shape=shape, transform=transform, fill=0, all_touched=True, dtype="uint8",
        )
        replace = (burned > 0) & ((label == 0) | (label > scen_id))
        label[replace] = scen_id
        print(f"  {scen_label}: {len(gdf):,} geometrii · {int((burned > 0).sum()):,} pixeli 100 m")

    dist_m, inds = distance_transform_edt(label == 0, sampling=100.0, return_indices=True)
    nearest_scen = label[inds[0], inds[1]]

    nrows, ncols = spec.nrows, spec.ncols
    db = dist_m.reshape(nrows, F, ncols, F).transpose(0, 2, 1, 3).reshape(nrows, ncols, F * F)
    lb = label.reshape(nrows, F, ncols, F).transpose(0, 2, 1, 3).reshape(nrows, ncols, F * F)
    nb = nearest_scen.reshape(nrows, F, ncols, F).transpose(0, 2, 1, 3).reshape(nrows, ncols, F * F)

    dist_km = db.min(axis=2) / 1000.0

    # scenariul celulei: cel mai frecvent prezent în bloc (min id > 0); dacă niciunul,
    # scenariul celui mai apropiat pixel inundabil (la sub-celula cu distanța minimă)
    present = np.where(lb > 0, lb, 255)
    min_present = present.min(axis=2)
    intersects = min_present != 255
    amin = db.argmin(axis=2)
    nearest_here = np.take_along_axis(nb, amin[..., None], axis=2)[..., 0]
    scen = np.where(intersects, min_present, nearest_here).astype("uint8")

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "dist_inundatii_km": np.round(dist_km[r, c], 2).astype(np.float32),
        "scenariu_inundatii": SCEN_LABELS[scen[r, c]],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "floods.parquet", index=False)

    inzone = int((out["dist_inundatii_km"] <= 0).sum())
    print(f"în zonă inundabilă (orice scenariu): {inzone:,} celule · "
          f"distanța maximă: {out['dist_inundatii_km'].max():.1f} km")
    print("scenarii (celule):", out["scenariu_inundatii"].value_counts().to_dict())
