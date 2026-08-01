# 04 — Motorul de interogare

## 1. Principiu: un AST, un motor canonic

Orice întrebare — preset ghidat sau construcție expertă — este un **AST de constrângeri**.
AST-ul se compilează la SQL și se execută în DuckDB-WASM, care este **singura sursă a cifrelor**.
Harta pictează bitset-ul de celule întors de aceeași interogare — imposibil ca harta și KPI-ul
să difere. Cubul Zarr servește vizualizarea variabilelor, profilele și seriile temporale,
nu cifrele oficiale.

## 2. Modelul de constrângeri

```ts
type QueryAST = {
  filter: Node;                       // arborele de constrângeri
  measure: Measure;                   // ce numărăm
  groupBy?: VariableId[];             // defalcări opționale
};

type Node =
  | { op: "and" | "or"; children: Node[] }
  | { op: "not"; child: Node }
  | Constraint;

type Constraint =
  | { var: VariableId; op: "between"; value: [number, number] }
  | { var: VariableId; op: "<" | "<=" | ">" | ">=" | "==" ; value: number }
  | { var: VariableId; op: "in"; value: (number | string)[] }   // categoriale
  | { var: VariableId; op: "is"; value: boolean }               // flag-uri
  | { op: "spatial"; kind: "uat" | "judet" | "polygon" | "radius"; value: … };

type Measure = {
  var: VariableId;                    // ex. pop_total, pop_f, gospodarii
  agg: "sum" | "count_cells" | "pop_weighted_mean" | "mean" | "quantile";
  of?: VariableId;                    // pentru pop_weighted_mean(of: altitudine) etc.
};
```

Exemplul din brief — *câte femei locuiesc la 200–500 m altitudine, cu precipitații < 600 mm/an
și temperatura medie anuală ≈ 12 °C*:

```json
{
  "filter": { "op": "and", "children": [
    { "var": "relief.alt",                  "op": "between", "value": [200, 500] },
    { "var": "clim.prec.annual.1991_2020",  "op": "<",       "value": 600 },
    { "var": "clim.tmean.annual.1991_2020", "op": "between", "value": [11.5, 12.5] }
  ]},
  "measure": { "var": "pop_f", "agg": "sum" }
}
```

## 3. Compilarea la SQL

Compilatorul folosește registrul pentru a ști în ce fișier/coloană stă fiecare variabilă și
generează join-uri doar pentru tabelele efectiv atinse:

```sql
SELECT sum(c.pop_f)                        AS valoare,
       sum(c.pop_total)                    AS pop_totala,
       count(*)                            AS n_celule,
       max(c.sdc_flag)                     AS sdc,
       list(c.cell_id)                     AS celule      -- doar când e nevoie de mască
FROM core c
JOIN env     e  USING (cell_id)
JOIN climate k  USING (cell_id)
WHERE e.alt BETWEEN 200 AND 500
  AND k.prec_annual_1991_2020 < 600
  AND k.tmean_annual_1991_2020 BETWEEN 11.5 AND 12.5;
```

Note de implementare:

- **două interogări, nu una**: (1) agregatele + defalcările (ieftină); (2) `SELECT cell_id WHERE …`
  pentru mască — întoarsă ca Arrow `uint32`, transformată în bitset (~48 KB pentru toată țara)
  și transferată către raster.worker;
- constrângerile spațiale: `uat/judet` → predicat pe coloanele de apartenență (deja per celulă);
  `polygon/radius` → extensia `spatial` a DuckDB sau, fallback, point-in-polygon în JS pe
  centroide (typed arrays, ~240k puncte, sub 50 ms);
- interogările sunt anulabile (o tastare nouă în builder anulează execuția precedentă) și
  cache-uite pe cheia `hash(AST + dataVersion)`;
- `EXPLAIN`-ul și SQL-ul generat sunt vizibile în modul expert („arată SQL”) — transparență și
  debugging.

## 4. Agregări și statistici corecte

- **Numărători:** `sum(measure)` pe celulele filtrate; întotdeauna raportăm și `% din total național`
  și numărul de celule.
- **Medii ponderate cu populația:** „altitudinea la care trăiește românul median” ≠ media altitudinii
  celulelor. Pentru `pop_weighted_mean(of: X)`: `sum(X * pop) / sum(pop)`.
- **Cuantile ponderate:** DuckDB nu are cuantile ponderate native; le calculăm pe histograma
  cumulativă: `GROUP BY bin(X)` cu ponderi `pop`, apoi interpolare în JS — exact suficient pentru
  bin-uri fine (256), și oricum afișăm histograma.
- **Defalcări (`groupBy`):** pe orice variabilă categorială → tabel + grafic (ex. defalcarea pe
  județe a populației „la mai puțin de 5 km de pădure”).
- **Comparație de definiții:** modul ghidat poate rula două AST-uri în paralel (ex. „la oraș” după
  statut administrativ vs. DEGURBA) și afișa ambele cifre — diferența este ea însăși informativă.

## 5. Confidențialitate și incertitudine în rezultate

1. Dacă selecția are `n_celule < N_min` sau `valoare < M_min` (praguri din manifest, moștenite de la
   INS), UI-ul afișează „sub pragul de confidențialitate”, nu cifra.
2. Dacă `sdc > 0` (selecția atinge celule perturbate), cifra primește simbolul „≈” și un popover:
   „include celule cu valori protejate statistic; cifra exactă poate diferi cu ±…”.
3. Variabilele cu `resolution: uat|judet` folosite în filtre adaugă automat nota: „criteriul X are
   rezoluție de județ — toate celulele unui județ îl satisfac sau nu împreună” (anti-MAUP).
4. Fiecare rezultat poartă versiunea datelor; permalink-ul o fixează (reproductibilitate).

## 6. Performanță

- Coloanele parquet atinse de o interogare tipică: 3–6 → citire de ordinul MB, apoi cache OPFS;
- după prima interogare, totul e local: țintă < 500 ms per interogare, inclusiv masca;
- preseturile au agregatele precalculate în `stats.parquet` pentru afișare instantanee la
  parametrii impliciți (înainte ca DuckDB să fie gata), înlocuite apoi de calculul live;
- teste de consistență: cifrele live = cifrele golden din pipeline (02 §4.4).
