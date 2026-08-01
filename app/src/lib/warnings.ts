/** Avertizări meteo — produse de refresher-ul din container (live/).
 *  Două surse: `nowcasting` (imediate, ore) și `general` (atenționări/avertizări, zile). */

export type WarnSource = "nowcasting" | "general";

export interface WarningLevelSummary {
  code: string;
  name: string;
  color: string;
  rank: number;
  pop: number;
  n_cells: number;
}

export interface WarningMessage {
  source: WarnSource;
  id: string;
  group_id: string;
  kind: string;
  level_code: string;
  level_name: string;
  color: string;
  phenomenon: string;
  start: string | null;
  end: string | null;
  interval: string | null;
  entity: string;
  area_text: string;
  affected_pop: number;
  counties?: string[];
  n_zones?: number;
  level_mix?: { code: string; name: string; color: string; n: number }[];
}

/** Nivelurile distincte prezente în datele curente (pentru legendă), sortate de la sever la ușor. */
export function levelsPresent(m: WarningsMeta): WarningLevelSummary[] {
  const byCode = new Map<string, WarningLevelSummary>();
  for (const src of ["nowcasting", "general"] as WarnSource[])
    for (const l of m.sources[src].levels) if (!byCode.has(l.code)) byCode.set(l.code, l);
  return [...byCode.values()].sort((a, b) => b.rank - a.rank);
}

export interface SourceSummary {
  ok: boolean;
  total_affected: number;
  n_messages: number;
  levels: WarningLevelSummary[];
  messages: WarningMessage[];
}

export interface WarningsMeta {
  generated_utc: string;
  sources_url: Record<WarnSource, string>;
  combined: { total_affected: number };
  sources: Record<WarnSource, SourceSummary>;
}

export function hasAnyWarnings(m: WarningsMeta | null): boolean {
  return !!m && (m.sources.nowcasting.n_messages > 0 || m.sources.general.n_messages > 0);
}

export async function loadWarnings(dataUrl: string): Promise<WarningsMeta | null> {
  try {
    const r = await fetch(`${dataUrl}/live/warnings.json`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as WarningsMeta;
  } catch {
    return null;
  }
}

const cellsUrl = (dataUrl: string) => `${dataUrl}/live/warnings_cells.parquet`;
const cellMsgUrl = (dataUrl: string) => `${dataUrl}/live/warnings_cell_msg.parquet`;

/** Populația afectată pe sursă și cod de severitate, pentru măsura aleasă (canonic în DuckDB). */
export function byLevelSql(dataUrl: string, measure: string): string {
  return `SELECT w.source, w.level_code, w.level_name, any_value(w.level_rank) AS rank,
                 sum(c."${measure}")::BIGINT AS pop, count(*)::BIGINT AS n_cells
          FROM read_parquet('${cellsUrl(dataUrl)}') w JOIN core c USING (cell_id)
          GROUP BY 1, 2, 3`;
}

/** Total combinat: celule distincte sub cel puțin o avertizare (fără dublă numărare între surse). */
export function combinedTotalSql(dataUrl: string, measure: string): string {
  return `SELECT sum(c."${measure}")::BIGINT AS pop, count(*)::BIGINT AS n_cells
          FROM core c JOIN (SELECT DISTINCT cell_id FROM read_parquet('${cellsUrl(dataUrl)}')) u
          USING (cell_id)`;
}

/** Populația afectată de FIECARE mesaj în parte (distinct, măsură-conștient). */
export function byMessageSql(dataUrl: string, measure: string): string {
  return `SELECT w.group_id, sum(c."${measure}")::BIGINT AS pop
          FROM read_parquet('${cellMsgUrl(dataUrl)}') w JOIN core c USING (cell_id)
          GROUP BY 1`;
}
