import os
from datetime import datetime
from pathlib import Path

DATA_IN = Path(os.environ.get("ULR_DATA_IN", "data"))
DATA_OUT = Path(os.environ.get("ULR_DATA_OUT", "data/out"))
STAGING = Path(os.environ.get("ULR_STAGING", "data/staging"))

# anul datelor climatice zilnice — implicit anul curent, deci URL-ul și fișierele se
# adaptează singure la trecerea în alt an (se schimbă doar cifra anului în nume)
CLIMATE_YEAR = int(os.environ.get("ULR_CLIMATE_YEAR", datetime.now().year))

# grilele zilnice actualizate zilnic de MeteoRomania (opendata)
METEO_BASE = "https://opendata.meteoromania.ro/data/daily"
CLIMATE_URLS = {
    "precip": f"{METEO_BASE}/precip/daily_precip_{CLIMATE_YEAR}.nc",
    "tmin": f"{METEO_BASE}/tmin/daily_tmin_synop_{CLIMATE_YEAR}.nc",
    "tmax": f"{METEO_BASE}/tmax/daily_tmax_synop_{CLIMATE_YEAR}.nc",
}

SRC = {
    "census": DATA_IN / "Recensamant2021_GridData.gpkg",
    "lau": DATA_IN / "ro_admin_lau_polygon.gpkg",
    "county": DATA_IN / "ro_admin_county_polygon.gpkg",
    "country_line": DATA_IN / "ro_admin_country_line.gpkg",
    "landforms": DATA_IN / "ro_geomorphometry_landforms_v11.gpkg",
    "intravilan": DATA_IN / "intravilan.gpkg",
    "protected_areas": DATA_IN / "arii-protejate.gpkg",
    "water": DATA_IN / "osm_hidrografie_romania.gpkg",
    "watercourses": DATA_IN / "cursuri_apa.gpkg",
    "flood_p10": DATA_IN / "hazard_inundatii_p10_dizolvat.gpkg",       # 10% anual (~10 ani)
    "flood_p1": DATA_IN / "hazard_inundatii_p1_dizolvat.gpkg",         # 1% anual (~100 ani)
    "flood_p01": DATA_IN / "hazard_inundatii_p0_1_dizolvat.gpkg",      # 0,1% anual (~1.000 ani)
    "bear": DATA_IN / "zonarea_managementului_populatiei_de_urs_brun.gpkg",  # zone conflict urs brun
    "hospitals": DATA_IN / "spitale_anmcs.gpkg",
    "crossings": DATA_IN / "puncte_trecere_frontiera.geojson",
    "airports": DATA_IN / "aeroporturi_romania.geojson",
    "fabdem": DATA_IN / "fabdem_ro.tif",
    "precip": DATA_IN / f"daily_precip_{CLIMATE_YEAR}.nc",
    "tmin": DATA_IN / f"daily_tmin_synop_{CLIMATE_YEAR}.nc",
    "tmax": DATA_IN / f"daily_tmax_synop_{CLIMATE_YEAR}.nc",
}

GRID_CRS = "EPSG:3035"   # grila GEOSTAT — spațiul canonic (după GRD_ID)
DATA_CRS = "EPSG:3844"   # Stereo70 — CRS-ul geometriilor din GPKG-uri
RES = 1000               # m

def ensure_dirs() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
