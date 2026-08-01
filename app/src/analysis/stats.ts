/** Statistici pe histograma ponderată (bin-uri fine) — cuantile prin interpolare pe cumulativă. */

import type { HistSpec } from "./sql";
import { N_BINS } from "./sql";

export interface WeightedDist {
  bins: Float64Array; // populația per bin (N_BINS)
  total: number;
  wmean: number | null;
}

export function distFromRows(
  rows: { bin: number; pop: number }[],
  wmean: number | null
): WeightedDist {
  const bins = new Float64Array(N_BINS);
  let total = 0;
  for (const r of rows) {
    bins[r.bin] += r.pop;
    total += r.pop;
  }
  return { bins, total, wmean };
}

/** Cuantila ponderată q∈(0,1): valoarea variabilei sub care trăiește q din populație. */
export function weightedQuantile(d: WeightedDist, spec: HistSpec, q: number): number | null {
  if (d.total <= 0) return null;
  const target = d.total * q;
  let acc = 0;
  for (let i = 0; i < N_BINS; i++) {
    const next = acc + d.bins[i];
    if (next >= target) {
      const frac = d.bins[i] > 0 ? (target - acc) / d.bins[i] : 0;
      return spec.lo + (i + frac) * spec.bw;
    }
    acc = next;
  }
  return spec.hi;
}

/** Reagregă bin-urile fine în ~n bin-uri de afișare (centre + valori). */
export function displayBins(
  d: WeightedDist,
  spec: HistSpec,
  n = 40
): { centers: number[]; values: number[] } {
  const per = Math.max(1, Math.round(N_BINS / n));
  const centers: number[] = [];
  const values: number[] = [];
  for (let i = 0; i < N_BINS; i += per) {
    let s = 0;
    for (let j = i; j < Math.min(i + per, N_BINS); j++) s += d.bins[j];
    centers.push(spec.lo + (i + per / 2) * spec.bw);
    values.push(s);
  }
  return { centers, values };
}
