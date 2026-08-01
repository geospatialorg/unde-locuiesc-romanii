/** Client pentru serviciul local de rutare (pgRouting) — cel mai apropiat spital pe drum. */

import type { Feature } from "geojson";

export type RouteTarget = "hospital" | "sea" | "border" | "crossing" | "airport";

/** Culorile traseelor pe hartă — aceleași buline apar și în fișa celulei. */
export const ROUTE_COLORS: Record<RouteTarget, string> = {
  hospital: "#7c3aed", // violet
  crossing: "#0d9488", // teal
  airport: "#db2777", // magenta
  sea: "#0ea5e9", // albastru-cer, asociat mării
  border: "#64748b",
};

export interface RouteResult {
  ok: boolean;
  to: RouteTarget;
  hospital?: { nume: string; judet: string | null; city: string | null };
  crossing?: { name: string; waiting_time_min?: number | null };
  airport?: { label: string; name: string };
  /** ruta „către mare" are Constanța ca destinație fixă, nu cel mai apropiat punct de țărm */
  sea?: { name: string };
  drive_min: number;
  dist_km: number;
  straight_km: number;
  route: Feature;
}

export type RouteState =
  | { status: "loading" }
  | { status: "ok"; data: RouteResult }
  | { status: "offline" } // serviciul nu rulează / graful neimportat
  | { status: "error"; message: string };

export async function fetchRoute(
  routingUrl: string,
  lon: number,
  lat: number,
  to: RouteTarget = "hospital",
  signal?: AbortSignal
): Promise<RouteState> {
  try {
    const r = await fetch(
      `${routingUrl}/route?lon=${lon.toFixed(6)}&lat=${lat.toFixed(6)}&to=${to}`,
      { signal }
    );
    if (r.status === 503) return { status: "offline" };
    if (!r.ok) {
      const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
      return { status: "error", message: detail?.detail ?? `HTTP ${r.status}` };
    }
    return { status: "ok", data: (await r.json()) as RouteResult };
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return { status: "offline" };
  }
}
