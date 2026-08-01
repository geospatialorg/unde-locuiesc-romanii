"""Apartenența la intravilan (perimetrul construit al localităților), tipul localității
și accesul la rețeaua de gaze naturale.

Sursa: intravilan.gpkg (ANCPI/CNGCFT, ~13.700 localități), cu atributele TipLocalitate
și conectata_gaz (branșate sau branșabile la rețea — atribut per localitate).
Clasificare urban/rural: localitățile de tip „Sat…" → rural (sat); restul (localitate
componentă de oraș/municipiu, sector București) → urban (oraș).

Atribuire per celulă: intravilanul e rasterizat la 100 m (aliniat grilei); fiecare celulă
de 1 km primește valoarea DOMINANTĂ pe cele 10×10 subcelule (câștigă clasa cu mai mulți
pixeli acoperiți; la egalitate câștigă a doua clasă — urban / conectat la gaz). La 1 km,
centroidul ar rata multe sate (mai mici decât celula) — de aceea dominanța pe suprafață,
nu punctul central. Celulele fără acoperire (extravilan) rămân fără valoare la ambele.
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
URBAN_LABELS = np.array([None, "sat", "oraș"], dtype=object)
GAS_LABELS = np.array([None, "neconectat", "conectat"], dtype=object)


def _is_urban(tip) -> bool:
    return isinstance(tip, str) and not tip.startswith("Sat")


def _dominant_class(shapes: list, spec) -> np.ndarray:
    """Rasterizează perechi (geom, clasă 1/2) la 100 m și întoarce clasa dominantă
    per celulă de 1 km (0 = fără acoperire; la egalitate câștigă clasa 2)."""
    transform = from_origin(spec.e_min, spec.n_top, 100, 100)
    shape = (spec.nrows * F, spec.ncols * F)
    ras = features.rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8")
    blocks = ras.reshape(spec.nrows, F, spec.ncols, F)
    px2 = (blocks == 2).sum(axis=(1, 3))
    px1 = (blocks == 1).sum(axis=(1, 3))
    return np.where(px2 >= px1, np.where(px2 > 0, 2, 0), np.where(px1 > 0, 1, 0)).astype(np.uint8)


def step_intravilan() -> None:
    spec = load_spec()
    iv = pyogrio.read_dataframe(
        SRC["intravilan"], columns=["TipLocalitate", "conectata_gaz"]
    ).to_crs(GRID_CRS)

    iv["urban_cls"] = iv["TipLocalitate"].map(lambda t: 2 if _is_urban(t) else 1).astype("uint8")
    iv["gas_cls"] = iv["conectata_gaz"].map(lambda g: 2 if bool(g) else 1).astype("uint8")
    print(f"intravilan: {len(iv)} localități "
          f"(urban {int((iv['urban_cls'] == 2).sum())}, rural {int((iv['urban_cls'] == 1).sum())}) · "
          f"gaze naturale (conectate/branșabile {int((iv['gas_cls'] == 2).sum())}, "
          f"neconectate {int((iv['gas_cls'] == 1).sum())})")

    # burn clasa 1 apoi clasa 2: la suprapuneri câștigă a doua (rasterize păstrează ultima)
    urban_shapes = sorted(zip(iv.geometry, iv["urban_cls"]), key=lambda x: x[1])
    gas_shapes = sorted(zip(iv.geometry, iv["gas_cls"]), key=lambda x: x[1])
    urban_cls = _dominant_class(urban_shapes, spec)
    gas_cls = _dominant_class(gas_shapes, spec)

    cells = load_cells(["cell_id", "row", "col"])
    r = cells["row"].to_numpy().astype(np.int64)
    c = cells["col"].to_numpy().astype(np.int64)
    out = pd.DataFrame({
        "cell_id": cells["cell_id"],
        "intravilan": URBAN_LABELS[urban_cls[r, c]],
        "acces_gaz": GAS_LABELS[gas_cls[r, c]],
    })
    out = out.sort_values("cell_id", ignore_index=True)
    out.to_parquet(STAGING / "intravilan.parquet", index=False)

    print(f"oraș: {(out['intravilan'] == 'oraș').sum():,} celule · "
          f"sat: {(out['intravilan'] == 'sat').sum():,} celule · "
          f"extravilan: {out['intravilan'].isna().sum():,} celule ({out['intravilan'].isna().mean():.1%})")
    print(f"acces gaze — conectat/branșabil: {(out['acces_gaz'] == 'conectat').sum():,} celule · "
          f"neconectat: {(out['acces_gaz'] == 'neconectat').sum():,} celule")
