/** Dashboardul de analiză — generat integral din registru: orice variabilă (actuală sau
 *  viitoare) devine analizabilă automat, cu explicații în limbaj natural, histograme
 *  ponderate cu populația, comparații România↔județe și clasament pe județe.
 *  Toate cifrele vin din DuckDB, cu aceeași semantică precum restul aplicației. */

import { useEffect, useMemo, useState } from "react";
import { runQuery } from "../lib/duck";
import { fmtInt, fmtNum, fmtPct } from "../lib/format";
import type { Registry } from "../lib/registry";
import { varById } from "../lib/registry";
import type { QueryState } from "../query/model";
import {
  categoryDistSql,
  countyRankingSql,
  histSpec,
  weightedHistSql,
  weightedMeanSql,
} from "../analysis/sql";
import { displayBins, distFromRows, weightedQuantile, type WeightedDist } from "../analysis/stats";
import { categorySentences, comparisonSentence, numericSentences } from "../analysis/text";
import { HistChart } from "./HistChart";

interface Props {
  dataUrl: string;
  registry: Registry;
  query: QueryState; // filtrul curent din modul întrebări (opțional aplicabil)
  onClose(): void;
}

type Area = string | null; // null = România; altfel county_mn

interface NumericData {
  dist: WeightedDist;
  p10: number | null;
  p50: number | null;
  p90: number | null;
}
interface CatRow {
  cat: string;
  pop: number;
  cells: number;
}
interface RankRow {
  mn: string;
  wmean: number;
  pop: number;
}

const MAX_CAT = 40; // categoriale cu prea multe valori (UAT, spitale) nu au sens aici

export function Dashboard({ dataUrl, registry, query, onClose }: Props) {
  const vars = useMemo(
    () =>
      registry.variables.filter(
        (v) =>
          (v.dtype === "int" || v.dtype === "float" || v.dtype === "cat") &&
          (v.dtype !== "cat" || (v.categories?.length ?? 99) <= MAX_CAT)
      ),
    [registry]
  );

  const [varId, setVarId] = useState("alt_mean");
  const [measure, setMeasure] = useState("pop_total");
  const [areaA, setAreaA] = useState<Area>(null);
  const [areaB, setAreaB] = useState<Area | "off">("off");
  const [useFilter, setUseFilter] = useState(false);

  const v = varById(registry, varId);
  const dec = v.decimals ?? (v.dtype === "int" ? 0 : 1);
  const measureLabel = registry.measures.find((m) => m.id === measure)?.label ?? "persoane";
  const areaLabel = (a: Area) => (a ? registry.countyLabels[a] ?? a : "România");
  const constraints = useFilter ? query.constraints : [];

  const [numA, setNumA] = useState<NumericData | null>(null);
  const [numB, setNumB] = useState<NumericData | null>(null);
  const [catA, setCatA] = useState<CatRow[] | null>(null);
  const [catB, setCatB] = useState<CatRow[] | null>(null);
  const [ranking, setRanking] = useState<RankRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  const spec = useMemo(() => histSpec(registry, varId), [registry, varId]);
  const isNumeric = v.dtype !== "cat";

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setNumA(null);
    setNumB(null);
    setCatA(null);
    setCatB(null);
    setRanking(null);

    async function loadNumeric(area: Area): Promise<NumericData> {
      const [hist, mean] = await Promise.all([
        runQuery(dataUrl, weightedHistSql(registry, varId, measure, constraints, area)),
        runQuery(dataUrl, weightedMeanSql(registry, varId, measure, constraints, area)),
      ]);
      const rows = [];
      for (let i = 0; i < hist.numRows; i++) {
        const r = hist.get(i)!;
        rows.push({ bin: Number(r["bin"]), pop: Number(r["pop"]) });
      }
      const m = mean.get(0);
      const dist = distFromRows(rows, m ? Number(m["wmean"]) : null);
      return {
        dist,
        p10: weightedQuantile(dist, spec, 0.1),
        p50: weightedQuantile(dist, spec, 0.5),
        p90: weightedQuantile(dist, spec, 0.9),
      };
    }

    async function loadCat(area: Area): Promise<CatRow[]> {
      const t = await runQuery(dataUrl, categoryDistSql(registry, varId, measure, constraints, area));
      const rows: CatRow[] = [];
      for (let i = 0; i < t.numRows; i++) {
        const r = t.get(i)!;
        rows.push({ cat: String(r["cat"]), pop: Number(r["pop"]), cells: Number(r["cells"]) });
      }
      return rows;
    }

    (async () => {
      try {
        if (isNumeric) {
          const [a, b, rank] = await Promise.all([
            loadNumeric(areaA),
            areaB !== "off" ? loadNumeric(areaB) : Promise.resolve(null),
            runQuery(dataUrl, countyRankingSql(registry, varId, measure, constraints)),
          ]);
          if (!alive) return;
          setNumA(a);
          setNumB(b);
          const rk: RankRow[] = [];
          for (let i = 0; i < rank.numRows; i++) {
            const r = rank.get(i)!;
            rk.push({ mn: String(r["mn"]), wmean: Number(r["wmean"]), pop: Number(r["pop"]) });
          }
          setRanking(rk);
        } else {
          const [a, b] = await Promise.all([
            loadCat(areaA),
            areaB !== "off" ? loadCat(areaB) : Promise.resolve(null),
          ]);
          if (!alive) return;
          setCatA(a);
          setCatB(b);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (alive) setBusy(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUrl, registry, varId, measure, areaA, areaB, useFilter]);

  const counties = useMemo(
    () =>
      Object.entries(registry.countyLabels)
        .map(([mn, name]) => ({ mn, name }))
        .sort((a, b) => a.name.localeCompare(b.name, "ro")),
    [registry]
  );

  // propozițiile generate
  const sentences: string[] = [];
  if (isNumeric && numA) {
    sentences.push(
      ...numericSentences(v, measureLabel, areaLabel(areaA), { ...numA, wmean: numA.dist.wmean, total: numA.dist.total }, dec)
    );
    if (numB && areaB !== "off") {
      const s = comparisonSentence(v, areaLabel(areaA), areaLabel(areaB), numA.p50, numB.p50, dec);
      if (s) sentences.push(s);
    }
  }
  if (!isNumeric && catA) {
    sentences.push(
      ...categorySentences(v, measureLabel, areaLabel(areaA), catA, catA.reduce((s, c) => s + c.pop, 0))
    );
  }

  const histView = useMemo(() => {
    if (!numA) return null;
    const a = displayBins(numA.dist, spec);
    const b = numB ? displayBins(numB.dist, spec) : null;
    // seriile pe procente când comparăm arii de mărimi diferite
    const norm = (vals: number[], total: number) =>
      areaB !== "off" && total > 0 ? vals.map((x) => (100 * x) / total) : vals;
    return {
      centers: a.centers,
      A: norm(a.values, numA.dist.total),
      B: b && numB ? norm(b.values, numB.dist.total) : null,
      pct: areaB !== "off",
    };
  }, [numA, numB, spec, areaB]);

  return (
    <div className="dashboard">
      <div className="dash-head">
        <h2>Analiză: unde trăiesc {measureLabel}?</h2>
        <button className="remove" onClick={onClose} title="Închide analiza">×</button>
      </div>

      <div className="dash-controls">
        <label>
          <span>Variabila</span>
          <select value={varId} onChange={(e) => setVarId(e.target.value)}>
            {Object.entries(registry.groups).map(([gid, glabel]) => (
              <optgroup key={gid} label={glabel}>
                {vars.filter((x) => x.group === gid).map((x) => (
                  <option key={x.id} value={x.id}>{x.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          <span>Măsura</span>
          <select value={measure} onChange={(e) => setMeasure(e.target.value)}>
            {registry.measures.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Aria A</span>
          <select value={areaA ?? ""} onChange={(e) => setAreaA(e.target.value || null)}>
            <option value="">România</option>
            {counties.map((c) => (
              <option key={c.mn} value={c.mn}>{c.name}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Compară cu</span>
          <select
            value={areaB === "off" ? "off" : areaB ?? ""}
            onChange={(e) => setAreaB(e.target.value === "off" ? "off" : e.target.value || null)}
          >
            <option value="off">— fără comparație —</option>
            <option value="">România</option>
            {counties.map((c) => (
              <option key={c.mn} value={c.mn}>{c.name}</option>
            ))}
          </select>
        </label>
        {query.constraints.length > 0 && (
          <label className="dash-filter-toggle">
            <input type="checkbox" checked={useFilter} onChange={(e) => setUseFilter(e.target.checked)} />
            <span>
              aplică filtrul curent (
              {query.constraints.length === 1 ? "1 criteriu" : `${query.constraints.length} criterii`})
            </span>
          </label>
        )}
      </div>

      {v.note && <p className="dash-note">{v.note}</p>}
      {busy && <p className="dash-note">se calculează…</p>}

      {sentences.length > 0 && (
        <div className="dash-sentences">
          {sentences.map((s, i) => (
            <p key={i}>{s}</p>
          ))}
        </div>
      )}

      <div className="dash-grid">
        <section className="dash-card">
          <h3>
            Distribuția: {v.label}
            {histView?.pct ? " (procente din fiecare arie)" : ""}
          </h3>
          {isNumeric && histView && (
            <HistChart
              centers={histView.centers}
              seriesA={histView.A}
              seriesB={histView.B}
              labelA={areaLabel(areaA)}
              labelB={areaB !== "off" ? areaLabel(areaB) : undefined}
              unit={v.unit}
              measureLabel={measureLabel}
              pct={histView.pct}
            />
          )}
          {isNumeric && numA && (
            <div className="dash-stats">
              <div><span>p10</span><strong>{fmtNum(numA.p10, dec)}</strong></div>
              <div><span>mediană</span><strong>{fmtNum(numA.p50, dec)}</strong></div>
              <div><span>p90</span><strong>{fmtNum(numA.p90, dec)}</strong></div>
              <div><span>medie pond.</span><strong>{fmtNum(numA.dist.wmean, dec)}</strong></div>
              <div><span>{measureLabel}</span><strong>{fmtInt(numA.dist.total)}</strong></div>
            </div>
          )}
          {!isNumeric && catA && (
            <CategoryBars
              a={catA}
              b={areaB !== "off" ? catB : null}
              labelA={areaLabel(areaA)}
              labelB={areaB !== "off" ? areaLabel(areaB) : undefined}
            />
          )}
        </section>

        {isNumeric && ranking && ranking.length > 1 && (
          <section className="dash-card">
            <h3>Județe, după media ponderată{v.unit ? ` (${v.unit})` : ""}</h3>
            <RankingBars rows={ranking} labels={registry.countyLabels} dec={dec} highlight={[areaA, areaB === "off" ? null : areaB]} />
          </section>
        )}
      </div>

      <p className="dash-foot">
        Toate valorile sunt ponderate cu „{measureLabel}” — arată unde trăiesc oamenii, nu cum arată
        teritoriul. Sursa fiecărei variabile: fișa ei din registru · date {registry.version}.
      </p>
    </div>
  );
}

function CategoryBars({
  a,
  b,
  labelA,
  labelB,
}: {
  a: CatRow[];
  b?: CatRow[] | null;
  labelA: string;
  labelB?: string;
}) {
  const totalA = a.reduce((s, c) => s + c.pop, 0);
  const totalB = b ? b.reduce((s, c) => s + c.pop, 0) : 0;
  const bMap = new Map((b ?? []).map((c) => [c.cat, c.pop]));
  return (
    <div className="cat-bars">
      {b && (
        <div className="cat-legend">
          <span><i className="sw a" /> {labelA}</span>
          <span><i className="sw b" /> {labelB}</span>
        </div>
      )}
      {a.map((c) => {
        const pa = totalA > 0 ? c.pop / totalA : 0;
        const pb = b && totalB > 0 ? (bMap.get(c.cat) ?? 0) / totalB : null;
        return (
          <div
            key={c.cat}
            className="cat-row"
            title={`${labelA}: ${fmtInt(c.pop)} (${fmtPct(pa)})${pb != null ? ` · ${labelB}: ${fmtInt(bMap.get(c.cat) ?? 0)} (${fmtPct(pb)})` : ""}`}
          >
            <div className="cat-name">{c.cat}</div>
            <div className="cat-track">
              <div className="cat-fill a" style={{ width: `${(pa * 100).toFixed(2)}%` }} />
              {pb != null && <div className="cat-fill b" style={{ width: `${(pb * 100).toFixed(2)}%` }} />}
            </div>
            <div className="cat-pct">
              {fmtPct(pa)}
              {pb != null ? ` / ${fmtPct(pb)}` : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RankingBars({
  rows,
  labels,
  dec,
  highlight,
}: {
  rows: RankRow[];
  labels: Record<string, string>;
  dec: number;
  highlight: (string | null)[];
}) {
  const max = Math.max(...rows.map((r) => Math.abs(r.wmean)));
  return (
    <div className="rank-list">
      {rows.map((r, i) => (
        <div
          key={r.mn}
          className={"rank-row" + (highlight.includes(r.mn) ? " hl" : "")}
          title={`${labels[r.mn] ?? r.mn}: medie ${fmtNum(r.wmean, dec)} · ${fmtInt(r.pop)} persoane`}
        >
          <span className="rank-pos">{i + 1}</span>
          <span className="rank-name">{labels[r.mn] ?? r.mn}</span>
          <span className="rank-track">
            <span className="rank-fill" style={{ width: `${max > 0 ? (100 * Math.abs(r.wmean)) / max : 0}%` }} />
          </span>
          <span className="rank-val">{fmtNum(r.wmean, dec)}</span>
        </div>
      ))}
    </div>
  );
}
