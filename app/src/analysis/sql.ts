/** Interogările dashboardului de analiză — toate ponderate cu măsura aleasă, toate în DuckDB.
 *  Aria de analiză („România" sau un județ) e exprimată ca simplă constrângere pe county_mn,
 *  deci trece prin același compilator ca filtrele obișnuite. */

import type { Registry } from "../lib/registry";
import { varById } from "../lib/registry";
import type { Constraint } from "../query/model";
import { buildFromWhereFor } from "../query/sql";

export const N_BINS = 120; // bin-uri fine; afișarea le agregă, cuantilele le folosesc direct

export interface HistSpec {
  lo: number;
  hi: number;
  bw: number;
}

/** Intervalul histogramei din statisticile registrului (p02–p98, cu fallback la min–max). */
export function histSpec(reg: Registry, varId: string): HistSpec {
  const s = varById(reg, varId).stats;
  let lo = s?.p02 ?? s?.min ?? 0;
  let hi = s?.p98 ?? s?.max ?? 1;
  if (!(hi > lo)) {
    lo = s?.min ?? 0;
    hi = s?.max ?? lo + 1;
  }
  if (!(hi > lo)) hi = lo + 1;
  return { lo, hi, bw: (hi - lo) / N_BINS };
}

function areaConstraint(countyMn: string | null): Constraint[] {
  if (!countyMn) return [];
  return [{ varId: "county_mn", op: "in", values: [countyMn] }];
}

function validVar(reg: Registry, varId: string): string[] {
  const v = varById(reg, varId);
  const guards = [`"${v.id}" IS NOT NULL`];
  if (v.dtype === "float") guards.push(`NOT isnan("${v.id}")`);
  return guards;
}

/** Histogramă ponderată: populația (măsura) pe bin-uri fine ale variabilei numerice. */
export function weightedHistSql(
  reg: Registry,
  varId: string,
  measure: string,
  baseConstraints: Constraint[],
  countyMn: string | null
): string {
  const { lo, bw } = histSpec(reg, varId);
  const constraints = [...baseConstraints, ...areaConstraint(countyMn)];
  const { from, where } = buildFromWhereFor(reg, constraints, [varId, "county_mn"], validVar(reg, varId));
  return `SELECT LEAST(GREATEST(floor(("${varId}" - ${lo}) / ${bw})::INT, 0), ${N_BINS - 1}) AS bin,
                 sum("${measure}")::DOUBLE AS pop
          ${from} ${where} GROUP BY 1 ORDER BY 1`;
}

/** Media ponderată + total, pentru propozițiile generate. */
export function weightedMeanSql(
  reg: Registry,
  varId: string,
  measure: string,
  baseConstraints: Constraint[],
  countyMn: string | null
): string {
  const constraints = [...baseConstraints, ...areaConstraint(countyMn)];
  const { from, where } = buildFromWhereFor(reg, constraints, [varId, "county_mn"], validVar(reg, varId));
  return `SELECT sum("${varId}" * "${measure}") / NULLIF(sum("${measure}"), 0) AS wmean,
                 sum("${measure}")::DOUBLE AS pop
          ${from} ${where}`;
}

/** Distribuția pe categorii: populația (măsura) per valoare a variabilei categoriale. */
export function categoryDistSql(
  reg: Registry,
  varId: string,
  measure: string,
  baseConstraints: Constraint[],
  countyMn: string | null
): string {
  const constraints = [...baseConstraints, ...areaConstraint(countyMn)];
  const { from, where } = buildFromWhereFor(reg, constraints, [varId, "county_mn"], validVar(reg, varId));
  return `SELECT "${varId}"::VARCHAR AS cat, sum("${measure}")::DOUBLE AS pop, count(*)::BIGINT AS cells
          ${from} ${where} GROUP BY 1 ORDER BY pop DESC`;
}

/** Clasamentul județelor după media ponderată a variabilei numerice. */
export function countyRankingSql(
  reg: Registry,
  varId: string,
  measure: string,
  baseConstraints: Constraint[]
): string {
  const { from, where } = buildFromWhereFor(
    reg,
    baseConstraints,
    [varId, "county_mn"],
    [...validVar(reg, varId), `county_mn IS NOT NULL`]
  );
  return `SELECT county_mn::VARCHAR AS mn,
                 sum("${varId}" * "${measure}") / NULLIF(sum("${measure}"), 0) AS wmean,
                 sum("${measure}")::DOUBLE AS pop
          ${from} ${where} GROUP BY 1 HAVING sum("${measure}") > 0 ORDER BY wmean DESC`;
}
