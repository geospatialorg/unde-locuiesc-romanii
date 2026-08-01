/** Gazetteer local: UAT-uri + localități (din intravilan), pentru căutarea de pe hartă. */

export interface GazEntry {
  k: "u" | "l"; // uat | localitate
  n: string; // nume
  t: string; // tip (comună/oraș/municipiu · sat/localitate urbană/sector)
  j: string; // județ
  b: [number, number, number, number]; // bbox WGS84 [minx,miny,maxx,maxy]
  s?: string; // numele normalizat (calculat la încărcare)
}

/** Aceeași normalizare la indexare și interogare: minuscule, fără diacritice. */
export function norm(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

let cache: Promise<GazEntry[]> | null = null;

export function loadGazetteer(dataUrl: string): Promise<GazEntry[]> {
  cache ??= fetch(`${dataUrl}/gazetteer.json`)
    .then((r) => {
      if (!r.ok) throw new Error(`gazetteer.json: ${r.status}`);
      return r.json() as Promise<GazEntry[]>;
    })
    .then((rows) => {
      for (const e of rows) e.s = norm(e.n);
      return rows;
    });
  return cache;
}

/** Căutare cu rang: potrivire la început > la început de cuvânt > oriunde; UAT înaintea satelor. */
export function searchGazetteer(entries: GazEntry[], q: string, limit = 12): GazEntry[] {
  const nq = norm(q.trim());
  if (nq.length < 2) return [];
  const scored: { e: GazEntry; score: number }[] = [];
  for (const e of entries) {
    const idx = e.s!.indexOf(nq);
    if (idx < 0) continue;
    const boundary = idx === 0 ? 0 : /[\s\-.]/.test(e.s![idx - 1]) ? 1 : 3;
    const score = boundary + (e.k === "u" ? 0 : 0.5) + e.s!.length / 1000;
    scored.push({ e, score });
  }
  scored.sort((a, b) => a.score - b.score || a.e.s!.localeCompare(b.e.s!));
  return scored.slice(0, limit).map((x) => x.e);
}
