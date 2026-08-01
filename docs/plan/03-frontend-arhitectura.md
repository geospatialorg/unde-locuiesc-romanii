# 03 — Arhitectura frontend

Aplicație statică Vite + TypeScript (strict) + React 19, cu două web workere pentru munca grea.
Niciun apel către un backend propriu — doar fișiere statice și range requests către object storage.

## 1. Structura modulelor

```
app/src/
├── main.tsx  app/            # shell, layout, routing, stare globală (Zustand), stare-în-URL
├── data/
│   ├── registry.ts           # încarcă registry.json → tipuri VariableDef, grupuri, statistici
│   ├── manifest.ts           # versiunea de date, URL-uri produse
│   └── grid.ts               # matematica grilei: (lon,lat) ↔ (E,N) ↔ (col,row) ↔ cell_id
├── query/
│   ├── ast.ts                # modelul de constrângeri (vezi 04)
│   ├── compile-sql.ts        # AST → SQL DuckDB
│   ├── presets.ts            # cele 6+ întrebări ca AST-uri parametrizate
│   └── client.ts             # fațada către query-worker (Comlink)
├── workers/
│   ├── duckdb.worker.ts      # DuckDB-WASM: init leneș, register httpfs, execuție, Arrow → transferabile
│   └── raster.worker.ts      # Zarrita: chunks, decodare, warp LAEA→viewport, ImageBitmap
├── map/
│   ├── map.ts                # init MapLibre, protocol pmtiles + cog, stiluri
│   ├── layers/               # bazmap, hillshade, limite, mask-layer, choropleth-layer, hazard
│   └── interactions.ts       # hover/click → cell_id (formulă, fără hit-testing pe tile-uri)
├── charts/                   # învelișuri uPlot: Histogram, TimeSeries, AgePyramid, PercentileDots, Scatter
├── ui/                       # QueryBuilder, GuidedQuestions, KPIBar, ProfilePanel, ComparePanel,
│                             # ScenarioPanel (reformă), HazardPanel, Legend, MethodologyPopover, Glossary
└── lib/                      # proj (3035↔4326/3857), bitset, culori (scheme colorblind-safe),
                              # format ro-RO, url-state (lz-string), opfs-cache
```

Stare globală (Zustand), integral serializabilă în URL:

```ts
interface AppState {
  dataVersion: string;              // ex. "v2026.10"
  view: { center: [number, number]; zoom: number };
  query: QueryAST | null;           // constrângerile active
  activeLayer: VariableId | null;   // variabila colorată pe hartă
  timeIndex?: number;               // pentru straturi temporale
  selection: Selection | null;      // celulă / UAT / poligon desenat
  compare: Selection[];             // zone în comparație
  ui: { mode: "ghidat" | "expert"; panels: … };
}
```

`url-state` codifică `{dataVersion, view, query, activeLayer, selection}` cu lz-string →
**orice analiză este un permalink** (și baza pentru export/rapoarte).

## 2. Workerele

**duckdb.worker** — încărcat leneș la prima interogare (bundle-ul WASM ~5–10 MB gz, cu progres în UI):
1. instanțiere DuckDB-WASM, `INSTALL httpfs` (+ `spatial` doar la nevoie);
2. `CREATE VIEW core AS SELECT * FROM read_parquet('https://…/grid/core.parquet')` pentru fiecare tabelă
   (DuckDB citește doar footer-ul la creare — ieftin);
3. API Comlink: `run(sql) → {arrowIPC, elapsed}`; rezultatele mari se transferă ca `ArrayBuffer`;
4. cache: fișierele parquet accesate sunt copiate în **OPFS** la prima citire → vizitele următoare
   nu mai ating rețeaua (invalidare prin versiunea de date din manifest).

**raster.worker** — pornit imediat (Zarrita e mic):
1. citește metadatele consolidate ale cubului la pornire;
2. `getLayer(varId, timeIdx?) → Float32Array` (mozaicare chunks, cache LRU în worker + OPFS);
3. `renderMask(bitset, viewportBbox, size) → ImageBitmap` și
   `renderChoropleth(varId, colorScale, …) → ImageBitmap` (vezi §4);
4. `cellProfileSeries(cellId, varIds) → serii` pentru graficele temporale ale profilului.

## 3. Harta — straturi

| Strat | Sursă | Note |
|---|---|---|
| Bazmap vector | `basemap.pmtiles` | stil propriu, diacritice, două teme (deschis/închis) |
| Hillshade | `hillshade.pmtiles` | sub straturile tematice, opacitate mică |
| **Mască rezultat** | ImageSource actualizat din raster.worker | celulele care satisfac interogarea |
| **Choropleth variabilă** | idem | orice variabilă din cub, cu legendă din registru |
| Limite (UAT/județe/relief/cartiere) | `boundaries.pmtiles` | hover cu `feature-state`, click → fișă |
| Straturi de context | COG prin `maplibre-cog-protocol` | hazard, WorldCover etc., activate la cerere |

## 4. Randarea grilei — decizia centrală

Grila trăiește în EPSG:3035; harta în Web Mercator. Trei etape:

**4.1 Interacțiune (toate fazele):** hover/click nu folosesc tile-uri: `(lon,lat)` → proiecție în
3035 → `floor` la 1000 m → `cell_id`. Exact, instant, zero date suplimentare.

**4.2 MVP (F2): warp pe canvas în worker.** Pentru bbox-ul curent al viewportului (în 4326),
raster.worker generează o imagine `w×h` (~1–2 MP): pentru fiecare pixel de ieșire, proiectează
invers centrul pixelului în 3035, eșantionează nearest-neighbor valoarea/bitul celulei, scrie RGBA.
Rezultatul e corect prin construcție (nu întindem un dreptunghi LAEA peste Mercator — calculăm
fiecare pixel). Cu bucle pe `Float64Array` și formulele proj inline, ~1,5 MP se randează în
zeci de ms; re-randare pe `moveend` + debounce. Suficient până la F7.

**4.3 Optimizare (F7): recolorare în shader.** Custom layer WebGL: textura A = `cellid.pmtiles`
(RGB codifică `cell_id`, pre-reproiectate în 3857 — vezi 02 §3.3), textura B = LUT 1D construită
din bitset/paletă. Shaderul face lookup → recolorare instantanee la orice schimbare de interogare,
fără re-warp, cu zoom continuu. Aceeași mecanică servește și choropleth-urile (LUT = rampă de culori).

**4.4 Măști vizuale progresive:** la schimbarea interogării, masca se afișează imediat din bitset-ul
DuckDB; dacă DuckDB încă se încarcă (prima vizită), preseturile simple pot picta o mască aproximativă
din cub (Zarr) cu eticheta „calcul preliminar…”, înlocuită de cifrele exacte când motorul e gata.

## 5. Graficele (uPlot)

Învelișuri subțiri, toate cu temă comună și export PNG:

- **Histogram** — distribuția populației după o variabilă (bin-uri din DuckDB, nu în JS);
  folosită și ca „context de filtru”: sliderul intervalului este suprapus pe histogramă;
- **TimeSeries** — serii lunare/anuale (climă, NDVI, recensăminte); sincronizate cu time-sliderul
  hărții (cursor comun); benzi min–max pentru proiecții pe scenarii;
- **AgePyramid** — piramida vârstelor pentru selecție vs. național (bare divergente);
- **PercentileDots** — profilul celulei/zonei: fiecare variabilă ca punct pe axa percentilelor
  0–100 față de țară/județ (lizibil pentru sute de variabile, grupat pe categorii, cu căutare);
- **Scatter** — comparații între UAT-uri (ex. timp de acces vs. % vârstnici), cu brushing → hartă.

Regulă: orice grafic afișează sursa + anul datelor (din registru) și are buton „cum s-a calculat?”.

## 6. UI/UX

**Layout desktop:** hartă centrală; stânga — panoul de interogare (mod ghidat: carduri de întrebări;
mod expert: constructor de constrângeri); dreapta — panou de rezultate (KPI, grafice, profil,
comparații) redimensionabil; jos — time-slider când stratul activ e temporal.
**Mobil:** hartă + bottom-sheet cu aceleași panouri.

**Modul ghidat:** carduri cu întrebările-preset („Câți români locuiesc la mare?” …), fiecare cu
parametrii expuși ca slidere simple și definiția afișată sub rezultat (vezi 01 §3). Un buton
„deschide în modul expert” arată AST-ul echivalent — rampă de învățare.

**Modul expert — QueryBuilder:** listă de constrângeri (variabilă → operator → valoare), cu:
căutare în registru (fuzzy, pe etichete RO), slidere pe histograma variabilei, grupuri AND/OR
imbricabile (UI cu indentare, nu paranteze), alegerea măsurii (persoane / femei / gospodării / …),
și „defalcă pe” (județ, DEGURBA, grupă de vârstă) → tabel + grafic.

**Alte elemente:** căutare de localitate (index client-side SIRUTA + nume OSM), glosar cu popover-e
pe termeni, ecuson permanent cu versiunea datelor, buton global „metodologie”, temă deschis/închis.

## 7. Accesibilitate, i18n, formatare

- WCAG 2.2 AA: navigare completă din tastatură (inclusiv constructorul de interogări),
  `aria-live` pentru rezultate, contrast verificat pe ambele teme;
- palete colorblind-safe (viridis/cividis pentru continue; scheme categoriale testate);
  hărțile nu comunică niciodată doar prin culoare (legendă + valori la hover);
- numere formatate `ro-RO` (spațiu pentru mii, virgulă zecimală); i18n pregătit (chei + registru
  bilingv), livrat inițial doar RO;
- alternativă textuală: fiecare rezultat are o propoziție generată („≈1,2 milioane de persoane —
  6,3% din populația României — locuiesc la mai puțin de 5 km de mare”), utilă și pentru share/SEO.

## 8. Performanță și testare

Bugete (verificate în CI cu Lighthouse + teste de mărime):

| Metrică | Buget |
|---|---|
| JS inițial (fără DuckDB) | < 400 KB gz (MapLibre ~250 KB + app) |
| Prima hartă vizibilă | < 2,5 s pe 4G |
| DuckDB-WASM | leneș, cu progres; interogare după cache < 500 ms |
| Memorie totală | < 800 MB în scenariile e2e |

Testare:
- **vitest**: matematica grilei, compilatorul AST→SQL (teste golden), url-state, bitset;
- **Playwright e2e** pe mini-fixture-ul 10×10 (vezi 02 §4.5): preseturi, profil, comparații,
  permalink round-trip; și un smoke-test contra datelor reale (nightly);
- **test de consistență**: cifrele preseturilor = valorile golden din pipeline;
- vizual: screenshot-diff pe hartă și grafice pentru temele deschis/închis.

Securitate/confidențialitate: aplicație statică, fără cookie-uri; CSP strict (doar domeniul de date);
analytics privacy-friendly (Plausible) opțional; nicio dată personală — totul e agregat.
