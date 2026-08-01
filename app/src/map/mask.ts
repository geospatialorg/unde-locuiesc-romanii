/**
 * Randarea măștii de celule: un canvas fixat pe dreptunghiul României, pictat
 * o singură dată per interogare. Pixel↔celulă se precalculează la prima randare
 * (laticea nu se schimbă), deci recolorarea unei interogări noi durează ~ms.
 *
 * Culoarea codifică DENSITATEA: celula are exact 1 km², deci valoarea măsurii pe
 * celulă este densitatea pe km². Rampă secvențială de roșuri pe scară logaritmică
 * (1 → 10.000 pe km²) — pal = puțini, închis = mulți. Celulele care satisfac
 * criteriul dar nu au pe nimeni (măsura 0) apar într-un gri abia perceptibil.
 *
 * Canvasul este ancorat în Web Mercator (MapLibre interpolează liniar în mercator
 * între colțurile date), iar fiecare pixel se proiectează invers mercator→lon/lat→3035.
 */

import type { CellBitset, GridSpec } from "../lib/grid";
import { e3035ToLonLat, latToMercY, lonLatTo3035, lonToMercX, mercXToLon, mercYToLat } from "../lib/proj";

export interface MaskRenderer {
  canvas: HTMLCanvasElement;
  /** colțurile [NV, NE, SE, SV] în lon/lat pentru sursa canvas MapLibre */
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  paint(bitset: CellBitset | null, values: Float32Array | null, flatColor?: string): void;
}

/** Rampa de densitate (ColorBrewer Reds) — aceleași opriri sunt folosite și în legendă. */
export const DENSITY_STOPS: [number, number, number][] = [
  [254, 229, 217],
  [252, 146, 114],
  [203, 24, 29],
  [103, 0, 13],
];
/** Plafonul scării: 10^4 = 10.000 pe km² (peste — aceeași culoare maximă). */
export const DENSITY_LOG_MAX = 4;

const EMPTY_MATCH: [number, number, number, number] = [148, 140, 134, 70]; // potrivit, nelocuit
const FLAT_COLOR: [number, number, number, number] = [214, 40, 40, 200]; // fallback fără valori

function parseColor(value: string | undefined): [number, number, number, number] | null {
  const match = /^#([0-9a-f]{6})$/i.exec(value ?? "");
  if (!match) return null;
  const number = Number.parseInt(match[1], 16);
  return [(number >> 16) & 255, (number >> 8) & 255, number & 255, 215];
}

// LUT 256 de culori interpolate liniar între opririle rampei
const LUT = new Uint8Array(256 * 3);
for (let i = 0; i < 256; i++) {
  const t = (i / 255) * (DENSITY_STOPS.length - 1);
  const k = Math.min(DENSITY_STOPS.length - 2, Math.floor(t));
  const f = t - k;
  for (let c = 0; c < 3; c++) {
    LUT[i * 3 + c] = Math.round(DENSITY_STOPS[k][c] * (1 - f) + DENSITY_STOPS[k + 1][c] * f);
  }
}

export function createMaskRenderer(spec: GridSpec, pxPerKm = 1.4): MaskRenderer {
  // dreptunghiul grilei în lon/lat (prin colțurile 3035)
  const corners = [
    e3035ToLonLat(spec.e_min, spec.n_top),
    e3035ToLonLat(spec.e_max, spec.n_top),
    e3035ToLonLat(spec.e_max, spec.n_min),
    e3035ToLonLat(spec.e_min, spec.n_min),
  ];
  const lons = corners.map((c) => c[0]);
  const lats = corners.map((c) => c[1]);
  const west = Math.min(...lons), east = Math.max(...lons);
  const south = Math.min(...lats), north = Math.max(...lats);

  const w = Math.round(spec.ncols * pxPerKm);
  const h = Math.round(spec.nrows * pxPerKm);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;

  // precalculează cell_id per pixel (o singură dată; -1 = în afara grilei)
  const lattice = new Int32Array(w * h);
  const x0 = lonToMercX(west), x1 = lonToMercX(east);
  const y0 = latToMercY(north), y1 = latToMercY(south);
  for (let py = 0; py < h; py++) {
    const lat = mercYToLat(y0 + ((py + 0.5) / h) * (y1 - y0));
    for (let px = 0; px < w; px++) {
      const lon = mercXToLon(x0 + ((px + 0.5) / w) * (x1 - x0));
      const [e, n] = lonLatTo3035(lon, lat);
      const col = Math.floor((e - spec.e_min) / spec.res);
      const row = Math.floor((spec.n_top - n) / spec.res);
      lattice[py * w + px] =
        col >= 0 && col < spec.ncols && row >= 0 && row < spec.nrows ? row * spec.ncols + col : -1;
    }
  }

  const img = ctx.createImageData(w, h);
  const data = img.data;
  const invLogMax = 1 / DENSITY_LOG_MAX;

  function paint(bitset: CellBitset | null, values: Float32Array | null, flatColor?: string): void {
    const thematic = parseColor(flatColor);
    if (!bitset) {
      data.fill(0);
    } else {
      for (let i = 0; i < lattice.length; i++) {
        const id = lattice[i];
        const o = i * 4;
        if (id < 0 || !bitset.has(id)) {
          data[o + 3] = 0;
          continue;
        }
        if (thematic || !values) {
          const color = thematic ?? FLAT_COLOR;
          data[o] = color[0];
          data[o + 1] = color[1];
          data[o + 2] = color[2];
          data[o + 3] = color[3];
          continue;
        }
        const v = values[id];
        if (v > 0) {
          const t = Math.min(1, Math.log10(v) * invLogMax);
          const k = (t * 255) | 0;
          data[o] = LUT[k * 3];
          data[o + 1] = LUT[k * 3 + 1];
          data[o + 2] = LUT[k * 3 + 2];
          data[o + 3] = 225;
        } else {
          // criteriul e satisfăcut, dar măsura e 0 — arătăm discret „aici nu locuiește nimeni"
          data[o] = EMPTY_MATCH[0];
          data[o + 1] = EMPTY_MATCH[1];
          data[o + 2] = EMPTY_MATCH[2];
          data[o + 3] = EMPTY_MATCH[3];
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  return {
    canvas,
    coordinates: [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ],
    paint,
  };
}
