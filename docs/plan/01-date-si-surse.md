# 01 — Modelul de date și catalogul de surse

## 1. Grila de referință

- **CRS:** EPSG:3035 (ETRS89-LAEA) — sistemul grilei statistice europene, folosit de INS/Eurostat
  pentru grila de recensământ. Toate variabilele se calculează în acest sistem; reproiectarea
  se face doar la afișare.
- **Rezoluție:** 1 km (celula atomică). Unde sursele permit (GHSL, WorldCover), păstrăm în pipeline
  și produse intermediare la 100 m pentru derivări mai precise (ex. fracțiunea de intravilan din celulă),
  dar produsul publicat este la 1 km. O grilă de 100 m poate deveni un „nivel de zoom” viitor fără
  schimbări de arhitectură.
- **Extindere:** dreptunghiul de încadrare al României în EPSG:3035, aliniat la multipli de 1000 m —
  aproximativ 700 × 550 celule (~380.000 în dreptunghi, din care ~240.000 pe teritoriul național).
- **Identificatori:**
  - `grid_id` — identificatorul GEOSTAT standard (`CRS3035RES1000mN…E…`), păstrat pentru
    interoperabilitate cu Eurostat/INS;
  - `cell_id` — `uint32` compact, `row * n_cols + col` față de colțul NV al dreptunghiului.
    Este cheia de join în toate tabelele Parquet și indexul implicit în cubul Zarr.
    Conversia `(lon, lat) → (E, N) → (col, row) → cell_id` este o formulă închisă — interacțiunea
    pe hartă (hover/click) nu are nevoie de niciun tile de interogare.

## 2. Modelul semantic: registrul de variabile

Registrul (`catalog/variables/*.yaml`) este sursa de adevăr pentru pipeline, UI și documentație.
Schema unei variabile:

```yaml
# catalog/variables/clima.yaml (fragment)
- id: clim.prec.annual.1991_2020
  group: clima
  label: { ro: "Precipitații medii anuale (1991–2020)", en: "Mean annual precipitation" }
  description:
    ro: >
      Suma medie anuală a precipitațiilor pentru normala climatologică 1991–2020,
      reeșantionată pe grila de 1 km.
  unit: "mm/an"
  dtype: float32
  storage:
    parquet: { file: climate.parquet, column: prec_annual_1991_2020 }
    zarr:    { array: clim/prec_annual_1991_2020 }
  temporal: { type: static, reference: "1991-2020" }
  source: { ref: chelsa, vintage: "2024" }        # cheie în sources.yaml
  methodology: metodologie/clima.md#normale
  aggregation: pop_weighted_mean                   # cum se agregă pe o selecție de celule
  stats: { min: 380, p5: …, p50: …, p95: …, max: 1400 }   # completat de pipeline
  ui: { format: "0,0", slider: [300, 1500], phase: F4 }
```

Tipuri de variabile:

- **numerice continue** (altitudine, precipitații, NDVI, timp de acces) — filtre interval;
- **categoriale** (unitate de relief, clasă DEGURBA, clasă CLC dominantă, județ) — filtre apartenență,
  cu `categories: [{value, label, color}]`;
- **booleene** (în zonă inundabilă 1%, în zona de frontieră) — comutatoare;
- **serii temporale** (climă lunară, NDVI lunar, recensăminte istorice, proiecții pe scenarii) —
  dimensiune suplimentară `time` (și `scenario` pentru proiecții) în Zarr; în Parquet se păstrează
  doar agregate-cheie (medii, tendințe) pentru filtrare.

Grupuri planificate și ordinea de mărime a numărului de variabile (țintă totală: **400+**):

| Grup | Exemple | ~Nr. | Faza |
|---|---|---|---|
| `demografie` | populație totală, pe sex, grupe de vârstă, gospodării, etnie/limbă (dacă INS publică pe grilă), dinamică 2011→2021 | 40 | F1 |
| `locuire` | locuințe, suprafață medie, an construcție dominant, racord apă/canal/gaz (din recensământ) | 20 | F3 |
| `admin` | județ, UAT (SIRUTA), regiune, statut (municipiu/oraș/comună), DEGURBA, în zonă metropolitană | 15 | F1 |
| `relief` | altitudine, pantă, expoziție, TPI/TRI, geomorfoni, unitate de relief (formală), treaptă altitudinală | 25 | F1 |
| `apartenente` | distanță la: mare, frontieră (+ care frontieră), râu, lac, pădure, drum european, gară, oraș ≥30k; flag-uri „la mare”, „în zona de frontieră” etc. | 20 | F1 |
| `sol_geologie` | clasă de sol (ICPA/SoilGrids), textură, SOC, pH, litologie | 15 | F7 |
| `clima_prezent` | normale T/precipitații (4 perioade), lunare, indici (zile tropicale, grade-zile, De Martonne, SPI) | 60 | F4 |
| `clima_viitor` | aceleași pentru 2041–70 și 2071–2100 × scenarii SSP1-2.6/3-7.0/5-8.5 + delte față de prezent | 40 | F4 |
| `ocupare_teren` | fracțiuni CLC/WorldCover pe celulă, % pădure în raze de 1/3/5 km, impermeabilizare, fragmentare | 30 | F1–F7 |
| `hazard` | fracțiune inundabilă (3 scenarii), clasă susceptibilitate alunecări, ag seismic, intensitate MSK, index compus de expunere | 20 | F5 |
| `servicii_acces` | timp rutier la: spital/UPU, medic de familie, școală, liceu, gară, reședință de județ; nr. unități în 10/30 min | 40 | F7 |
| `economie_trai` | firme active, salariu mediu (județ), rată șomaj, marginalizare (atlasele BM), venituri proprii UAT/locuitor | 25 | F7 |
| `satelitar` | NDVI/EVI/NDWI/NDBI (compozite sezoniere + serii lunare), LST vară, lumini nocturne VIIRS, tendințe | 50+ | F7 |
| `istorie` | populație recensăminte 1930–2021 (crosswalk pe UAT), suprafață construită pe epoci GHSL 1975–2030, prezență pe hărți istorice | 20 | F7 |

## 3. Operaționalizarea conceptelor din întrebări

Fiecare concept „popular” are o **definiție implicită oficială/documentată + parametri ajustabili**
(slider în UI, cu nota metodologică alături). Acesta este contractul dintre modul ghidat și motorul de interogare:

| Concept | Definiție implicită | Parametri ajustabili | Sursa limitei |
|---|---|---|---|
| „la mare” | celule la < 5 km de linia țărmului Mării Negre | 1–30 km; alternativ: UAT-uri riverane litoralului | linia de coastă EU-Hydro / ANCPI |
| „lângă pădure” | distanța la cel mai apropiat corp de pădure ≥ 10 ha este < 1 km | distanța (0,5–5 km), suprafața minimă a pădurii, alternativ „% pădure în raza de 3 km ≥ 20%” | Copernicus HRL Forest / WorldCover |
| „la câmpie / deal / munte” | apartenența celulei la unitățile de relief (limite formale) | comutare pe trepte altitudinale (implicit: <300 m / 300–1000 m / >1000 m, praguri ajustabile) | limitele unităților de relief (set național, ex. geo-spatial.org) + DEM |
| „lângă apă (râu/lac)” | < 500 m de un râu cu ordin Strahler ≥ 3 sau < 1 km de un lac ≥ 50 ha | distanțe, ordin minim, suprafață minimă lac | EU-Hydro / cadastrul apelor ANAR |
| „la oraș / la sat” | implicit: statutul administrativ al UAT (municipiu/oraș vs. comună); alternativ DEGURBA pe celulă (urban dens / urban mic-suburban / rural) | comutator între cele două definiții (cifrele diferă — ocazie de educație statistică, afișăm ambele) | SIRUTA + GHS-SMOD |
| „în zona de frontieră” | < 30 km de frontiera de stat (definiția legală a zonei de frontieră) | 5–50 km; defalcare pe frontieră (UA/MD/BG/RS/HU) | limita de stat ANCPI |
| „în zonă inundabilă” | celulă cu fracțiune inundabilă > 0 la scenariul de probabilitate 1% | scenariul (10% / 1% / 0,1%), fracțiunea minimă | hărțile de hazard la inundații (ANAR, Directiva Inundații) |

Regulă generală: **modul ghidat afișează definiția folosită sub rezultat** („am considerat «la mare» =
la mai puțin de 5 km de țărm; modifică definiția”), transformând fiecare răspuns într-o mini-lecție
de metodologie.

## 4. Catalogul de surse

`catalog/sources.yaml` reține pentru fiecare sursă: denumire, editor, URL, licență, an/versiune,
mod de acces (download/API), pași de reproducere. Mai jos, catalogul de pornire (cel complet
trăiește în YAML):

### 4.1 Demografie și societate
| Sursă | Conținut folosit | Note |
|---|---|---|
| **INS — RPL 2021 pe grilă 1 km** | populație pe celulă + defalcări disponibile | sursa primară; formatul exact se confirmă la pasul următor |
| **Eurostat Census Grid 2021 (+ GEOSTAT 2006/2011/2018)** | populație 1 km, serii comparabile în timp | fundație publică sigură + dinamică pe grilă |
| **INS Tempo Online (API)** | serii pe UAT/județ: populație, natalitate, migrație, salarii, șomaj | pentru fișe UAT și tendințe |
| **Recensăminte istorice 1930–2011** | populație pe localitate/UAT | necesită crosswalk de limite (vezi §5) |
| **GHSL (JRC)**: GHS-POP, GHS-BUILT-S, GHS-SMOD | populație 100 m pe epoci 1975–2030, suprafață construită, grad de urbanizare | dinamică istorică + DEGURBA per celulă |
| **Atlasele zonelor marginalizate (BM/MMPS)** | marginalizare urbană/rurală pe sectoare de recensământ/UAT | nivel de trai |

### 4.2 Limite administrative și informale
| Sursă | Conținut | Note |
|---|---|---|
| **ANCPI / geoportal INSPIRE** | limite UAT, județe, limita de stat | oficiale |
| **SIRUTA (INS)** | nomenclatorul unităților | chei de join |
| **geo-spatial.org** | limite istorice UAT, unități de relief, seturi comunitare (ex. cartiere) | limite „formale și informale” |
| **OSM** | cartiere, localități componente, POI | licență ODbL — marcată în registru |
| **APIA/LPIS blocuri fizice** | utilizarea agricolă detaliată | acces/licență de clarificat; folosit la caracterizarea celulelor rurale |

### 4.3 Relief, sol, geologie
| Sursă | Derivate per celulă |
|---|---|
| **Copernicus DEM GLO-30 / FABDEM** | altitudine (medie/min/max), pantă, expoziție, TPI, TRI, rugozitate, geomorfoni (10 clase) |
| **Unități de relief (set național)** | apartenența formală: Carpații Orientali, Podișul Moldovei, Câmpia Română… |
| **ICPA 1:200k + SoilGrids 250m** | clasă de sol, textură, pH, carbon organic |
| **Zonarea seismică P100-1** | ag (accelerația de proiectare), perioada de colț Tc |

### 4.4 Climă (prezent și viitor)
| Sursă | Rol |
|---|---|
| **ROCADA (ANM)** | referință națională T/precipitații (validare) |
| **CHELSA 1 km** (normale + **CMIP6 ssp126/370/585**, 2041–70, 2071–2100) | setul principal — rezoluția se potrivește exact grilei |
| **E-OBS / ERA5-Land** | serii lunare lungi pentru grafice temporale |
| **Indici derivați** | zile tropicale, nopți tropicale, grade-zile încălzire/răcire, indice De Martonne, SPI/SPEI |

### 4.5 Hidrografie, mare, hazard
| Sursă | Derivate |
|---|---|
| **EU-Hydro / ANAR** | distanță la râu (pe ordine Strahler), la lac, densitatea rețelei; linia țărmului |
| **Hărți hazard inundații (ANAR, Directiva 2007/60, ciclul 2)** | fracțiunea inundabilă a celulei la 10% / 1% / 0,1% |
| **ELSUS v2 (JRC) / hărți naționale de alunecări** | clasă de susceptibilitate |
| **P100-1 + studii INFP** | expunere seismică |

### 4.6 Ocuparea terenului și date satelitare
| Sursă | Derivate |
|---|---|
| **CORINE Land Cover + CLC+ Backbone, ESA WorldCover 10 m, Copernicus HRL** | fracțiuni pe clase, % pădure în vecinătăți, impermeabilizare |
| **Sentinel-2** | compozite sezoniere NDVI/EVI/NDWI/NDBI + serii lunare (cub temporal) |
| **MODIS/Sentinel-3 LST** | temperatura suprafeței vara (insule de căldură) |
| **VIIRS Nighttime Lights** | radianță medie anuală + tendință (proxy activitate economică) |
| **CAMS / calitateaer.ro** | PM2.5, NO₂ medii anuale |

### 4.7 Servicii, economie, nivel de trai
| Sursă | Derivate |
|---|---|
| **SIIIR (Min. Educației)** + rezultate EN/BAC | școli, distanță/timp de acces, rezultate agregate pe localitate |
| **Min. Sănătății / CNAS** | spitale, UPU, farmacii → timpi de acces |
| **OSM rutier + OSRM/Valhalla (offline)** | matrici de timp de acces per celulă către ținte (spital, liceu, gară, reședință de județ) |
| **CFR / GTFS unde există** | acces la transport public |
| **ONRC / data.gov.ro, ANAF, MDLPA** | firme active, execuții bugetare UAT (venituri proprii/locuitor — relevant pentru reforma administrativă) |
| **ANCOM** | acoperire broadband (de clarificat accesul) |

### 4.8 Istorie
| Sursă | Derivate |
|---|---|
| **Recensăminte 1930–2021** | serii pe UAT armonizate |
| **Hărți istorice georeferențiate (Planurile Directoare de Tragere, Szathmári — geo-spatial.org)** | prezența așezărilor pe hărți istorice, vechimea intravilanului |
| **GHSL built-up pe epoci** | expansiunea construită 1975→2030 |

## 5. Probleme cunoscute de modelare

1. **Confidențialitate statistică (SDC).** INS/Eurostat perturbă sau maschează celulele cu populație
   foarte mică. Reguli: (a) flag `sdc_flag` per celulă, propagat în toate agregatele; (b) UI-ul nu
   afișează niciodată o valoare pentru o selecție cu < N celule sau < M persoane (praguri din
   metadatele sursei) — afișează „sub pragul de confidențialitate”; (c) totalurile naționale se
   reconciliază cu cifrele oficiale publicate și diferența se documentează.
2. **Crosswalk istoric al UAT-urilor.** Limitele și componența UAT s-au schimbat între recensăminte.
   Construim un tabel de corespondență (SIRUTA istoric → SIRUTA 2021, cu ponderi la divizări),
   documentat ca metodologie separată; seriile istorice pe grilă se obțin doar via GHS-POP
   (dezagregare model), marcate explicit ca estimări.
3. **MAUP și dezagregare.** Variabilele disponibile doar pe UAT/județ (salarii, șomaj) sunt atașate
   celulelor prin apartenență — registrul le marchează `resolution: uat|judet`, iar UI-ul afișează
   nivelul real de rezoluție (ex. hașură sau notă „valoare la nivel de județ”).
4. **Licențe.** Fiecare variabilă moștenește licența sursei din `sources.yaml`; pagina „Date și licențe”
   se generează automat. Derivatele din OSM (ODbL) sunt ținute în fișiere Parquet separate pentru a
   putea aplica share-alike fără a contamina restul.
5. **Versionare.** Publicare pe prefixe imutabile (`/v2026.10/…`) + `manifest.json` (hash-uri, dimensiuni,
   versiune registru). Aplicația fixează versiunea de date la build, cu posibilitate de override
   (`?data=v2026.10`) pentru reproducerea analizelor vechi.
