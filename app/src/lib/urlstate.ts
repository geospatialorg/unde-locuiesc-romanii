/** Serializarea stării partajabile a hărții în URL (fragment #s=…).
 *  Compact (base64url peste JSON), tolerant la Unicode (nume românești: „oraș", „Câmpia Română"). */

import type { Constraint, QueryState } from "../query/model";
import type { WarnSelection } from "../components/WarningsPanel";
import {
  validForecastSelection,
  type AppMode,
  type ForecastSelection,
} from "./forecasts";

export interface ShareState {
  mode: AppMode;
  query: QueryState;
  preset: string | null;
  warn: WarnSelection | null;
  forecast?: ForecastSelection | null;
  view?: { center: [number, number]; zoom: number };
  cell?: number | null;
}

// formă compactă cu chei scurte, ca să nu umflăm URL-ul
interface Packed {
  v: 1;
  m: AppMode;
  ms: string;
  c: Constraint[];
  p?: string | null;
  w?: WarnSelection | null;
  f?: ForecastSelection | null;
  vw?: [number, number, number]; // lng, lat, zoom (rotunjite)
  cl?: number;
}

function toB64Url(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64Url(s: string): string {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (ch) => ch.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function encodeShare(s: ShareState): string {
  const p: Packed = {
    v: 1,
    m: s.mode,
    ms: s.query.measure,
    c: s.query.constraints,
  };
  if (s.preset) p.p = s.preset;
  if (s.warn) p.w = s.warn;
  if (s.forecast) p.f = s.forecast;
  if (s.view) p.vw = [round(s.view.center[0], 4), round(s.view.center[1], 4), round(s.view.zoom, 2)];
  if (s.cell != null) p.cl = s.cell;
  return toB64Url(JSON.stringify(p));
}

export function decodeShare(token: string): ShareState | null {
  try {
    const p = JSON.parse(fromB64Url(token)) as Packed;
    if (
      p.v !== 1 ||
      !["warnings", "forecast", "query"].includes(p.m) ||
      typeof p.ms !== "string" ||
      !/^[A-Za-z_][A-Za-z0-9_]*$/.test(p.ms)
    ) return null;
    const constraints = Array.isArray(p.c) ? p.c.filter(isConstraint) : [];
    const view = validView(p.vw)
      ? { center: [p.vw[0], p.vw[1]] as [number, number], zoom: p.vw[2] }
      : undefined;
    const cell = typeof p.cl === "number" && Number.isSafeInteger(p.cl) && p.cl >= 0 ? p.cl : null;
    return {
      mode: p.m,
      query: { measure: p.ms, constraints },
      preset: p.p ?? null,
      warn: p.w ?? null,
      forecast: validForecastSelection(p.f) ? p.f : null,
      view,
      cell,
    };
  } catch {
    return null;
  }
}

/** Citește starea din fragmentul URL curent (#s=…), dacă există. */
export function readShareFromUrl(): ShareState | null {
  const m = /[#&]s=([^&]+)/.exec(location.hash);
  return m ? decodeShare(m[1]) : null;
}

/** Construiește URL-ul complet de partajare și îl scrie în bara de adrese (fără intrare în istoric). */
export function buildShareUrl(s: ShareState): string {
  const token = encodeShare(s);
  const url = `${location.origin}${location.pathname}${location.search}#s=${token}`;
  history.replaceState(null, "", url);
  return url;
}

function round(x: number, d: number): number {
  const f = 10 ** d;
  return Math.round(x * f) / f;
}

function isConstraint(c: unknown): c is Constraint {
  if (!c || typeof c !== "object") return false;
  const o = c as Record<string, unknown>;
  if (typeof o.varId !== "string" || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(o.varId)) return false;
  if (o.op === "in") return Array.isArray(o.values) && o.values.every((value) => typeof value === "string");
  if (o.op !== "between") return false;
  const numberOrNull = (value: unknown) => value == null || (typeof value === "number" && Number.isFinite(value));
  return numberOrNull(o.min) && numberOrNull(o.max);
}

function validView(value: unknown): value is [number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 3 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item)) &&
    value[0] >= -180 && value[0] <= 180 &&
    value[1] >= -85 && value[1] <= 85 &&
    value[2] >= 0 && value[2] <= 24
  );
}
