/** Modelul de constrângeri — AST-ul minimal al v0 (doar AND între constrângeri). */

export type Constraint =
  | {
      varId: string;
      op: "between";
      min: number | null;
      max: number | null;
      /** dacă e true, capătul superior e inclusiv (≤ max) în loc de strict (< max);
       *  necesar pt. praguri unde valoarea „0" trebuie să selecteze celulele cu exact 0 */
      maxInclusive?: boolean;
    }
  | { varId: string; op: "in"; values: string[] };

export interface QueryState {
  measure: string; // id-ul măsurii (pop_total, pop_f, …)
  constraints: Constraint[];
}

export interface QueryResult {
  value: number;
  nCells: number;
  pctOfNational: number;
  cellIds: Uint32Array;
}

export function describeConstraint(
  c: Constraint,
  label: string,
  unit: string | undefined,
  fmt: (x: number) => string
): string {
  if (c.op === "in") return `${label}: ${c.values.join(", ")}`;
  const u = unit ? ` ${unit}` : "";
  const le = c.maxInclusive ? "≤" : "<";
  if (c.min != null && c.max != null) return `${label} între ${fmt(c.min)} și ${fmt(c.max)}${u}`;
  if (c.min != null) return `${label} ≥ ${fmt(c.min)}${u}`;
  if (c.max != null) return `${label} ${le} ${fmt(c.max)}${u}`;
  return label;
}
