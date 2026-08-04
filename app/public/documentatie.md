# Unde locuiesc românii? — documentație

Aplicație interactivă care răspunde la întrebări despre **câți români locuiesc într-un loc și cum arată viața acolo**, pe o grilă statistică de 1×1 km. Totul rulează în browser, fără backend, interogând direct fișiere cloud-native (GeoParquet cu DuckDB-WASM).

Cod sursă: **[github.com/geospatialorg/unde-locuiesc-romanii](https://github.com/geospatialorg/unde-locuiesc-romanii)**

---

## ⚠️ Limitări importante (a se citi înainte de a cita cifrele)

### 1. Cifrele de populație pot fi SUPRAESTIMATE

Populația provine din **grila de populație de 1×1 km a INS / EUROSTAT** (recensământul 2021, format GEOSTAT). Fiecare celulă are un număr total de locuitori, **fără a ști cum sunt distribuiți în interiorul ei**.

Selecțiile din aplicație funcționează pe bază de **intersecție**: o celulă de 1 km² este numărată dacă *se intersectează* cu zona întrebării (râu, zonă inundabilă, arie protejată, zonă de risc etc.). Ca urmare:

- dacă doar o parte a celulei atinge zona, dar **toată** populația celulei este numărată, rezultatul **supraestimează** numărul real de locuitori afectați;
- nu putem anticipa dacă oamenii dintr-o celulă locuiesc chiar în porțiunea intersectată sau în cealaltă.

Tratați cifrele ca **ordine de mărime și comparații**, nu ca numărători exacte. Avem în plan metode de dezagregare sub-celulară (ponderare pe zone construite / clădiri), dar **momentan** aplicația lucrează la rezoluția de 1 km.

### 2. Rutarea este orientativă

Rutele pe șosea (până la mare, frontieră, spital, aeroport) se calculează pe un **extras OpenStreetMap**, cu [pgRouting](https://pgrouting.org):

- **nu sunt date live** — fără trafic, fără restricții în timp real, fără închideri de drum;
- **fără reguli sofisticate** de rutare (sensuri, categorii fine de viteză, taxe);
- e o estimare **orientativă** a distanței și timpului, nu o navigație.

În plus, **multe distanțe sunt calculate în linie dreaptă**, nu pe traseu rutier (de ex. distanța până la un corp de apă, un curs de apă, o arie protejată, linia de frontieră). Doar câteva ținte au rută reală pe șosea (mare/Constanța, punct de trecere a frontierei, spital, aeroport).

---

## Metodă

- Grilă statistică de **1×1 km** (EPSG:3035 LAEA, identificator GEOSTAT), ~240.000 de celule locuite pe teritoriul României.
- Fiecare sursă de date (relief, climă, hidrografie, hazard etc.) este redusă la **valori per celulă** printr-un pipeline ETL în Python (rasterizare la 100 m + agregare pe blocul de 10×10 subcelule: dominanță, minim, distanță etc.).
- **DuckDB-WASM** este sursa canonică a cifrelor: interoghează GeoParquet direct în browser.
- Profilul unei celule și seriile temporale climatice folosesc suplimentar un cub multianual.

---

## Surse de date

- **Populație (grilă 1 km):** Institutul Național de Statistică — Recensământul Populației și Locuințelor 2021; format grilă **EUROSTAT / GEOSTAT**. [INS](https://www.recensamantromania.ro/) · [Eurostat GEOSTAT](https://ec.europa.eu/eurostat/web/gisco/geodata/reference-data/population-distribution-demography/geostat)
- **Limite administrative:** ANCPI.
- **Relief / forme de relief:** model geomorfometric + **FABDEM** (model de teren).
- **Climă (zilnic + serii 1961–prezent):** [Administrația Națională de Meteorologie](https://www.meteoromania.ro/).
- **Prognoză temperatură:** [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) (CC BY 4.0).
- **Prognoză calitatea aerului:** [Copernicus Atmosphere Monitoring Service (CAMS)](https://atmosphere.copernicus.eu/) (CC BY 4.0).
- **Avertizări meteo:** ANM (feed-uri publice de avertizări/nowcasting).
- **Hidrografie (lacuri, cursuri de apă):** [OpenStreetMap](https://www.openstreetmap.org/) (ODbL).
- **Rețea rutieră (rutare):** [OpenStreetMap](https://www.openstreetmap.org/) via [Geofabrik](https://download.geofabrik.de/) (ODbL).
- **Arii protejate:** ANANP.
- **Spitale:** ANMCS. · **Aeroporturi:** [OurAirports](https://ourairports.com/).
- **Puncte de trecere a frontierei:** Poliția de Frontieră Română.
- **Hazard la inundații (scenarii 10% / 1% / 0,1%):** hărțile de hazard din planurile de management al riscului la inundații.
- **Zone de conflict cu ursul brun:** zonarea managementului populației de urs brun.

> Notă: unele seturi de date sunt intersectate/reproiectate în procesare; verificați întotdeauna sursa oficială înainte de utilizări cu cerințe ridicate de precizie.

---

## Soluții open source folosite

**Frontend:** [Vite](https://vitejs.dev/) · [TypeScript](https://www.typescriptlang.org/) · [MapLibre GL JS](https://maplibre.org/) · [DuckDB-WASM](https://duckdb.org/docs/api/wasm/overview) · [uPlot](https://github.com/leeoniya/uPlot) · [marked](https://marked.js.org/) · fundal [OpenFreeMap](https://openfreemap.org/) / [OpenMapTiles](https://openmaptiles.org/).

**Pipeline / date:** [Python](https://www.python.org/) · [GeoPandas](https://geopandas.org/) · [pyogrio](https://pyogrio.readthedocs.io/) · [rasterio](https://rasterio.readthedocs.io/) · [SciPy](https://scipy.org/) · [NumPy](https://numpy.org/) · [xarray](https://xarray.dev/) + [Zarr](https://zarr.dev/) · [DuckDB](https://duckdb.org/) · [GDAL/OGR](https://gdal.org/).

**Rutare:** [PostgreSQL](https://www.postgresql.org/) + [PostGIS](https://postgis.net/) + [pgRouting](https://pgrouting.org/) · [osm2pgrouting](https://github.com/pgRouting/osm2pgrouting) · [osmium](https://osmcode.org/osmium-tool/).

**Infrastructură:** [Docker](https://www.docker.com/) · [Caddy](https://caddyserver.com/) · GitHub Actions.

---

## Statut

Prototip în dezvoltare. Cifrele se validează continuu contra rapoartelor pipeline-ului. Feedback și contribuții: prin [depozitul GitHub](https://github.com/geospatialorg/unde-locuiesc-romanii).
