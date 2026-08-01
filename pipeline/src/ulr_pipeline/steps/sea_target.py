"""Punctul-țintă pentru ruta „către mare": Constanța.

Nu produce o distanță per celulă (aceea rămâne `dist_coast_km` — distanța în linie
dreaptă la linia țărmului, din border.py) ci doar o destinație CONCRETĂ pentru traseul
rutier desenat pe hartă la click: „cum ajung la mare cu mașina" are sens ca rută către
un oraș real (cel mai mare port, reședința județului Constanța), nu către un punct
arbitrar de pe litoral ales doar pentru că e cel mai apropiat de rețeaua rutieră.

Sursa: ro_admin_lau_polygon.gpkg, UAT-ul „Constanța" (natCode 60419, municipiu reședință
de județ). Punctul e un „representative point" (garantat în interiorul poligonului).
"""

from __future__ import annotations

import pyogrio

from ..config import DATA_OUT, SRC

CONSTANTA_NATCODE = 60419


def step_sea_target() -> None:
    lau = pyogrio.read_dataframe(SRC["lau"])
    hit = lau[lau["natCode"] == CONSTANTA_NATCODE]
    if len(hit) != 1:
        raise ValueError(f"aștept exact un UAT cu natCode={CONSTANTA_NATCODE}, am găsit {len(hit)}")

    hit = hit.to_crs("EPSG:4326").copy()
    hit["geometry"] = hit.geometry.representative_point()
    out = hit[["name", "geometry"]]
    out.to_file(DATA_OUT / "sea_target.geojson", driver="GeoJSON")

    pt = out.geometry.iloc[0]
    name = out["name"].iloc[0]
    print(f"punct către mare: {name} ({pt.y:.4f}, {pt.x:.4f})")
