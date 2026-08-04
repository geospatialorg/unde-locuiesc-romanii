"""Orchestratorul pipeline-ului: python -m ulr_pipeline.run [pas ...|all]"""

from __future__ import annotations

import sys
import time

from .config import ensure_dirs


def main() -> None:
    from .grid import step_grid
    from .steps.admin import step_admin
    from .steps.landform import step_landform
    from .steps.intravilan import step_intravilan
    from .steps.protected_areas import step_protected_areas
    from .steps.water import step_water
    from .steps.watercourses import step_watercourses
    from .steps.floods import step_floods
    from .steps.bear import step_bear
    from .steps.hospitals import step_hospitals
    from .steps.crossings import step_crossings
    from .steps.airports import step_airports
    from .steps.sea_target import step_sea_target
    from .steps.terrain import step_terrain
    from .steps.border import step_border
    from .steps.climate import step_climate
    from .steps.climate_zarr import step_climate_zarr
    from .steps.climate_history import step_climate_history
    from .export import step_export
    from .validate import step_validate

    steps = {
        "grid": step_grid,
        "admin": step_admin,
        "landform": step_landform,
        "intravilan": step_intravilan,  # intravilan ANCPI → oraș/sat per celulă
        "protected_areas": step_protected_areas,  # apartenența la o arie protejată (ANANP)
        "water": step_water,            # distanța la cel mai apropiat corp de apă + tipul (OSM)
        "watercourses": step_watercourses,  # distanța la cel mai apropiat curs de apă + tipul (OSM)
        "floods": step_floods,          # distanța la zona cu hazard de inundații + scenariul
        "bear": step_bear,              # zona de management al conflictului cu ursul brun
        "hospitals": step_hospitals,    # distanța la cel mai apropiat spital (ANMCS)
        "crossings": step_crossings,    # distanța la cel mai apropiat punct de trecere a frontierei
        "airports": step_airports,      # distanța la cel mai apropiat aeroport
        "sea_target": step_sea_target,  # destinația rutei „către mare" (Constanța)
        "terrain": step_terrain,
        "border": step_border,
        "climate": step_climate,
        "climate_zarr": step_climate_zarr,        # NC 1961–prezent → cub Zarr omogenizat
        "climate_history": step_climate_history,  # analiză multianuală 1961–2025 per celulă
        "export": step_export,
        "validate": step_validate,
    }

    args = sys.argv[1:] or ["all"]
    names = list(steps) if args == ["all"] else args
    unknown = [n for n in names if n not in steps]
    if unknown:
        sys.exit(f"pași necunoscuți: {unknown}; disponibili: {list(steps)} sau 'all'")

    ensure_dirs()
    for name in names:
        t0 = time.time()
        print(f"\n=== {name} ===")
        steps[name]()
        print(f"=== {name} gata în {time.time() - t0:.1f}s ===")


if __name__ == "__main__":
    main()
