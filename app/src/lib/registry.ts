export type VarDtype = "int" | "float" | "cat";
export type VarRole = "filter" | "profile";

export interface VarStats {
  min: number | null;
  max: number | null;
  p02: number | null;
  p50: number | null;
  p98: number | null;
  nulls: number;
}

export interface VarCategory {
  value: string;
  count: number;
}

export interface VariableDef {
  id: string;
  table: "core" | "env" | "climate";
  group: string;
  label: string;
  unit?: string;
  dtype: VarDtype;
  decimals?: number;
  role: VarRole[];
  note?: string;
  stats?: VarStats;
  categories?: VarCategory[];
  /** valori de categorie fixate la finalul listei de chips (ex. „Alt tip"), indiferent de
   *  frecvență — restul își păstrează ordinea (după număr de celule) */
  catPinLast?: string[];
  /** intervalul implicit al filtrului (min, max) — folosit la adăugarea filtrului și ca
   *  placeholder, când domeniul „conceptual" diferă de percentilele/limitele din date
   *  (ex. altitudinea: 0–2544 m, vârful Moldoveanu, chiar dacă DEM-ul nu atinge maximul) */
  filterRange?: [number | null, number | null];
}

export interface MeasureDef {
  id: string;
  label: string;
}

export interface Registry {
  version: string;
  generated: string;
  dataNote: string;
  climateYear: number;
  tables: Record<string, string>;
  groups: Record<string, string>;
  measures: MeasureDef[];
  national: Record<string, number>;
  countyLabels: Record<string, string>;
  variables: VariableDef[];
}

export async function loadRegistry(dataUrl: string): Promise<Registry> {
  const r = await fetch(`${dataUrl}/registry.json`);
  if (!r.ok) throw new Error(`registry.json: ${r.status}`);
  return (await r.json()) as Registry;
}

export function varById(reg: Registry, id: string): VariableDef {
  const v = reg.variables.find((v) => v.id === id);
  if (!v) throw new Error(`variabilă necunoscută: ${id}`);
  return v;
}
