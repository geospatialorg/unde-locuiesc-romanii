/** Propozițiile-explicație generate din statistici — limbaj simplu, cu cifre formate ro-RO. */

import { fmtInt, fmtNum, fmtPct } from "../lib/format";
import type { VariableDef } from "../lib/registry";

const u = (v: VariableDef) => (v.unit ? ` ${v.unit}` : "");

export function numericSentences(
  v: VariableDef,
  measureLabel: string,
  areaLabel: string,
  stats: { p10: number | null; p50: number | null; p90: number | null; wmean: number | null; total: number },
  dec: number
): string[] {
  const out: string[] = [];
  if (stats.p50 != null)
    out.push(
      `Jumătate dintre ${measureLabel} din ${areaLabel} trăiesc acolo unde „${v.label.toLowerCase()}” este sub ${fmtNum(stats.p50, dec)}${u(v)}.`
    );
  if (stats.p10 != null && stats.p90 != null)
    out.push(
      `80% trăiesc între ${fmtNum(stats.p10, dec)} și ${fmtNum(stats.p90, dec)}${u(v)}; ` +
        `media ponderată cu populația este ${stats.wmean != null ? fmtNum(stats.wmean, dec) : "–"}${u(v)}.`
    );
  return out;
}

export function categorySentences(
  _v: VariableDef,
  measureLabel: string,
  areaLabel: string,
  cats: { cat: string; pop: number }[],
  total: number
): string[] {
  if (!cats.length || total <= 0) return [];
  const top = cats[0];
  const out = [
    `Cei mai mulți ${measureLabel} din ${areaLabel} — ${fmtPct(top.pop / total)} (${fmtInt(top.pop)}) — ` +
      `se află în categoria „${top.cat}”.`,
  ];
  if (cats.length >= 3) {
    const t3 = cats.slice(0, 3).reduce((s, c) => s + c.pop, 0);
    out.push(
      `Primele trei categorii (${cats.slice(0, 3).map((c) => `„${c.cat}”`).join(", ")}) cumulează ${fmtPct(t3 / total)}.`
    );
  }
  return out;
}

export function comparisonSentence(
  v: VariableDef,
  aLabel: string,
  bLabel: string,
  aP50: number | null,
  bP50: number | null,
  dec: number
): string | null {
  if (aP50 == null || bP50 == null) return null;
  const diff = aP50 - bP50;
  const rel = Math.abs(diff) < Math.max(Math.abs(aP50), 1e-9) * 0.02 ? "aproape egală cu" : diff > 0 ? "mai mare decât" : "mai mică decât";
  return (
    `Mediana pentru ${aLabel} (${fmtNum(aP50, dec)}${u(v)}) este ${rel} cea pentru ${bLabel} ` +
    `(${fmtNum(bP50, dec)}${u(v)}).`
  );
}
