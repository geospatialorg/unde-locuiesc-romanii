"""Definiția grilei de 1 km și extragerea atributelor de recensământ.

Grila este grila statistică europeană (GEOSTAT, EPSG:3035) — GRD_ID de forma
CRS3035RES1000mN<northing>E<easting>, cu N/E = colțul de sud-vest al celulei, în metri.
Geometriile din GPKG sunt stocate în Stereo70, dar nu le folosim: totul se derivă
din GRD_ID, iar spațiul canonic al aplicației este EPSG:3035.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
import pyogrio
from pyproj import Transformer

from .config import GRID_CRS, RES, SRC, STAGING

CENSUS_LAYER = "recensamant2021_griddata"

RENAME = {
    "Populatia_totala_T": "pop_total",
    "Populatia_sex_feminin_F": "pop_f",
    "Populatia_sex_masculin_M": "pop_m",
    "Persoane_cu_varsta_mai_mica_de_15_ani_Y_LT15": "pop_0_14",
    "Persoane_cu_varsta_cuprinsa_intre_15_si_65_de_ani_Y15_64": "pop_15_64",
    "Persoane_cu_varsta_de_65_ani_si_peste_Y_GE65": "pop_65p",
    "Populatia_ocupata_EMP": "pop_ocupata",
    "Persoane_de_cetatenie_romana_NAT": "pop_cet_ro",
    "Persoane_de_alta_cetatenie_dar_al_unui_stat_membru_UE_EU_OTH": "pop_cet_ue",
    "Persoane_de_alta_cetatenie_dar_dintr_un_stat_non_UE_OTH": "pop_cet_non_ue",
    "Persoane_care_si_au_schimbat_resedinta_in_tara_CHG_IN": "pop_mutati_in_tara",
    "Persoane_care_si_au_schimbat_resedinta_in_afara_tarii_CHG_OU": "pop_mutati_strainatate",
    "Persoane_cu_resedinta_obisnuita_neschimbata_SAME": "pop_res_neschimbata",
    "TOT_P_2021": "pop_2021_eurostat",
    "TOT_P_2018": "pop_2018",
    "TOT_P_2011": "pop_2011",
    "TOT_P_2006": "pop_2006",
}


@dataclass
class GridSpec:
    e_min: int
    n_min: int
    ncols: int
    nrows: int
    res: int = RES
    crs: str = GRID_CRS

    @property
    def n_top(self) -> int:
        return self.n_min + self.nrows * self.res

    @property
    def e_max(self) -> int:
        return self.e_min + self.ncols * self.res

    def save(self, path) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self) | {"n_top": self.n_top, "e_max": self.e_max}, f, indent=2)

    @classmethod
    def load(cls, path) -> "GridSpec":
        with open(path) as f:
            d = json.load(f)
        return cls(e_min=d["e_min"], n_min=d["n_min"], ncols=d["ncols"], nrows=d["nrows"],
                   res=d["res"], crs=d["crs"])


def load_spec() -> GridSpec:
    return GridSpec.load(STAGING / "gridspec.json")


def load_cells(columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(STAGING / "cells.parquet", columns=columns)


def cell_centroids_3035(cells: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Centroidele celulelor în EPSG:3035."""
    return cells["e"].to_numpy() + RES / 2, cells["n"].to_numpy() + RES / 2


def step_grid() -> None:
    df = pyogrio.read_dataframe(SRC["census"], layer=CENSUS_LAYER, read_geometry=False)
    print(f"celule recensământ: {len(df)}")

    en = df["GRD_ID"].str.extract(r"N(\d+)E(\d+)").astype(np.int64)
    n, e = en[0].to_numpy(), en[1].to_numpy()

    spec = GridSpec(
        e_min=int(e.min()), n_min=int(n.min()),
        ncols=int((e.max() - e.min()) // RES) + 1,
        nrows=int((n.max() - n.min()) // RES) + 1,
    )
    print(f"grilă: {spec.ncols} × {spec.nrows} celule, "
          f"E [{spec.e_min}, {spec.e_max}], N [{spec.n_min}, {spec.n_top}]")

    col = ((e - spec.e_min) // RES).astype(np.int32)
    row = ((spec.n_top - RES - n) // RES).astype(np.int32)  # rândul 0 = nord
    cell_id = (row.astype(np.int64) * spec.ncols + col).astype(np.uint32)
    assert len(np.unique(cell_id)) == len(cell_id), "cell_id trebuie să fie unic"

    tr = Transformer.from_crs(GRID_CRS, "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(e + RES / 2, n + RES / 2)

    out = pd.DataFrame({
        "cell_id": cell_id,
        "grid_id": df["GRD_ID"],
        "col": col.astype(np.uint16),
        "row": row.astype(np.uint16),
        "e": e.astype(np.int32),
        "n": n.astype(np.int32),
        "lon": np.asarray(lon, dtype=np.float64),
        "lat": np.asarray(lat, dtype=np.float64),
    })
    for src_col, dst in RENAME.items():
        s = df[src_col]
        if s.dtype.kind == "f":  # seriile Eurostat 2006/2011/2018 sunt Real, cu goluri
            out[dst] = s.astype(np.float32)
        else:
            out[dst] = s.astype(np.int32)

    out = out.sort_values("cell_id", ignore_index=True)
    spec.save(STAGING / "gridspec.json")
    out.to_parquet(STAGING / "cells.parquet", index=False)
    print(f"populație totală 2021 (INS): {out['pop_total'].sum():,}")
