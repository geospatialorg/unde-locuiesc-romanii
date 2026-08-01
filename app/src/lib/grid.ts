import { e3035ToLonLat, lonLatTo3035 } from "./proj";

export interface GridSpec {
  e_min: number;
  n_min: number;
  ncols: number;
  nrows: number;
  res: number;
  n_top: number;
  e_max: number;
  crs: string;
}

/** (lon, lat) → cell_id, sau null în afara grilei. Formulă închisă, fără tile-uri. */
export function lonLatToCellId(spec: GridSpec, lon: number, lat: number): number | null {
  const [e, n] = lonLatTo3035(lon, lat);
  const col = Math.floor((e - spec.e_min) / spec.res);
  const row = Math.floor((spec.n_top - n) / spec.res);
  if (col < 0 || col >= spec.ncols || row < 0 || row >= spec.nrows) return null;
  return row * spec.ncols + col;
}

/** Conturul celulei în lon/lat (colțurile pătratului de 1 km din EPSG:3035). */
export function cellRingLonLat(spec: GridSpec, cellId: number): [number, number][] {
  const row = Math.floor(cellId / spec.ncols);
  const col = cellId % spec.ncols;
  const e0 = spec.e_min + col * spec.res;
  const n1 = spec.n_top - row * spec.res; // marginea de nord
  const n0 = n1 - spec.res;
  const e1 = e0 + spec.res;
  return [
    e3035ToLonLat(e0, n1),
    e3035ToLonLat(e1, n1),
    e3035ToLonLat(e1, n0),
    e3035ToLonLat(e0, n0),
    e3035ToLonLat(e0, n1),
  ];
}

export async function loadGridSpec(dataUrl: string): Promise<GridSpec> {
  const r = await fetch(`${dataUrl}/gridspec.json`);
  if (!r.ok) throw new Error(`gridspec.json: ${r.status}`);
  return (await r.json()) as GridSpec;
}

/** Bitset peste celulele grilei (ncols × nrows). */
export class CellBitset {
  readonly bits: Uint8Array;
  constructor(readonly size: number) {
    this.bits = new Uint8Array((size + 7) >> 3);
  }
  static fromIds(size: number, ids: Uint32Array | number[]): CellBitset {
    const bs = new CellBitset(size);
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i as number] as number;
      bs.bits[id >> 3] |= 1 << (id & 7);
    }
    return bs;
  }
  has(id: number): boolean {
    return (this.bits[id >> 3] & (1 << (id & 7))) !== 0;
  }
}
