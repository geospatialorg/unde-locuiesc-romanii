"""Zona de management al conflictului cu ursul brun, per celulă.

Sursa: zonarea_managementului_populatiei_de_urs_brun.gpkg (3 poligoane dizolvate pe tip,
atributul `symbol` 0/1/2 = severitate crescătoare). Nivele de risc de conflict:
  symbol 0 → „Risc potențial"  (Zone potențiale de conflict)
  symbol 1 → „Risc mediu"       (Zone cu risc mediu de conflict)
  symbol 2 → „Risc ridicat"     (Zone cu risc ridicat de conflict)

Per celulă de 1 km: clasa DOMINANTĂ pe blocul 10×10 (ca la intravilan) — câștigă nivelul
cu cei mai mulți pixeli; la egalitate câștigă riscul mai mare. Celulele majoritar în afara
oricărei zone rămân fără valoare. Categoriile se exclud (o celulă = un nivel de risc), deci
în aplicație apar ca chips.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyogrio
from rasterio import features
from rasterio.transform import from_origin

from ..config import GRID_CRS, SRC, STAGING
from ..grid import load_cells, load_spec

F = 10  # subcelule de 100 m pe latura unei celule de 1 km
# index = clasă (0 = fără zonă, 1/2/3 = potențial/mediu/ridicat)
LABELS = np.array([None, "Risc potențial", "Risc mediu", "Risc ridicat"], dtype=object)


def step_bear() -> None:
    spec = load_spec()
    gdf = pyogrio.read_dataframe(SRC["bear"], columns=["symbol"]).to_crs(GRID_CRS)
    gdf["zid"] = (gdf["symbol"].astype(int) + 1).astype("uint8")  # 1/2/3
    print(f"zone urs brun: {len(gdf)} poligoane (potențial/mediu/ridicat)")

    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)
    # burn crescător după zid → la eventuale suprapuneri câștigă riscul mai mare (ultimul ars)
    shapes = sorted(zip(gdf.geometry, gdf["zid"]), key=lambda gv: gv[1])
    ras = features.rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8")

    b = ras.reshape(spec.nrows, F, spec.ncols, F)
    px1 = (b == 1).sum(axis=(1, 3))
    px2 = (b == 2).sum(axis=(1, 3))
    px3 = (b == 3).sum(axis=(1, 3))
    px0 = F * F - px1 - px2 - px3
    # clasa dominantă; ordinea (3,2,1,0) face ca argmax (primul maxim) să favorizeze riscul mai mare
    idx = np.stack([px3, px2, px1, px0], axis=-1).argmax(axis=-1)
    cls = np.array([3, 2, 1, 0], dtype=np.uint8)[idx]

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "risc_urs": LABELS[cls[r, c]],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "bear.parquet", index=False)

    inzone = int(out["risc_urs"].notna().sum())
    print(f"în zonă de management urs (orice nivel): {inzone:,} celule")
    print("nivele (celule):", out["risc_urs"].value_counts(dropna=False).to_dict())
