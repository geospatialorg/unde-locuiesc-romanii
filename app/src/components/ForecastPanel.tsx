import { fmtInt, fmtSharePct } from "../lib/format";
import {
  effectiveThreshold,
  forecastDays,
  sourceAvailable,
  type ForecastMeta,
  type ForecastResult,
  type ForecastSelection,
} from "../lib/forecasts";
import type { Registry } from "../lib/registry";

interface Props {
  registry: Registry;
  meta: ForecastMeta;
  selection: ForecastSelection;
  result: ForecastResult | null;
  busy: boolean;
  queryError: string | null;
  onChange(selection: ForecastSelection): void;
}

function dayLabel(value: string): string {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString("ro-RO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function ForecastPanel({ registry, meta, selection, result, busy, queryError, onChange }: Props) {
  const product = meta.products[selection.productId];
  const source = meta.sources[product.source];
  const days = forecastDays(source);
  const measureLabel = registry.measures.find((item) => item.id === selection.measure)?.label ?? "persoane";
  const generated = new Date(meta.generated_utc).toLocaleString("ro-RO", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const run = source.run_utc
    ? new Date(source.run_utc).toLocaleString("ro-RO", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  const editableThreshold = product.source === "weather";
  const threshold = effectiveThreshold(product, selection);
  const overridden = selection.thresholdOverride != null;

  return (
    <section className="forecast-panel">
      <h2>{product.label}</h2>
      {editableThreshold && (
        <label className="threshold-box">
          <span>Prag {product.operator === ">=" ? "≥" : "≤"}</span>
          <span className="threshold-input">
            <input
              type="number"
              step={1}
              value={threshold}
              onChange={(event) =>
                onChange({
                  ...selection,
                  thresholdOverride: event.target.value === "" ? null : Number(event.target.value),
                })
              }
            />
            <span className="threshold-unit">{product.unit}</span>
            {overridden && (
              <button
                type="button"
                className="threshold-auto"
                title="Revino la pragul automat, ales după prognoză"
                onClick={() => onChange({ ...selection, thresholdOverride: null })}
              >
                ↺ auto ({product.threshold}
                {product.unit})
              </button>
            )}
          </span>
        </label>
      )}
      <label className="row">
        <span>Perioada</span>
        <select
          value={selection.date ?? "all"}
          onChange={(event) => onChange({ ...selection, date: event.target.value === "all" ? null : event.target.value })}
          disabled={!sourceAvailable(source)}
        >
          <option value="all">toate zilele prognozate</option>
          {days.map((day) => (
            <option key={day} value={day}>{dayLabel(day)}</option>
          ))}
        </select>
      </label>
      <label className="row">
        <span>Numărăm</span>
        <select
          value={selection.measure}
          onChange={(event) => onChange({ ...selection, measure: event.target.value })}
        >
          {registry.measures.map((measure) => (
            <option key={measure.id} value={measure.id}>{measure.label}</option>
          ))}
        </select>
      </label>

      <div aria-live="polite">
        {busy && <div className="busy">se calculează…</div>}
        {!busy && result && (
          <>
            <div className="kpi-value">{fmtInt(result.value)}</div>
            <div className="kpi-sub">
              {fmtSharePct(result.pctOfNational)} din totalul național
            </div>
          </>
        )}
      </div>
      {!sourceAvailable(source) && <p className="forecast-error">Prognoza acestei surse nu este încă disponibilă.</p>}
      {queryError && <p className="forecast-error">{queryError}</p>}
      {!source.ok && source.error && <p className="forecast-stale">{source.error}</p>}
      <p className="definition">
        {product.definition} Numărăm distinct populația rezidentă expusă cel puțin o dată în perioada aleasă.
      </p>
      <p className="forecast-source">
        {source.provider} · {source.model} · rezoluție nativă {source.resolution}
        {run ? ` · rulare ${run}` : ""} · manifest actualizat {generated}
      </p>
      <p className="forecast-source">Atribuire: {source.attribution}</p>
      <p className="forecast-source">Măsură: {measureLabel}. Prognoza indică expunere potențială, nu impact individual.</p>
    </section>
  );
}
