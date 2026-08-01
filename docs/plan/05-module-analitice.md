# 05 — Modulele analitice

## 1. Preseturile de întrebări (F2)

Fiecare întrebare din brief este un AST parametrizat (definițiile implicite în 01 §3), cu un card
în modul ghidat: cifră mare + hartă + o defalcare implicită + definiția folosită + slider de parametru.

| Întrebare | Măsură | Filtru implicit | Defalcare implicită |
|---|---|---|---|
| Câți români locuiesc la mare? | `sum(pop_total)` | `dist.sea < 5 km` | pe UAT litoral |
| … lângă pădure? | idem | `dist.forest < 1 km` | pe județe |
| … la câmpie / deal / munte? | idem | `relief.unitate in […]` | pe unități de relief |
| … lângă apă? | idem | `dist.river < 500 m OR dist.lake < 1 km` | râu vs. lac |
| … la oraș / la sat? | idem | statut UAT (comutabil pe DEGURBA) | ambele definiții, față în față |
| … în zona de frontieră? | idem | `dist.border < 30 km` | pe frontiere (UA/MD/BG/RS/HU) |

Preseturile sunt date, nu cod (`presets.ts` e generat din YAML) — adăugarea unei întrebări noi
(ex. „câți români locuiesc în zone cu risc seismic ridicat?”) nu cere modificări în aplicație.

## 2. Profilul „cetățeanului virtual” — fișa celulei de 1 km (F3, F7)

Click pe orice celulă → **fișa locului**, construită din toate variabilele registrului:

1. **Antet:** localitate/UAT/județ, populație, flag SDC dacă e cazul.
2. **Percentile:** fiecare variabilă ca punct pe axa 0–100 față de distribuția națională (și,
   comutabil, față de județ) — graficul `PercentileDots`, grupat pe categoriile registrului,
   cu căutare; suportă lizibil sute de variabile. Percentilele vin din `stats.parquet` (precalculate).
3. **Serii temporale:** climă lunară/normale succesive, NDVI, proiecții pe scenarii (benzi),
   populația UAT la recensămintele 1930–2021 — grafice uPlot.
4. **„Locuri asemănătoare”:** din `embedding.parquet` (PCA 32-dim precalculat pe vectorul complet
   standardizat): similaritate cosinus în JS pe Float32Array (~240k × 32 = 30 MB, < 100 ms) →
   top-N celule similare evidențiate pe hartă. Răspunde la „unde se mai trăiește ca aici?”.
5. **Tipologii:** clase de clustering precalculate în pipeline (k-means/HDBSCAN pe embedding,
   etichetate manual: „rural montan îmbătrânit”, „periurban în expansiune”…) — o variabilă
   categorială ca oricare alta, deci filtrabilă și cartografiabilă.

Aceeași fișă există la nivel de **UAT** și de **selecție arbitrară** (poligon desenat / rază), cu
agregatele ponderate cu populația și piramida vârstelor. Două-trei selecții se pot pune în
**comparație side-by-side** (tabel + grafice suprapuse).

## 3. Modulul de reformă administrativă (F6)

Scop: fundamentarea obiectivă a scenariilor de reorganizare a UAT-urilor.

**Constructor de scenarii:**
- selecție pe hartă a UAT-urilor de comasat (click / lasso / „sugerează vecinii”);
- pentru unitatea rezultată se calculează instant: populație (2021 + tendință 2011→2021 + proiecție
  simplă), suprafață, densitate, formă/contiguitate, timpi de acces ponderați cu populația către
  noul centru propus (selectabil), servicii existente (școli, spitale, gări), venituri proprii
  însumate / locuitor, indicatori de îmbătrânire și dependență;
- **praguri configurabile** (ex. populație minimă 5.000, timp maxim de acces 30 min) cu semafor
  verde/galben/roșu per criteriu — pragurile nu sunt hard-codate, fiind ele însele obiect de
  dezbatere publică;
- scenariile se salvează ca JSON (listă de comasări + parametri), se partajează prin permalink și
  se **compară între ele** (tabel de scenarii × indicatori);
- export: fișă de scenariu imprimabilă (PDF prin print CSS) cu hărți, cifre, metodologie.

**Extensii (cercetare, post-v1):** sugestii automate de comasare — partiționare de graf pe graful
de vecinătate al UAT-urilor cu constrângeri de contiguitate, populație minimă și timp de acces;
rulată offline, livrată ca scenarii-propuneri comentabile.

## 4. Modulul de vulnerabilitate (F5)

Trei straturi de analiză, combinabile:

1. **Expunere:** populația din celule cu hazard — inundații (scenarii 10%/1%/0,1%, fracțiune
   inundabilă), alunecări (clase de susceptibilitate), seism (ag/intensitate) — cu defalcări
   pe județ/UAT/vârstă.
2. **Vulnerabilitate socială:** index compus per celulă din: % vârstnici, % copii, marginalizare,
   timp la UPU/spital, calitatea locuirii (racorduri, vechime) — **ponderi ajustabile în UI**, cu
   metodologia afișată (nu există index „obiectiv”; transparența ponderilor e obligatorie).
3. **Risc prioritizat:** expunere × vulnerabilitate → ierarhizări de UAT-uri/celule pentru
   intervenție, cu export CSV și fișe imprimabile pentru protecția civilă.

Întrebări-tip: „câți vârstnici singuri locuiesc în zone inundabile la scenariul 1%, la peste
30 de minute de un spital?” — este doar un AST cu 3 constrângeri, deci vine „gratis” din motor;
modulul adaugă preseturile, indexul compus și rapoartele.

## 5. Dimensiunea temporală (F4, F7)

- **Climă:** normale succesive (1961–90 → 1991–2020) + proiecții 2041–70 / 2071–2100 pe scenarii
  SSP — time-slider pe hartă + grafice cu benzi de incertitudine; „delta” ca strat propriu
  (ex. schimbarea numărului de zile tropicale);
- **Populație pe grilă:** GEOSTAT 2006/2011/2018/2021 (+ GHS-POP pe epoci, marcat ca estimare) —
  animația „unde a crescut / a scăzut populația”;
- **Recensăminte 1930–2021** pe UAT armonizat — serii lungi în fișe;
- **Satelitar:** NDVI lunar (fenologie), lumini nocturne anuale, expansiunea construită GHSL;
- întrebări încrucișate: „câți români locuiesc azi în locuri care în 2071–2100 (SSP3-7.0) vor avea
  clima Greciei de azi?” — analog climatic implementat ca similaritate pe variabilele climatice.

## 6. Export, partajare, raportare

- **Permalink** cu tot (stare + versiune date) — deja în arhitectură;
- **Export date:** CSV (agregate/defalcări), GeoJSON (celule selectate / limite), PNG (hartă +
  grafice cu legendă și atribuiri);
- **Fișe imprimabile:** celulă / UAT / scenariu / raport de vulnerabilitate — pagini print-CSS
  cu antet, dată, versiune date, surse;
- **Embed:** hărți-widget (iframe cu stare fixată) pentru presă;
- **Story mode (F8, opțional):** scrollytelling introductiv cu 5–6 răspunsuri-vedetă, ca poartă
  de intrare pentru public larg.
