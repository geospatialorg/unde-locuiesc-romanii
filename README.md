# Unde locuiesc românii?

Atlas interactiv al populației României pe grila statistică de 1 km — interogări multi-criteriu
(relief, climă, distanțe, demografie), integral în browser. Vezi [PLAN.md](PLAN.md) pentru
proiectarea completă.

## Pornire rapidă (Docker)

Datele de intrare stau în `data/` (negit-uite). Produsele generate ajung în `data/out/`.

```bash
# 1. Rulează pipeline-ul ETL (generează parquet + registry + limite în data/out)
docker compose build pipeline
docker compose run --rm pipeline python -m ulr_pipeline.run all

# 2. Pornește serverul de date (:8090), aplicația (:5173) și serviciile live
docker compose up data web warnings forecast
```

Aplicația: http://localhost:5173 · Produsele de date: http://localhost:8090

## Structură

```
pipeline/   ETL Python (container): grilă 1 km EPSG:3035 → parquet/registry/limite
app/        Frontend Vite + React + TS: MapLibre + DuckDB-WASM + uPlot
infra/      Caddyfile (server de date cu CORS + range requests)
data/       intrări (gpkg/tif/nc) + staging/ + out/ (produse)
docs/plan/  documentele de proiectare
```

## Stare curentă (v0)

Funcțional cap-coadă pe datele de start: grila RPL 2021 (240.290 celule, EPSG:3035),
limite administrative, forme de relief (ierarhia formală), **intravilan (perimetrul construit
al localităților, ANCPI/CNGCFT)** clasificat oraș/sat **și acces la rețeaua de gaze naturale**
(atribut per localitate, `conectata_gaz`), FABDEM (altitudine/pantă), distanțe
frontieră/litoral, climă zilnică MeteoRomania ian–iul 2026. Preseturile și constructorul de
filtre rulează în DuckDB-WASM, cu cifre identice cu `data/out/validation_report.md`
(test golden). Click pe hartă → fișa celulei cu grafic climatic uPlot pe județ.

Mecanisme UI: o întrebare poate avea **variante** comutabile rapid (ex. „La oraș” ↔ „La sat”,
pe intravilan), fără ca ambele să apară în lista implicită; secțiunea **„Alte întrebări”**
(`MORE_PRESETS` în `app/src/query/presets.ts`) ține o listă extinsă, ascunsă implicit.

Harta răspunsului codifică **densitatea**, nu doar apartenența: fiecare celulă potrivită e
colorată pe o rampă secvențială de roșuri după valoarea măsurii pe celulă (celula are 1 km²,
deci valoarea = densitatea pe km²), pe scară logaritmică 1 → 10.000, cu legendă pe hartă.
Celulele potrivite dar nelocuite apar într-un gri discret („zonă potrivită, nelocuită”).

**Căutare pe hartă** (`gazetteer.json`, generat la export): 3.186 UAT-uri (limite LAU) +
13.656 localități (din intravilan), cu potrivire fără diacritice, dezambiguizare pe județ și
tip (municipiu/oraș/comună · sat/localitate urbană), zbor la limitele entității + marcaj.
Fără servicii externe — gazetteer-ul e derivat integral din datele proiectului.

Adăugarea unui parametru nou = un pas de pipeline care scrie o coloană per `cell_id`
+ o intrare în `registry_def.py`. UI-ul se generează din registru.

## Avertizări meteo în timp aproape real

MeteoRomania publică **două** tipuri de mesaje, în feed-uri XML distincte, ambele preluate de serviciul `warnings`:

- **nowcasting** (`avertizari-nowcasting-xml-gis.php`) — imediate (ore), „zonă delimitată" cu poligon propriu;
- **atenționări / avertizări generale** (`avertizari-xml.php`) — valabile pe intervale lungi (zile), cu geometrie pe fiecare `<judet>`/`<zona>`, fiecare cu cod de culoare propriu.

Serviciul `warnings` (container, buclă la `WARN_INTERVAL` secunde, implicit 600) taie geometriile
ambelor feed-uri peste grila de 1 km și publică în `data/out/live/`:

- `warnings.json` — sumar pe **sursă** și **cod de severitate** + lista mesajelor (interval, fenomen, județe/zone, populație);
- `warnings_cells.parquet` — `cell_id × source → codul maxim` (join în DuckDB → combinabil cu orice măsură: „câți vârstnici sub cel puțin o avertizare");
- `warnings_cell_msg.parquet` — `cell_id × mesaj` (pentru afișarea **distinctă** a fiecărui mesaj, măsură-conștient);
- `warnings.geojson` — geometriile pentru hartă, cu proprietățile `source` și `group_id` (mesajul).

Astfel aplicația răspunde la „câți români sunt afectați acum de avertizări meteo?" fără a atinge
meteoromania.ro (fără CORS), cu cifra calculată canonic în DuckDB (identică cu join-ul server-side).

Meteo este **prima întrebare** din listă (marcată „⚠ ACUM"), integrată printre întrebările clasice:
harta afișează la un moment dat **un singur tip** de informație — fie avertizările, fie masca unei
întrebări clasice. În modul meteo, panoul arată total combinat + defalcare pe cele două surse și pe
cod; fiecare mesaj poate fi afișat **distinct** (click → doar zona lui pe hartă + populația proprie)
sau **cumulat**. Harta desenează zonele nowcasting (saturate) peste atenționările generale
(umplere discretă, intensitate cumulativă unde se suprapun mesaje). Doar geometriile cu **cod activ**
(culoare ≥ galben) sunt evidențiate — poligoanele-context de tip „județ întreg, doar zona montană
avertizată" (culoare verde) sunt excluse, ca să nu supraevalueze populația.

```bash
docker compose run --rm warnings python -m ulr_pipeline.warnings_live once   # o reîmprospătare manuală
docker compose up -d warnings                                                # buclă operațională
```

## Prognoze meteo și de calitate a aerului

Serviciul `forecast` actualizează independent două surse și publică produsele în
`data/out/live/forecast/`:

- **ECMWF Open Data, IFS determinist 0,25°**: ultima rulare `oper/fc/sfc`, extremele
  de temperatură la 2 m pe intervale de 3 ore (`mn2t3`, `mx2t3`), pașii 3–120;
- **CAMS Europe air-quality ensemble, 0,1°**: prognoza de la 00:00 UTC, pașii
  orari 0–96, pentru PM2.5, PM10, NO₂, O₃ și SO₂ la nivelul 0.

ECMWF Open Data nu cere autentificare. Pentru CAMS este necesar un cont în
[Atmosphere Data Store](https://ads.atmosphere.copernicus.eu/), acceptarea manuală a
licenței datasetului **CAMS European air quality forecasts** din formularul de download și
un personal access token. Configurația locală poate porni de la `.env.example`:

```bash
cp .env.example .env
# editează local ADS_API_KEY; .env și .cdsapirc sunt ignorate de git
```

Variabile de mediu:

- `ADS_API_KEY` — personal access token ADS; nu este necesar pentru produsul meteo;
- `ADS_API_URL` — implicit `https://ads.atmosphere.copernicus.eu/api`;
- `FORECAST_INTERVAL` — intervalul buclei în secunde, implicit `21600` (6 ore).

```bash
# actualizare unică; fără ADS_API_KEY se actualizează doar vremea și se păstrează aerul anterior
docker compose run --rm forecast python -m ulr_pipeline.forecast_live once

# serviciu periodic
docker compose up -d forecast
```

Datele sunt tăiate la caseta România cu margine (`N 49 / V 20 / S 43 / E 30`).
Extremele ECMWF în Kelvin sunt convertite în °C și atribuite datei locale
`Europe/Bucharest` după mijlocul fiecărui interval de 3 ore. Pentru CAMS, categoria
particulelor PM2.5/PM10 se calculează din media mobilă de 24 de ore, iar categoria
NO₂/O₃/SO₂ din concentrația orară. Categoria zilnică publicată este cea mai rea dintre
cei cinci poluanți și toate orele zilei, pe ranguri 0–5.

Pragurile dintre categorii sunt:

| Poluant | Praguri în µg/m³ (rangurile 0 → 5) |
|---|---|
| PM2.5 | 10, 20, 25, 50, 75 |
| PM10 | 20, 40, 50, 100, 150 |
| NO₂ | 40, 90, 120, 230, 340 |
| O₃ | 50, 100, 130, 240, 380 |
| SO₂ | 100, 200, 350, 500, 750 |

Produsele logice din `manifest.json` sunt: caniculă (`tmax >= 35°C`), ger
(`tmin <= -10°C`) și aer slab sau mai rău (`aqi_rank >= 3`). Aceste praguri sunt
instrumente de screening pe prognoze de model, nu avertizări oficiale, măsurători la
stație, diagnostic medical sau un AQI oficial observat. Zilele parțiale de la începutul
și sfârșitul rulării sunt excluse din produse și din calculele de expunere.

Fiecare produs Parquet rămâne pe grila nativă a sursei; fișierele de mapare versionate
`weather_map_<hash>.parquet` și `air_map_<hash>.parquet` leagă fiecare `cell_id` de cel mai apropiat
`grid_id`. `manifest.json` este publicat atomic și indică fișierele imuabile ale
rulării curente; se păstrează cel mult patru rulări recente per sursă. Dacă o sursă
eșuează, referința sa validă anterioară rămâne disponibilă.

Interpretarea populației folosește **populația rezidentă la recensământul 2021** din
celula de 1 km, asociată prognozei la cel mai apropiat nod. Rezultatul nu reprezintă
populația aflată fizic în zonă la ora prognozei și nici expunerea individuală.

**Atribuire:** date meteo © ECMWF Open Data, CC BY 4.0; date de compoziție atmosferică
Copernicus Atmosphere Monitoring Service (CAMS), CC BY 4.0. Dataset CAMS:
[DOI 10.24381/a4005cee](https://doi.org/10.24381/a4005cee).

## Partajare

Butonul „🔗 Partajează harta" copiază în clipboard un link care conține **toată starea curentă** —
modul (avertizări/prognoză/întrebare), măsura, filtrele, selecția de avertizare sau prognoză, poziția și zoom-ul hărții,
plus celula selectată — codate compact în fragmentul URL (`#s=…`, base64url peste JSON, tolerant
la diacritice). Oricine deschide link-ul primește exact aceeași hartă. Starea din link e curățată
automat față de registrul curent (variabile scoase/redenumite sunt ignorate, nu blochează harta).

## Dashboardul de analiză

Butonul „📊 Analiză" deschide un dashboard **generat integral din registru** — orice variabilă
nouă din pipeline devine automat analizabilă, fără cod nou în aplicație:

- **explicații în limbaj natural**, generate din statistici ponderate („Jumătate dintre români
  trăiesc sub 161 m altitudine; 80% între 45 și 503 m");
- **histograme interactive** (uPlot) ale populației pe valorile variabilei — ponderate cu măsura
  aleasă (persoane/femei/vârstnici…), nu cu suprafața;
- **comparații** între orice două arii (România ↔ județe), cu distribuții suprapuse în procente
  și propoziție de comparație a medianelor;
- **clasamentul județelor** după media ponderată, cu ariile comparate evidențiate;
- comutator „aplică filtrul curent" — analiza se poate restrânge la selecția activă din hartă.

Cuantilele ponderate se calculează pe histograma cumulativă (120 de bin-uri fine), în browser,
din aceleași interogări DuckDB ca restul aplicației.

## Acces la spitale + rutare reală (pgRouting)

Registrul ANMCS (`data/spitale_anmcs.gpkg`, 718 unități active) alimentează variabila
`dist_hospital_km` (linie dreaptă, cKDTree pe grilă) și întrebarea „Câți români locuiesc
departe de un spital?" (praguri 10/25/50 km). Pentru distanța **pe șosea**, stiva opțională
de rutare rulează integral local:

- **`routing-db`** — PostGIS + pgRouting cu graful rutier OSM România (~197k muchii;
  clase motorway→unclassified, costuri în secunde din vitezele pe clase);
- **`routing-import`** — descarcă extractul Geofabrik (cache în `data/osm/`), filtrează cu
  osmium, importă cu osm2pgrouting și ancorează spitalele la rețea;
- **`routing-api`** (`:8091`) — `GET /route?lon&lat` → cel mai apropiat spital **pe drum**
  (Dijkstra one-to-many peste cei mai apropiați 6 candidați euclidieni), cu timp, km și
  geometria traseului.

```bash
docker compose up -d routing-db
docker compose run --rm routing-import     # o singură dată (~10 min cu tot cu descărcare)
docker compose up -d routing-api
```

Aceeași stivă rutează și către **mare** (`to=sea` — destinație fixă: Constanța, nu cel mai
apropiat punct arbitrar de pe litoral), **frontieră** (`to=border`), **puncte de trecere a
frontierei** (`to=crossing`) și **aeroporturi** (`to=airport`, din
`aeroporturi_romania.geojson` — OurAirports, 18 aeroporturi). În fișa celulei apar **ambele valori**: distanța în linie dreaptă (până la mare, până
la linia de frontieră, până la cel mai apropiat punct de trecere) **și** ruta reală pe șosea (km,
minute, plus numele punctului de trecere și timpul de așteptare estimat). Notă: cel mai apropiat
punct de trecere în linie dreaptă poate diferi de cel mai rapid pe șosea (rețeaua rutieră) — se
afișează explicit ambele.

În aplicație: click pe orice celulă → fișa arată „Acces rutier la spital" (minute, km,
unitatea) și desenează traseul pe hartă, plus rutele către mare/frontieră ca text. Fără serviciul
pornit, fișa afișează doar distanțele în linie dreaptă + instrucțiunea de pornire. Notă: rețeaua exclude drumurile
rezidențiale/de serviciu (ultimul kilometru în localitate e aproximat); registrul ANMCS
include toate unitățile sanitare acreditate/în acreditare, nu doar spitalele de urgență —
filtrarea pe tip de unitate e un pas următor natural.

## Date climatice actualizate zilnic

Grilele zilnice de temperatură și precipitații (opendata MeteoRomania) se actualizează automat:
serviciul **`climate-cron`** descarcă zilnic la **10:00 (ora României)** fișierele NetCDF ale
**anului curent**, le validează, le înlocuiește în `data/` și re-asamblează produsele
(`climate.parquet`, seriile climatice județene, `registry.json`). Aplicația preia datele noi
la următoarea încărcare (Caddy servește cu `no-cache`).

```bash
docker compose up -d climate-cron           # pornește cron-ul (10:00 zilnic)
# actualizare manuală acum:
docker compose run --rm pipeline python -m ulr_pipeline.climate_refresh once
```

Anul e derivat automat (`ULR_CLIMATE_YEAR`, implicit anul curent), deci **la trecerea în alt an
URL-ul și numele fișierelor se schimbă singure** — se modifică doar cifra anului. Ca să reziste
la schimbarea anului, coloanele climatice **nu poartă anul în nume** (`tmean`, `precip_total`,
`hot_days`…); anul apare doar în etichete (din `registry.climateYear`). Ora se schimbă din
`CRON_HOUR`/`CRON_MIN`; `RUN_ON_START=1` forțează o actualizare la pornire.

## Cubul climatic Zarr (1961–prezent) și analiza multianuală

Grilele zilnice MeteoRomania 1961–prezent (tmin, tmax, precipitații; ~200 de fișiere NetCDF,
7,7 GB) sunt convertite într-un **cub Zarr omogenizat** — `data/out/climate.zarr`, dims
`(time, lat, lon)` pe grila istorică 483×972 (0,01°). Fișierele anului curent („synop") au
domenii mai mari și **decalate** față de laticea istorică (~0,006°) — se reindexează nearest
cu toleranță de semi-pas. Rulare: `… ulr_pipeline.run climate_zarr` (rebuild complet, ~5 min).

Din cub, pasul `climate_history` calculează per celulă caracterizarea multianuală 1961–2025
(în spiritul analizelor ANM): normalele 1961–1990 și 1991–2020 (temperatură, precipitații),
**încălzirea** dintre normale, **tendința** temperaturii (°C/deceniu, OLS), **schimbarea
precipitațiilor (%)** și **anomalia anului 2025**. Variabilele intră în registru (grupul
„Climă multianuală") — deci în filtre, fișa celulei și dashboardul de analiză, automat.
Același pas publică seria anuală pe județ 1961–prezent; în fișa unei locații, graficul climatic
poate fi comutat între zilele anului curent și evoluția anuală completă.
Cubul fiind servit de Caddy, e pregătit pentru citire directă în browser cu Zarrita (planul F4).

## Pipeline — pași individuali

```bash
docker compose run --rm pipeline python -m ulr_pipeline.run grid        # definiția grilei + demografie
docker compose run --rm pipeline python -m ulr_pipeline.run admin       # join UAT / județe
docker compose run --rm pipeline python -m ulr_pipeline.run landform    # forme de relief
docker compose run --rm pipeline python -m ulr_pipeline.run terrain     # altitudine + pantă (FABDEM)
docker compose run --rm pipeline python -m ulr_pipeline.run border      # distanțe frontieră / litoral
docker compose run --rm pipeline python -m ulr_pipeline.run climate     # agregate climatice 2026
docker compose run --rm pipeline python -m ulr_pipeline.run export      # asamblare + registry + limite
docker compose run --rm pipeline python -m ulr_pipeline.run validate    # raport de validare
```
