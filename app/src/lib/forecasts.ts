import type { QueryResult } from "../query/model";

export type AppMode = "warnings" | "forecast" | "query";
export type ForecastSourceId = "weather" | "air";
export type ForecastProductId = "heat" | "cold" | "air_poor";

export interface ForecastSource {
  ok: boolean;
  provider: string;
  model: string;
  run_utc: string | null;
  data_file: string | null;
  map_file: string | null;
  days: string[];
  resolution: string;
  attribution: string;
  error?: string;
}

export interface ForecastProduct {
  source: ForecastSourceId;
  field: string;
  reducer: "min" | "max";
  operator: "<=" | ">=";
  threshold: number;
  unit: string;
  label: string;
  question: string;
  definition: string;
  color: string;
  /** produsul e relevant pentru prognoza curentă (ex. „ger" e ascuns vara) */
  active?: boolean;
}

export interface ForecastMeta {
  schema_version: 1;
  generated_utc: string;
  sources: Record<ForecastSourceId, ForecastSource>;
  products: Record<ForecastProductId, ForecastProduct>;
}

export interface ForecastSelection {
  productId: ForecastProductId;
  date: string | null;
  measure: string;
  /** prag ales manual de utilizator; null = pragul auto (dinamic) al produsului */
  thresholdOverride?: number | null;
}

/** pragul efectiv al selecției: override-ul manual dacă există, altfel auto-ul produsului */
export function effectiveThreshold(product: ForecastProduct, selection: ForecastSelection): number {
  return selection.thresholdOverride != null ? selection.thresholdOverride : product.threshold;
}

export const FORECAST_PRODUCT_ORDER: ForecastProductId[] = ["heat", "cold", "air_poor"];

export const DEFAULT_FORECAST_SELECTION: ForecastSelection = {
  productId: "heat",
  date: null,
  measure: "pop_total",
  thresholdOverride: null,
};

/** produsele relevante pentru prognoza curentă, în ordine (ascunde cele cu active:false) */
export function activeForecastProducts(meta: ForecastMeta): ForecastProductId[] {
  return FORECAST_PRODUCT_ORDER.filter((id) => meta.products[id]?.active !== false);
}

function validSource(value: unknown): value is ForecastSource {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.ok === "boolean" &&
    typeof item.provider === "string" &&
    typeof item.model === "string" &&
    (item.run_utc == null || typeof item.run_utc === "string") &&
    (item.data_file == null || typeof item.data_file === "string") &&
    (item.map_file == null || typeof item.map_file === "string") &&
    Array.isArray(item.days) && item.days.every((day) => typeof day === "string") &&
    typeof item.resolution === "string" &&
    typeof item.attribution === "string"
  );
}

function validProduct(value: unknown): value is ForecastProduct {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    (item.source === "weather" || item.source === "air") &&
    typeof item.field === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(item.field) &&
    (item.reducer === "min" || item.reducer === "max") &&
    (item.operator === "<=" || item.operator === ">=") &&
    typeof item.threshold === "number" && Number.isFinite(item.threshold) &&
    ["unit", "label", "question", "definition", "color"].every((key) => typeof item[key] === "string")
  );
}

export async function loadForecasts(dataUrl: string): Promise<ForecastMeta | null> {
  try {
    const response = await fetch(`${dataUrl}/live/forecast/manifest.json`, { cache: "no-store" });
    if (!response.ok) return null;
    const value = (await response.json()) as ForecastMeta;
    if (
      value.schema_version !== 1 ||
      typeof value.generated_utc !== "string" ||
      !validSource(value.sources?.weather) ||
      !validSource(value.sources?.air) ||
      FORECAST_PRODUCT_ORDER.some((id) => !validProduct(value.products?.[id]))
    ) return null;
    return value;
  } catch {
    return null;
  }
}

export function sourceAvailable(source: ForecastSource): boolean {
  return !!source.data_file && !!source.map_file && forecastDays(source).length > 0;
}

function localToday(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Bucharest",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts();
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function forecastDays(source: ForecastSource): string[] {
  const today = localToday();
  return Array.isArray(source.days)
    ? source.days.filter((day) => /^\d{4}-\d{2}-\d{2}$/.test(day) && day >= today)
    : [];
}

function sqlString(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

function safeFile(dataUrl: string, path: string | null): string {
  if (!path || path.startsWith("/") || path.split("/").includes("..")) {
    throw new Error("cale de prognoză invalidă");
  }
  return `${dataUrl.replace(/\/$/, "")}/${path}`;
}

function forecastCte(dataUrl: string, meta: ForecastMeta, selection: ForecastSelection): string {
  const product = meta.products[selection.productId];
  const source = product && meta.sources[product.source];
  if (!product || !source || !sourceAvailable(source)) throw new Error("prognoză indisponibilă");
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(product.field)) throw new Error("câmp invalid");
  if (!(["min", "max"] as string[]).includes(product.reducer)) throw new Error("agregare invalidă");
  if (!(["<=", ">="] as string[]).includes(product.operator)) throw new Error("operator invalid");
  const threshold = effectiveThreshold(product, selection);
  if (!Number.isFinite(threshold)) throw new Error("prag invalid");
  if (selection.date && !/^\d{4}-\d{2}-\d{2}$/.test(selection.date)) throw new Error("dată invalidă");

  const dataFile = sqlString(safeFile(dataUrl, source.data_file));
  const mapFile = sqlString(safeFile(dataUrl, source.map_file));
  const field = `"${product.field}"`;
  const availableDays = forecastDays(source).map((day) => `DATE ${sqlString(day)}`).join(", ");
  const forecast = selection.date
    ? `SELECT grid_id, ${field}::DOUBLE AS val FROM read_parquet(${dataFile})
       WHERE valid_date = DATE ${sqlString(selection.date)}`
    : `SELECT grid_id, ${product.reducer}(${field})::DOUBLE AS val FROM read_parquet(${dataFile})
       WHERE valid_date IN (${availableDays}) GROUP BY grid_id`;

  // Interpolare biliniara pe cele 4 noduri vecine din grila nativa (rara) — evita
  // petele dreptunghiulare late cat o celula Voronoi a grilei native (~0,1-0,25°)
  // care ar aparea daca s-ar folosi doar cel mai apropiat nod (m.grid_id).
  return `WITH forecast AS (${forecast}), interp AS (
            SELECT m.cell_id,
              (coalesce(m.weight_a * fa.val, 0) + coalesce(m.weight_b * fb.val, 0)
               + coalesce(m.weight_c * fc.val, 0) + coalesce(m.weight_d * fd.val, 0))
              / NULLIF(
                (CASE WHEN fa.val IS NULL THEN 0 ELSE m.weight_a END)
                + (CASE WHEN fb.val IS NULL THEN 0 ELSE m.weight_b END)
                + (CASE WHEN fc.val IS NULL THEN 0 ELSE m.weight_c END)
                + (CASE WHEN fd.val IS NULL THEN 0 ELSE m.weight_d END), 0) AS val
            FROM read_parquet(${mapFile}) m
            LEFT JOIN forecast fa ON fa.grid_id = m.grid_id_a
            LEFT JOIN forecast fb ON fb.grid_id = m.grid_id_b
            LEFT JOIN forecast fc ON fc.grid_id = m.grid_id_c
            LEFT JOIN forecast fd ON fd.grid_id = m.grid_id_d
          ), exposed AS (
            SELECT cell_id, val FROM interp
            WHERE isfinite(val) AND val ${product.operator} ${threshold}
          )`;
}

export function forecastAggregateSql(
  dataUrl: string,
  meta: ForecastMeta,
  selection: ForecastSelection
): string {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(selection.measure)) throw new Error("măsură invalidă");
  return `${forecastCte(dataUrl, meta, selection)}
          SELECT coalesce(sum(c."${selection.measure}"), 0)::BIGINT AS value,
                 count(*)::BIGINT AS n_cells
          FROM exposed e JOIN core c USING (cell_id)`;
}

/** Celulele expuse + valoarea măsurii pe fiecare — la fel ca la celelalte întrebări,
 * ca să se coloreze gradual după densitatea populației, nu cu o culoare uniformă. */
export function forecastCellValuesSql(
  dataUrl: string,
  meta: ForecastMeta,
  selection: ForecastSelection
): string {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(selection.measure)) throw new Error("măsură invalidă");
  return `${forecastCte(dataUrl, meta, selection)}
          SELECT e.cell_id, c."${selection.measure}"::DOUBLE AS val
          FROM exposed e JOIN core c USING (cell_id)`;
}

export function locationForecastSql(
  dataUrl: string,
  meta: ForecastMeta,
  sourceId: ForecastSourceId,
  cellId: number
): string | null {
  const source = meta.sources[sourceId];
  if (!sourceAvailable(source)) return null;
  if (!Number.isSafeInteger(cellId) || cellId < 0) throw new Error("celulă invalidă");
  const dataFile = sqlString(safeFile(dataUrl, source.data_file));
  const mapFile = sqlString(safeFile(dataUrl, source.map_file));
  const days = forecastDays(source).map((day) => `DATE ${sqlString(day)}`).join(", ");
  const fields = sourceId === "weather"
    ? "f.tmin::DOUBLE AS tmin, f.tmax::DOUBLE AS tmax"
    : `f.aqi_rank::INTEGER AS aqi_rank, f.pm25_max::DOUBLE AS pm25_max,
       f.pm10_max::DOUBLE AS pm10_max, f.no2_max::DOUBLE AS no2_max,
       f.o3_max::DOUBLE AS o3_max, f.so2_max::DOUBLE AS so2_max`;
  return `SELECT CAST(f.valid_date AS VARCHAR) AS day, ${fields}
          FROM read_parquet(${mapFile}) m JOIN read_parquet(${dataFile}) f USING (grid_id)
          WHERE m.cell_id = ${cellId} AND f.valid_date IN (${days}) ORDER BY f.valid_date`;
}

export function validForecastSelection(value: unknown): value is ForecastSelection {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    FORECAST_PRODUCT_ORDER.includes(item.productId as ForecastProductId) &&
    (item.date == null || (typeof item.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(item.date))) &&
    typeof item.measure === "string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(item.measure) &&
    (item.thresholdOverride == null ||
      (typeof item.thresholdOverride === "number" && Number.isFinite(item.thresholdOverride)))
  );
}

export type ForecastResult = QueryResult;
