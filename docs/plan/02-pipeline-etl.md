# 02 — Pipeline-ul de date (ETL)

Pipeline-ul rulează offline (local sau în CI), transformă sursele brute în produsele cloud-native
consumate de aplicație și publică totul versionat în object storage. Este proiectat ca **funcție pură**:
`surse brute + catalog → produse publicate`, reproductibilă bit-cu-bit.

## 1. Stack și organizare

- **Python 3.12**, mediu gestionat cu **uv** (`pyproject.toml` + lockfile).
- Biblioteci: `xarray`, `rioxarray`, `dask` (procesare pe chunks), `zarr` v3 (sharding),
  `geopandas`, `pyogrio`, `exactextract` (statistici zonale exacte pe fracțiuni de celulă),
  `whitebox` (geomorfoni, derivate DEM), `duckdb` (asamblare tabele + validări SQL),
  `rio-cogeo` (COG), `pmtiles`/`tippecanoe` (tile-uri vector), `planetiler` (bazmap OSM),
  `pandera` (contracte de date), `pyproj`.
- Orchestrare: **just** (rețete incrementale per sursă) — simplu, transparent; dacă graful de
  dependențe crește, migrăm rețetele în **Snakemake** fără a schimba codul.

```
pipeline/
├── justfile                  # just ingest-dem, just derive-climate, just export, just publish…
├── pyproject.toml
└── src/ulr_pipeline/
    ├── grid.py               # definiția grilei: bbox, n_cols/n_rows, cell_id ↔ (row,col) ↔ (E,N) ↔ grid_id GEOSTAT
    ├── sources/              # un modul per sursă: download scriptat + checksum + citire normalizată
    │   ├── ins_grid.py  eurostat_grid.py  dem.py  clc.py  chelsa.py  euhydro.py  ghsl.py  …
    ├── derive/
    │   ├── zonal.py          # exactextract: fracțiuni/medii din rastere & poligoane → per celulă
    │   ├── distance.py       # rastere de distanță (GDAL proximity) pe grila 1 km: mare, frontieră, pădure, râu…
    │   ├── terrain.py        # pantă, expoziție, TPI/TRI, geomorfoni (Whitebox)
    │   ├── access.py         # timpi de acces: OSRM/Valhalla local pe OSM, ținte din SIIIR/MS/CFR
    │   ├── climate.py        # normale, indici, delte proiecții
    │   └── timeseries.py     # serii lunare (NDVI, climă) → cub temporal + agregate per UAT
    ├── export/
    │   ├── to_parquet.py     # tabele tematice GeoParquet
    │   ├── to_zarr.py        # cubul GeoZarr v3
    │   ├── tiles.py          # PMTiles limite + bazmap; COG-uri tematice; tile-uri „id raster” (v2 randare)
    │   └── stats.py          # statistici per variabilă (percentile țară/județ) → registru + stats.parquet
    ├── validate/             # pandera + verificări SQL (totaluri, intervale, consistență)
    └── publish.py            # rclone → R2, prefix versionat, manifest.json cu hash-uri
```

Fiecare sursă trece prin aceleași etape: **download** (URL-uri fixate + checksum în `sources.yaml`) →
**normalizare** (CRS 3035, decupare la bbox) → **derivare per celulă** → **staging**
(`data/staging/<grup>.parquet`, cheia `cell_id`) → **export** → **validare** → **publicare**.
Rețetele `just` sunt incrementale: se re-rulează doar ce s-a schimbat.

## 2. Derivarea per celulă — metode standard

| Tip sursă | Metodă | Exemple |
|---|---|---|
| Raster < 1 km (WorldCover 10 m, GHSL 100 m) | agregare exactă la celulă: fracțiuni pe clase, medii | % pădure, % construit, impermeabilizare |
| Raster ≈ 1 km (CHELSA) | reeșantionare aliniată la grilă (bilinear pt. continue) | normale climatice |
| Raster > 1 km (ERA5-Land 9 km) | interpolare + notă de rezoluție în registru | serii lunare lungi |
| Poligoane (UAT, unități de relief, zone inundabile) | `exactextract`: clasa majoritară + fracțiuni | apartenență relief, fracțiune inundabilă |
| Linii/puncte (râuri, țărm, gări, spitale) | rastere de distanță euclidiană; pentru „timp de acces” — rutare pe rețea | dist. la mare, timp la UPU |
| Tabele pe UAT/județ (Tempo, ANAF) | join pe SIRUTA → atașare la celule prin apartenență | salariu mediu, venituri UAT |
| Vecinătăți | focal statistics pe grila 1 km (raze 1/3/5 km) | % pădure în raza de 3 km |

Timpii de acces (F7): rulăm OSRM/Valhalla local pe extractul OSM România; origini = centroidele
celulelor locuite (~120k), destinații = seturi mici de ținte (spitale, licee, gări, reședințe);
`table service` pe loturi → minute per celulă per țintă. Precalculat integral — în browser ajunge
doar rezultatul.

## 3. Produsele publicate

### 3.1 GeoParquet — tabelele tematice (motorul de interogare)

O tabelă lată per grup tematic, toate cu cheia `cell_id` (join leneș în DuckDB):

```
grid/core.parquet       # cell_id, grid_id, col, row, lon, lat, judet, siruta, degurba, sdc_flag,
                        # pop_total, pop_m, pop_f, pop_0_14, … (demografie + admin)
grid/env.parquet        # relief, distanțe, apartenențe, ocupare teren
grid/climate.parquet    # normale + indici + delte proiecții (agregate filtrabile)
grid/hazard.parquet     # inundații, alunecări, seism
grid/services.parquet   # timpi de acces, densități de servicii
grid/economy.parquet    # economie, nivel de trai
grid/satellite.parquet  # compozite și tendințe satelitare
grid/osm_derived.parquet# tot ce moștenește ODbL (izolat pentru licență)
grid/embedding.parquet  # cell_id + vector PCA 32-dim (float32) pt. similaritate
uat/uat.parquet         # fișe UAT: indicatori agregați + serii recensăminte istorice
uat/uat_timeseries.parquet # serii temporale pre-agregate per UAT (climă lunară, NDVI…)
stats/stats.parquet     # percentile per variabilă, la nivel de țară și județ
```

Detalii de layout, critice pentru performanța range-request:

- rânduri **sortate pe curbă Hilbert** a centroidelor (localitate spațială → filtrele spațiale ating
  puține row groups);
- **row groups de ~32k rânduri** (~8 grupuri pe țară) cu statistici min/max per coloană
  (predicate pushdown în DuckDB);
- compresie ZSTD; `float32` pentru continue, dicționar pentru categoriale;
- metadate GeoParquet 1.1 (coloană `geometry` doar în `uat.parquet`; tabelele de grilă păstrează
  doar `cell_id` + lon/lat — geometria celulelor e implicită);
- dimensiune estimată: `core+env` ≈ 30–60 MB; totalul tuturor tabelelor ≈ 300–500 MB, din care o
  interogare tipică citește **sub 5 MB** (doar coloanele filtrate/agregate).

### 3.2 GeoZarr — cubul raster (vizualizare + profile + serii)

```
cube.zarr/            (Zarr v3, sharded, consolidated metadata, conform GeoZarr: CF + grid_mapping)
├── x (float64[~700])  y (float64[~550])  spatial_ref (EPSG:3035)
├── pop/     total, f, m, age_0_14, …        (int32,  y·x)
├── dem/     alt, slope, aspect, tpi, geomorphon(int8)
├── dist/    sea, border, forest, river, lake
├── clim/    tmean_1991_2020, prec_1991_2020, …          (float32, y·x)
│            tmean_monthly (time=12, y, x)
│            tmean_proj (scenario=3, period=2, y, x)
├── s2/      ndvi_monthly (time≈120, y, x)   # chunking (12, 128, 128)
└── mask/    land (bool), sdc (int8)
```

- chunking 2D: `256×256` → ~6 chunks/variabilă, un shard per variabilă (puține obiecte, citire
  full-country într-o singură cerere);
- serii temporale: chunks `(12, 128, 128)` — compromis între „profil temporal al unei celule”
  (citește coloana de timp) și „harta unui moment” (citește un plan);
- compresie zstd + shuffle; pentru float-uri zgomotoase (NDVI) — `bitround` la precizia declarată
  în registru;
- rol în aplicație: colorarea oricărei variabile ca strat continuu, profilul temporal al unei
  celule, agregări pe măști ad-hoc. **Nu** este folosit pentru cifrele oficiale (acelea vin din
  DuckDB — vezi 04).

### 3.3 PMTiles, COG și tile-urile de identificare

- `basemap.pmtiles` — bazmap România generat cu Planetiler din extractul OSM, stil propriu cu
  diacritice corecte (F0);
- `boundaries.pmtiles` — UAT/județe/regiuni/unități de relief/cartiere, cu `siruta`/coduri ca
  `promoteId` pentru hover și fișe;
- `hillshade.pmtiles` (raster) din Copernicus DEM;
- COG-uri tematice pentru straturi „de context” la rezoluție nativă (WorldCover, hazard raster),
  servite prin `maplibre-cog-protocol`;
- **`cellid.pmtiles` (v2, faza de optimizare):** tile-uri raster în care valoarea RGB a fiecărui
  pixel codifică `cell_id` — permite recolorarea instantanee a măștii în shader (vezi 03 §4.3);
  generate cu GDAL din grila reproiectată în 3857, z5–z12.

### 3.4 Registrul publicat

`registry.json` (compilat din YAML-uri) + `manifest.json` (versiune, hash-uri, praguri SDC,
atribuirile de licență). Aplicația le încarcă la pornire; UI-ul se construiește din registru.

## 4. Asigurarea calității datelor

1. **Contracte pandera** per tabelă: tipuri, intervale valide, non-null, unicitatea `cell_id`.
2. **Reconciliere cu totaluri oficiale:** `SUM(pop_total)` = populația României publicată de INS
   (toleranță documentată din SDC); populația pe județe = Tempo; abaterile se raportează în
   `validation_report.md` publicat lângă date.
3. **Consistență între produse:** pentru 20 de variabile-eșantion, valorile din Zarr = valorile din
   Parquet pe 1000 de celule aleatoare (test automat).
4. **Teste golden pentru preseturi:** cele 6 întrebări au răspunsuri calculate în pipeline (DuckDB
   nativ); aplicația trebuie să obțină aceleași cifre (test e2e — vezi 03 §8).
5. **Mini-fixture:** un set sintetic 10×10 celule cu toate produsele, folosit în testele aplicației
   și în CI (nu depindem de datele mari în teste).

## 5. Publicare

```
r2://ulr-data/
├── v2026.10/            # imutabil
│   ├── grid/*.parquet  cube.zarr/  tiles/*.pmtiles  cogs/*.tif
│   ├── registry.json  manifest.json  validation_report.md
└── latest → v2026.10    # doar un pointer (fișier JSON), nu symlink
```

- `rclone` cu `--checksum`; CORS: `GET, HEAD` + `Range` de pe domeniul aplicației;
  `Cache-Control: public, max-age=31536000, immutable` (prefixele sunt versionate);
- aplicația citește `latest.json` la pornire dar poate fixa versiunea (`?data=v2026.10`) —
  orice permalink include versiunea de date, deci analizele rămân reproductibile după actualizări.
