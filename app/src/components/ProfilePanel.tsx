import { useEffect, useState } from "react";
import type { Feature } from "geojson";
import { runQuery } from "../lib/duck";
import { fmtInt, fmtNum } from "../lib/format";
import type { Registry } from "../lib/registry";
import { fetchRoute, ROUTE_COLORS, type RouteResult, type RouteState, type RouteTarget } from "../lib/routing";
import { profileSql } from "../query/sql";
import { ClimateChart } from "./ClimateChart";
import { LocationForecast } from "./LocationForecast";
import type { ForecastMeta } from "../lib/forecasts";

interface Props {
  dataUrl: string;
  routingUrl: string;
  registry: Registry;
  forecasts: ForecastMeta | null;
  cellId: number;
  onRoutes(routes: Feature[] | null): void;
  onClose(): void;
}

type Row = Record<string, unknown>;

/** Țintele DESENATE pe hartă la click — o țintă nouă (ex. gări) = o intrare aici
 *  (+ variabila ei în pipeline și targetul în serviciul de rutare). */
const ROUTE_TARGETS: { target: RouteTarget; label: string; presentIf?: string }[] = [
  { target: "hospital", label: "Spital" },
  { target: "crossing", label: "Punct de trecere a frontierei", presentIf: "dist_crossing_km" },
  { target: "airport", label: "Aeroport", presentIf: "dist_airport_km" },
  { target: "sea", label: "Mare (Constanța)", presentIf: "dist_coast_km" },
];

// variabile de distanță „în linie dreaptă" care primesc și valoarea pe șosea (spre aceeași țintă)
const ROUTED_VARS: Record<string, RouteTarget> = {
  dist_coast_km: "sea",
  dist_crossing_km: "crossing",
  dist_airport_km: "airport",
};

/** Numele țintei atinse (pentru rândurile din secțiunea de trasee). */
function targetName(d: RouteResult): string {
  if (d.hospital) return d.hospital.city ? `${d.hospital.nume} · ${d.hospital.city}` : d.hospital.nume;
  if (d.crossing) {
    const w = d.crossing.waiting_time_min;
    return w != null ? `${d.crossing.name} (așteptare ~${w} min)` : d.crossing.name;
  }
  if (d.airport) return d.airport.label;
  if (d.sea) return d.sea.name;
  return "";
}

export function ProfilePanel({ dataUrl, routingUrl, registry, forecasts, cellId, onRoutes, onClose }: Props) {
  const [row, setRow] = useState<Row | null>(null);
  const [missing, setMissing] = useState(false);
  const [routes, setRoutes] = useState<Partial<Record<RouteTarget, RouteState>>>({});

  useEffect(() => {
    let alive = true;
    setRow(null);
    setMissing(false);
    runQuery(dataUrl, profileSql(cellId))
      .then((t) => {
        if (!alive) return;
        if (t.numRows === 0) setMissing(true);
        else setRow(t.get(0)!.toJSON() as Row);
      })
      .catch(() => {
        if (alive) setMissing(true);
      });
    return () => {
      alive = false;
    };
  }, [dataUrl, cellId]);

  // rute reale pe centroida celulei: țintele din ROUTE_TARGETS se desenează pe hartă
  useEffect(() => {
    setRoutes({});
    onRoutes(null);
    if (!row || row["lon"] == null) return;
    const ctrl = new AbortController();
    const lon = Number(row["lon"]);
    const lat = Number(row["lat"]);
    for (const spec of ROUTE_TARGETS) {
      if (spec.presentIf && row[spec.presentIf] == null) continue;
      setRoutes((prev) => ({ ...prev, [spec.target]: { status: "loading" } }));
      fetchRoute(routingUrl, lon, lat, spec.target, ctrl.signal)
        .then((st) => setRoutes((prev) => ({ ...prev, [spec.target]: st })))
        .catch(() => undefined);
    }
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row, routingUrl]);

  // traseele sosite până acum → pe hartă, fiecare cu culoarea lui
  useEffect(() => {
    const feats: Feature[] = [];
    for (const spec of ROUTE_TARGETS) {
      const st = routes[spec.target];
      if (st?.status === "ok" && st.data.route.geometry) {
        feats.push({
          ...st.data.route,
          properties: { ...(st.data.route.properties ?? {}), color: ROUTE_COLORS[spec.target], target: spec.target },
        });
      }
    }
    onRoutes(feats.length ? feats : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routes]);

  function routedText(varId: string): string | null {
    const target = ROUTED_VARS[varId];
    if (!target) return null;
    const st = routes[target];
    if (!st) return null;
    if (st.status === "loading") return "pe șosea: se calculează…";
    if (st.status === "ok") {
      const km = `${fmtNum(st.data.dist_km, 0)} km / ${fmtNum(st.data.drive_min, 0)} min`;
      // ținta cea mai rapidă pe șosea poate fi alta decât cea mai apropiată în linie dreaptă
      // (spitale/treceri); pentru „sea" numele e mereu Constanța — informația rămâne utilă
      const name = targetName(st.data);
      return name ? `cel mai rapid pe șosea: ${name} — ${km}` : `pe șosea: ${km}`;
    }
    return null; // offline/error: rămâne doar linia dreaptă
  }

  if (missing)
    return (
      <div className="profile">
        <PanelHead onClose={onClose} title="În afara grilei" subtitle="Celulă fără date" />
      </div>
    );
  if (!row)
    return (
      <div className="profile">
        <PanelHead onClose={onClose} title="Se încarcă…" subtitle="" />
      </div>
    );

  const uat = String(row["uat_name"] ?? "–");
  const county = String(row["county_name"] ?? "–");
  const countyMn = row["county_mn"] != null ? String(row["county_mn"]) : null;

  return (
    <div className="profile">
      <PanelHead
        onClose={onClose}
        title={`${uat} (${county})`}
        subtitle={`≈ ${fmtInt(Number(row["pop_total"]))} locuitori`}
      />
      <div className="profile-body">
        <RoutesSection routes={routes} />
        {forecasts && (
          <section>
            <h3>Prognoză meteo și calitatea aerului</h3>
            <LocationForecast dataUrl={dataUrl} meta={forecasts} cellId={cellId} />
          </section>
        )}
        {Object.entries(registry.groups).map(([gid, glabel]) => {
          const vars = registry.variables.filter(
            (v) => v.group === gid && v.role.includes("profile") && row[v.id] != null
          );
          if (vars.length === 0) return null;
          return (
            <section key={gid}>
              <h3>{glabel}</h3>
              <dl>
                {vars.map((v) => {
                  const raw = row[v.id];
                  let text: string;
                  if (v.dtype === "cat") text = String(raw);
                  else if (v.dtype === "int") text = fmtInt(Number(raw));
                  else text = fmtNum(Number(raw), v.decimals ?? 1);
                  const routed = routedText(v.id);
                  return (
                    <div key={v.id} title={v.note} className={routed ? "routed-row" : undefined}>
                      <dt>{v.label}</dt>
                      <dd>
                        {text}
                        {v.unit ? ` ${v.unit}` : ""}
                        {routed && <span className="routed-inline"> {routed}</span>}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </section>
          );
        })}
        {countyMn && (
          <section>
            <h3>Climă — județul {registry.countyLabels[countyMn] ?? countyMn}</h3>
            <ClimateChart dataUrl={dataUrl} countyMn={countyMn} climateYear={registry.climateYear} />
          </section>
        )}
      </div>
    </div>
  );
}

function RoutesSection({ routes }: { routes: Partial<Record<RouteTarget, RouteState>> }) {
  const entries = ROUTE_TARGETS.map((spec) => ({ spec, st: routes[spec.target] })).filter(
    (e) => e.st != null
  );
  if (entries.length === 0) return null;
  const allOffline = entries.every((e) => e.st!.status === "offline");
  return (
    <section className="route-section">
      <h3>Acces rutier — traseele sunt desenate pe hartă</h3>
      {allOffline ? (
        <p className="route-note">
          Serviciul de rutare nu rulează. Pornește-l cu{" "}
          <code>docker compose up -d routing-db routing-api</code> (+ importul, prima dată).
        </p>
      ) : (
        <div className="route-rows">
          {entries.map(({ spec, st }) => (
            <div key={spec.target} className="route-row">
              <span className="swatch" style={{ background: ROUTE_COLORS[spec.target] }} />
              <span className="route-row-label">{spec.label}</span>
              {st!.status === "loading" && <span className="route-row-val">se calculează…</span>}
              {st!.status === "error" && <span className="route-row-val">–</span>}
              {st!.status === "offline" && <span className="route-row-val">offline</span>}
              {st!.status === "ok" && (
                <span className="route-row-val">
                  <strong>{fmtNum(st!.data.drive_min, 0)} min</strong> · {fmtNum(st!.data.dist_km, 0)} km
                  <span className="route-row-name">{targetName(st!.data)}</span>
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function PanelHead({
  title,
  subtitle,
  onClose,
}: {
  title: string;
  subtitle: string;
  onClose(): void;
}) {
  return (
    <div className="profile-head">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <button className="remove" onClick={onClose} title="Închide">
        ×
      </button>
    </div>
  );
}
