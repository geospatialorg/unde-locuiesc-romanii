const nf = new Intl.NumberFormat("ro-RO");

export function fmtInt(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return nf.format(Math.round(x));
}

export function fmtNum(x: number | null | undefined, decimals = 1): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return new Intl.NumberFormat("ro-RO", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(x);
}

export function fmtPct(x: number | null | undefined, decimals = 1): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return `${fmtNum(x * 100, decimals)}%`;
}

/** Procent pentru o pondere din total: o valoare mică dar nenulă (ex. 0,04%) nu trebuie
 *  afișată ca „0,0%" (pare zero) — se arată „<0,1%". */
export function fmtSharePct(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "–";
  if (x > 0 && x < 0.001) return "<0,1%";
  return fmtPct(x, 1);
}
