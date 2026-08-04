import { useEffect, useMemo, useRef, useState } from "react";
import { fmtInt, fmtNum, fmtSharePct } from "../lib/format";
import type { Registry, VariableDef } from "../lib/registry";
import { varById } from "../lib/registry";
import type { Constraint, QueryResult, QueryState } from "../query/model";
import { MORE_PRESETS, PRESETS, type PresetThreshold } from "../query/presets";
import { WarningsPanel, type WarnSelection } from "./WarningsPanel";
import { hasAnyWarnings, type WarningsMeta } from "../lib/warnings";
import {
  activeForecastProducts,
  sourceAvailable,
  type AppMode,
  type ForecastMeta,
  type ForecastProductId,
  type ForecastSelection,
} from "../lib/forecasts";
import { ForecastPanel } from "./ForecastPanel";

const sameQuery = (a: QueryState, b: QueryState) => JSON.stringify(a) === JSON.stringify(b);

interface Props {
  registry: Registry;
  mode: AppMode;
  query: QueryState;
  activePreset: string | null;
  result: QueryResult | null;
  busy: boolean;
  forecastQueryError: string | null;
  onQueryChange(q: QueryState, presetId: string | null): void;
  onSelectWarnings(): void;
  warnings: WarningsMeta | null;
  warnSelection: WarnSelection | null;
  onSelectWarning(sel: WarnSelection | null): void;
  forecasts: ForecastMeta | null;
  forecastSelection: ForecastSelection;
  onSelectForecast(productId: ForecastProductId): void;
  onForecastChange(selection: ForecastSelection): void;
  dashboardOpen: boolean;
  onToggleDashboard(): void;
  onShare(): string;
  dataUrl: string;
  drawerOpen?: boolean;
  onCloseDrawer?(): void;
  onOpenDocs(): void;
}

export function Sidebar(p: Props) {
  const { registry, query } = p;
  const [moreOpen, setMoreOpen] = useState(false);
  const [shared, setShared] = useState(false);
  const asideRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [showCue, setShowCue] = useState(false);

  // indiciul de scroll apare cât timp rezultatele (cifrele, filtrele) sunt sub marginea de
  // jos a panoului — ca la prima vizită, când vezi harta + întrebările dar nu și numerele
  useEffect(() => {
    const el = asideRef.current;
    const anchor = resultsRef.current;
    if (!el || !anchor) return;
    const update = () => {
      const canScroll = el.scrollHeight - el.clientHeight > 24;
      const below = anchor.getBoundingClientRect().top > el.getBoundingClientRect().bottom - 48;
      setShowCue(canScroll && below);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      ro.disconnect();
    };
  }, [p.mode, p.result, p.query, p.activePreset, p.busy, p.forecastSelection]);

  async function share() {
    const url = p.onShare();
    let ok = false;
    try {
      await navigator.clipboard.writeText(url);
      ok = true;
    } catch {
      ok = false; // context nesecurizat / permisiune refuzată — URL-ul e oricum în bara de adrese
    }
    setShared(true);
    window.setTimeout(() => setShared(false), ok ? 2500 : 4000);
  }
  const warnActive = hasAnyWarnings(p.warnings);
  const filterVars = useMemo(
    () => registry.variables.filter((v) => v.role.includes("filter")),
    [registry]
  );

  const activePresetObj = useMemo(
    () => [...PRESETS, ...MORE_PRESETS].find((pr) => pr.id === p.activePreset) ?? null,
    [p.activePreset]
  );
  // definiția afișată ține cont de varianta activă (ex. oraș vs sat)
  const definition = useMemo(() => {
    if (!activePresetObj) return null;
    if (activePresetObj.variants) {
      const v = activePresetObj.variants.find((v) => sameQuery(query, v.query));
      return (v ?? activePresetObj.variants[0]).definition;
    }
    return activePresetObj.definition;
  }, [activePresetObj, query]);

  function update(q: QueryState) {
    p.onQueryChange(q, null); // orice editare manuală iese din preset
  }

  function setConstraint(i: number, c: Constraint) {
    const constraints = query.constraints.slice();
    constraints[i] = c;
    update({ ...query, constraints });
  }

  function addConstraint(varId: string) {
    const v = varById(registry, varId);
    // interval implicit: dacă variabila are un domeniu declarat (filterRange), pornim cu el
    // (adăugarea filtrului nu exclude pe nimeni); altfel folosim percentilele p02–p98
    const [dMin, dMax] = v.filterRange ?? [v.stats?.p02 ?? null, v.stats?.p98 ?? null];
    const c: Constraint =
      v.dtype === "cat"
        ? { varId, op: "in", values: [] }
        : { varId, op: "between", min: dMin, max: dMax };
    update({ ...query, constraints: [...query.constraints, c] });
  }

  function removeConstraint(i: number) {
    update({ ...query, constraints: query.constraints.filter((_, j) => j !== i) });
  }

  return (
    <aside ref={asideRef} className={"sidebar" + (p.drawerOpen ? " drawer-open" : "")}>
      <header>
        <h1>Unde locuiesc românii?</h1>
        <p className="subtitle">{registry.dataNote}</p>
      </header>

      <section>
        <h2>Întrebări</h2>
        <div className="presets">
          {/* meteo apare prima, marcată, DOAR când există avertizări active */}
          {warnActive && (
            <button
              className={"preset warn-preset" + (p.mode === "warnings" ? " active" : "")}
              onClick={() => {
                p.onSelectWarnings();
                p.onCloseDrawer?.();
              }}
            >
              <span className="warn-badge">⚠ acum</span>
              Câți români sunt afectați de avertizări meteo?
            </button>
          )}
          {p.forecasts && activeForecastProducts(p.forecasts).map((productId) => {
            const product = p.forecasts!.products[productId];
            const available = sourceAvailable(p.forecasts!.sources[product.source]);
            return (
              <button
                key={productId}
                className={
                  "preset forecast-preset" +
                  (p.mode === "forecast" && productId === p.forecastSelection.productId ? " active" : "") +
                  (!available ? " unavailable" : "")
                }
                onClick={() => {
                  p.onSelectForecast(productId);
                  p.onCloseDrawer?.();
                }}
              >
                <span className="forecast-badge">prognoză</span>
                {product.question}
                {!available && <span className="warn-none-tag">indisponibilă</span>}
              </button>
            );
          })}
          {PRESETS.map((pr) => (
            <button
              key={pr.id}
              className={p.mode === "query" && pr.id === p.activePreset ? "preset active" : "preset"}
              onClick={() => {
                p.onQueryChange(pr.query, pr.id);
                p.onCloseDrawer?.();
              }}
            >
              {pr.title}
            </button>
          ))}

          <button className="preset more-toggle" onClick={() => setMoreOpen((v) => !v)}>
            {moreOpen ? "▾" : "▸"} Alte întrebări
          </button>
          {moreOpen && (
            <>
              {/* fără avertizări active, întrebarea meteo trăiește aici */}
              {!warnActive && p.warnings && (
                <button
                  className={"preset more-preset" + (p.mode === "warnings" ? " active" : "")}
                  onClick={p.onSelectWarnings}
                >
                  Câți români sunt afectați de avertizări meteo?{" "}
                  <span className="warn-none-tag">momentan niciuna</span>
                </button>
              )}
              {MORE_PRESETS.map((pr) => (
                <button
                  key={pr.id}
                  className={
                    "preset more-preset" +
                    (p.mode === "query" && pr.id === p.activePreset ? " active" : "")
                  }
                  onClick={() => p.onQueryChange(pr.query, pr.id)}
                >
                  {pr.title}
                </button>
              ))}
            </>
          )}
        </div>
      </section>

      {/* ancoră: aici încep rezultatele (cifre + filtre) — ținta indiciului de scroll */}
      <div ref={resultsRef} className="results-anchor" />

      {p.mode === "warnings" && p.warnings && (
        <WarningsPanel
          dataUrl={p.dataUrl}
          registry={registry}
          meta={p.warnings}
          selection={p.warnSelection}
          onSelect={p.onSelectWarning}
        />
      )}

      {p.mode === "forecast" && p.forecasts && (
        <ForecastPanel
          registry={registry}
          meta={p.forecasts}
          selection={p.forecastSelection}
          result={p.result}
          busy={p.busy}
          queryError={p.forecastQueryError}
          onChange={p.onForecastChange}
        />
      )}

      {p.mode === "query" && (
        <>
          <section className="kpi">
            {activePresetObj?.variants && (
              <div className="variants">
                {activePresetObj.variants.map((v) => (
                  <button
                    key={v.label}
                    className={"variant" + (sameQuery(query, v.query) ? " active" : "")}
                    onClick={() => p.onQueryChange(v.query, activePresetObj.id)}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            )}
            {activePresetObj?.threshold && (
              <ThresholdBox
                threshold={activePresetObj.threshold}
                query={query}
                onChange={(nq) => p.onQueryChange(nq, activePresetObj.id)}
              />
            )}
            {p.busy && <div className="busy">se calculează…</div>}
            {p.result && !p.busy && (
              <>
                <div className="kpi-value">{fmtInt(p.result.value)}</div>
                <div className="kpi-sub">
                  {fmtSharePct(p.result.pctOfNational)} din total național
                </div>
              </>
            )}
            {definition && <p className="definition">{definition}</p>}
          </section>

          <section>
            <h2>Filtre</h2>
        <label className="row">
          <span>Numărăm</span>
          <select
            value={query.measure}
            onChange={(e) => update({ ...query, measure: e.target.value })}
          >
            {registry.measures.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>

        {query.constraints.map((c, i) => {
          // ascunse din Filtre (rămân active în interogare, dar fără rând redundant):
          //  • variabile fără rol „filter" (ex. scenariul de inundații, ales din variante)
          //  • variabila controlată deja de caseta de prag din secțiunea KPI
          const hidden =
            !varById(registry, c.varId).role.includes("filter") ||
            c.varId === activePresetObj?.threshold?.varId;
          if (hidden) return null;
          return (
            <ConstraintRow
              key={`${c.varId}-${i}`}
              registry={registry}
              constraint={c}
              onChange={(nc) => setConstraint(i, nc)}
              onRemove={() => removeConstraint(i)}
            />
          );
        })}

        <label className="row add-filter">
          <span>Adaugă filtru</span>
          <select value="" onChange={(e) => e.target.value && addConstraint(e.target.value)}>
            <option value="">alege variabila…</option>
            {Object.entries(registry.groups).map(([gid, glabel]) => (
              <optgroup key={gid} label={glabel}>
                {filterVars
                  .filter((v) => v.group === gid)
                  .map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
          </section>
        </>
      )}

      <section className="sidebar-actions">
        <div className="header-actions">
          <button
            className={"dash-toggle" + (p.dashboardOpen ? " active" : "")}
            onClick={p.onToggleDashboard}
          >
            📊 {p.dashboardOpen ? "Înapoi la hartă" : "Analiză — distribuții și comparații"}
          </button>
          <button className="share-btn" onClick={share} title="Copiază un link către harta curentă">
            {shared ? "✓ Link copiat" : "🔗 Partajează harta"}
          </button>
        </div>
        <button
          className="docs-btn"
          onClick={p.onOpenDocs}
          title="Metodă, surse de date, soluții open source și limitări"
        >
          ℹ️ Documentație — metodă, surse și limitări
        </button>
      </section>

      {showCue && (
        <button
          className="scroll-cue"
          onClick={() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
          title="Vezi rezultatele mai jos"
        >
          <span>rezultate mai jos</span>
          <span className="scroll-cue-arrow">↓</span>
        </button>
      )}
    </aside>
  );
}

/** Caseta de prag reglabil a unui preset — editarea păstrează presetul activ. */
function ThresholdBox({
  threshold,
  query,
  onChange,
}: {
  threshold: PresetThreshold;
  query: QueryState;
  onChange(q: QueryState): void;
}) {
  const current = query.constraints.find(
    (c): c is Extract<Constraint, { op: "between" }> =>
      c.op === "between" && c.varId === threshold.varId
  );
  const value = current ? current[threshold.bound] : threshold.default;

  function setValue(raw: string) {
    const v = raw === "" ? null : Number(raw);
    let found = false;
    const constraints = query.constraints.map((c) => {
      if (c.op === "between" && c.varId === threshold.varId) {
        found = true;
        return { ...c, [threshold.bound]: v };
      }
      return c;
    });
    if (!found) {
      constraints.push({
        varId: threshold.varId,
        op: "between",
        min: threshold.bound === "min" ? v : null,
        max: threshold.bound === "max" ? v : null,
        ...(threshold.inclusive ? { maxInclusive: true } : {}),
      });
    }
    onChange({ ...query, constraints });
  }

  return (
    <label className="threshold-box">
      <span>{threshold.label}</span>
      <span className="threshold-input">
        <input
          type="number"
          min={threshold.minValue}
          step={threshold.step ?? 1}
          value={value ?? ""}
          onChange={(e) => setValue(e.target.value)}
        />
        <span className="threshold-unit">{threshold.unit}</span>
      </span>
    </label>
  );
}

function ConstraintRow({
  registry,
  constraint: c,
  onChange,
  onRemove,
}: {
  registry: Registry;
  constraint: Constraint;
  onChange(c: Constraint): void;
  onRemove(): void;
}) {
  const v = varById(registry, c.varId);
  return (
    <div className="constraint">
      <div className="constraint-head">
        <span className="constraint-label" title={v.note}>
          {v.label}
          {v.unit ? ` (${v.unit})` : ""}
        </span>
        <button className="remove" onClick={onRemove} title="Șterge filtrul">
          ×
        </button>
      </div>
      {c.op === "between" ? (
        <NumericInputs v={v} c={c} onChange={onChange} />
      ) : (
        <CategoryChips v={v} c={c} registry={registry} onChange={onChange} />
      )}
    </div>
  );
}

function NumericInputs({
  v,
  c,
  onChange,
}: {
  v: VariableDef;
  c: Extract<Constraint, { op: "between" }>;
  onChange(c: Constraint): void;
}) {
  const lo = v.filterRange?.[0] ?? v.stats?.min ?? 0;
  const hi = v.filterRange?.[1] ?? v.stats?.max ?? 100;
  return (
    <div className="numeric">
      <input
        type="number"
        placeholder={`min (${fmtNum(lo, 0)})`}
        value={c.min ?? ""}
        onChange={(e) =>
          onChange({ ...c, min: e.target.value === "" ? null : Number(e.target.value) })
        }
      />
      <span>–</span>
      <input
        type="number"
        placeholder={`max (${fmtNum(hi, 0)})`}
        value={c.max ?? ""}
        onChange={(e) =>
          onChange({ ...c, max: e.target.value === "" ? null : Number(e.target.value) })
        }
      />
    </div>
  );
}

function CategoryChips({
  v,
  c,
  registry,
  onChange,
}: {
  v: VariableDef;
  c: Extract<Constraint, { op: "in" }>;
  registry: Registry;
  onChange(c: Constraint): void;
}) {
  // categoriile fixate (ex. „Alt tip") merg la final; restul păstrează ordinea după frecvență
  const pinLast = v.catPinLast ?? [];
  const cats = [...(v.categories ?? [])].sort(
    (a, b) => Number(pinLast.includes(a.value)) - Number(pinLast.includes(b.value))
  );
  function toggle(value: string) {
    const values = c.values.includes(value)
      ? c.values.filter((x) => x !== value)
      : [...c.values, value];
    onChange({ ...c, values });
  }
  return (
    <div className="chips">
      {cats.map((cat) => (
        <button
          key={cat.value}
          className={c.values.includes(cat.value) ? "chip on" : "chip"}
          onClick={() => toggle(cat.value)}
          title={fmtInt(cat.count) + " km²"}
        >
          {v.id === "county_mn" ? registry.countyLabels[cat.value] ?? cat.value : cat.value}
        </button>
      ))}
    </div>
  );
}
