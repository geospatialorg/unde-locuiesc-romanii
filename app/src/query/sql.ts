import type { Registry } from "../lib/registry";
import { varById } from "../lib/registry";
import type { Constraint, QueryState } from "./model";

function sqlLiteral(s: string): string {
  return `'${s.replace(/'/g, "''")}'`;
}

function constraintSql(reg: Registry, c: Constraint): string | null {
  const v = varById(reg, c.varId);
  const col = `"${v.id}"`;
  if (c.op === "in") {
    if (c.values.length === 0) return null;
    return `${col} IN (${c.values.map(sqlLiteral).join(", ")})`;
  }
  const parts: string[] = [];
  if (c.min != null) parts.push(`${col} >= ${c.min}`);
  if (c.max != null) parts.push(`${col} ${c.maxInclusive ? "<=" : "<"} ${c.max}`);
  if (parts.length === 0) return null;
  // în DuckDB NaN > orice — fără garda asta, un filtru doar cu prag minim ar include celulele fără date
  if (v.dtype === "float") parts.push(`NOT isnan(${col})`);
  return parts.join(" AND ");
}

/** FROM + WHERE pentru un set de constrângeri; join-uri doar pe tabelele efectiv folosite.
 *  `extraVars` forțează join-ul tabelelor unor variabile citite (nu doar filtrate) —
 *  folosit de dashboard, unde variabila analizată poate să nu apară în filtre. */
export function buildFromWhereFor(
  reg: Registry,
  constraints: Constraint[],
  extraVars: string[] = [],
  extraWhere: string[] = []
): { from: string; where: string } {
  const tables = new Set<string>(["core"]);
  for (const c of constraints) tables.add(varById(reg, c.varId).table);
  for (const id of extraVars) tables.add(varById(reg, id).table);

  let from = "FROM core";
  if (tables.has("env")) from += " JOIN env USING (cell_id)";
  if (tables.has("climate")) from += " JOIN climate USING (cell_id)";

  const clauses = constraints
    .map((c) => constraintSql(reg, c))
    .filter((s): s is string => s != null)
    .concat(extraWhere);
  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  return { from, where };
}

/** FROM + WHERE pentru starea curentă a interogării. */
export function buildFromWhere(reg: Registry, q: QueryState): { from: string; where: string } {
  return buildFromWhereFor(reg, q.constraints);
}

export function aggregateSql(reg: Registry, q: QueryState): string {
  const { from, where } = buildFromWhere(reg, q);
  return `SELECT sum("${q.measure}")::BIGINT AS value, count(*)::BIGINT AS n_cells ${from} ${where}`;
}

/** Celulele potrivite + valoarea măsurii pe fiecare (celula are 1 km² → valoarea = densitatea/km²). */
export function cellValuesSql(reg: Registry, q: QueryState): string {
  const { from, where } = buildFromWhere(reg, q);
  return `SELECT cell_id, "${q.measure}"::DOUBLE AS val ${from} ${where}`;
}

export function profileSql(cellId: number): string {
  return `SELECT * FROM core JOIN env USING (cell_id) LEFT JOIN climate USING (cell_id)
          WHERE cell_id = ${cellId}`;
}

export function countyDailySql(countyMn: string): string {
  return `SELECT date, tmin, tmax, precip FROM county_climate_daily
          WHERE county_mn = ${sqlLiteral(countyMn)} ORDER BY date`;
}

export function countyAnnualSql(countyMn: string): string {
  return `SELECT make_date(year, 1, 1) AS date, tmin, tmax, precip
          FROM county_climate_annual
          WHERE county_mn = ${sqlLiteral(countyMn)} ORDER BY year`;
}
