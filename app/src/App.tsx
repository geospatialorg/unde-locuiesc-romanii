import { useCallback, useEffect, useRef, useState } from "react";
import { CellBitset, loadGridSpec, type GridSpec } from "./lib/grid";
import { runQuery } from "./lib/duck";
import { loadRegistry, type Registry } from "./lib/registry";
import type { QueryResult, QueryState } from "./query/model";
import { PRESETS } from "./query/presets";
import { aggregateSql, cellValuesSql } from "./query/sql";
import { MapView, type MapApi } from "./components/MapView";
import { Sidebar } from "./components/Sidebar";
import { ProfilePanel } from "./components/ProfilePanel";
import { DensityLegend } from "./components/DensityLegend";
import { WarningsLegend } from "./components/WarningsLegend";
import { ForecastLegend } from "./components/ForecastLegend";
import { Dashboard } from "./components/Dashboard";
import { SearchBox } from "./components/SearchBox";
import { hasAnyWarnings, loadWarnings, type WarningsMeta } from "./lib/warnings";
import type { WarnSelection } from "./components/WarningsPanel";
import { buildShareUrl, readShareFromUrl, type ShareState } from "./lib/urlstate";
import {
  activeForecastProducts,
  DEFAULT_FORECAST_SELECTION,
  forecastAggregateSql,
  forecastCellValuesSql,
  forecastDays,
  loadForecasts,
  sourceAvailable,
  type AppMode,
  type ForecastMeta,
  type ForecastSelection,
} from "./lib/forecasts";

const ROUTING_URL =
  (import.meta.env.VITE_ROUTING_URL as string | undefined) ?? "http://localhost:8091";

// starea partajată din URL (dacă există) — citită o singură dată, la pornire
const SHARED = readShareFromUrl();

export function App({ dataUrl }: { dataUrl: string }) {
  const routingUrl = ROUTING_URL;
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [spec, setSpec] = useState<GridSpec | null>(null);
  const [error, setError] = useState<string | null>(null);

  // modul comută între avertizări meteo și întrebările clasice; pornim pe meteo, dar dacă la
  // încărcare nu există avertizări active (și utilizatorul n-a ales încă), trecem pe o întrebare normală
  const [mode, setMode] = useState<AppMode>(SHARED?.mode ?? "warnings");
  const [query, setQuery] = useState<QueryState>(SHARED?.query ?? PRESETS[0].query);
  const [activePreset, setActivePreset] = useState<string | null>(
    SHARED ? SHARED.preset : PRESETS[0].id
  );
  const [result, setResult] = useState<QueryResult | null>(null);
  const [bitset, setBitset] = useState<CellBitset | null>(null);
  const [cellValues, setCellValues] = useState<Float32Array | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedCell, setSelectedCell] = useState<number | null>(SHARED?.cell ?? null);
  const [warnings, setWarnings] = useState<WarningsMeta | null>(null);
  const [warnSelection, setWarnSelection] = useState<WarnSelection | null>(SHARED?.warn ?? null);
  const [forecasts, setForecasts] = useState<ForecastMeta | null>(null);
  const [forecastSelection, setForecastSelection] = useState<ForecastSelection>(
    SHARED?.forecast ?? DEFAULT_FORECAST_SELECTION
  );
  const [forecastQueryError, setForecastQueryError] = useState<string | null>(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);

  const queryEpoch = useRef(0);
  const userInteracted = useRef(!!SHARED); // un link partajat = alegere explicită de mod
  const mapApi = useRef<MapApi | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("theme");
    if (saved) return saved === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    Promise.all([loadRegistry(dataUrl), loadGridSpec(dataUrl)])
      .then(([reg, gs]) => {
        setRegistry(reg);
        setSpec(gs);
      })
      .catch((e) => setError(`Nu pot încărca datele (${e}). Rulează pipeline-ul și serverul de date.`));
    loadWarnings(dataUrl).then((w) => {
      setWarnings(w);
      if (!hasAnyWarnings(w) && !userInteracted.current) setMode("query");
    });
    let alive = true;
    const refreshForecasts = () => loadForecasts(dataUrl).then((next) => {
      if (!alive || !next) return;
      setForecasts((current) => current?.generated_utc === next.generated_utc ? current : next);
    });
    refreshForecasts();
    const forecastTimer = window.setInterval(refreshForecasts, 15 * 60 * 1000);
    return () => {
      alive = false;
      window.clearInterval(forecastTimer);
    };
  }, [dataUrl]);

  // rulează interogarea curentă (agregat + lista de celule pentru mască) — doar în modul „query"
  useEffect(() => {
    if (!registry || !spec || mode !== "query") return;
    const epoch = ++queryEpoch.current;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const agg = await runQuery(dataUrl, aggregateSql(registry, query));
        const cells = await runQuery(dataUrl, cellValuesSql(registry, query));
        if (epoch !== queryEpoch.current) return; // interogare abandonată
        const row = agg.get(0);
        const value = Number(row?.value ?? 0);
        const nCells = Number(row?.n_cells ?? 0);
        const cellIds = cells.getChild("cell_id")!.toArray() as Uint32Array;
        const vals = cells.getChild("val")!.toArray() as Float64Array;
        // vector plin pe grilă: valoarea măsurii per celulă potrivită (1 km² → densitate/km²)
        const values = new Float32Array(spec.ncols * spec.nrows);
        for (let i = 0; i < cellIds.length; i++) values[cellIds[i]] = vals[i];
        const national = registry.national[query.measure] ?? 1;
        const res: QueryResult = { value, nCells, pctOfNational: value / national, cellIds };
        setResult(res);
        setBitset(CellBitset.fromIds(spec.ncols * spec.nrows, cellIds));
        setCellValues(values);
      } catch (e) {
        console.error(e);
        setError(`Interogarea a eșuat: ${e}`);
      } finally {
        if (epoch === queryEpoch.current) setBusy(false);
      }
    }, 250);
    return () => {
      clearTimeout(t);
      queryEpoch.current++;
    };
  }, [dataUrl, registry, spec, query, mode]);

  useEffect(() => {
    if (!registry || !spec || mode !== "forecast") return;
    const epoch = ++queryEpoch.current;
    setResult(null);
    setBitset(null);
    setCellValues(null);
    if (!forecasts) {
      setBusy(false);
      return;
    }
    const product = forecasts.products[forecastSelection.productId];
    const source = product && forecasts.sources[product.source];
    if (!product || !source || !sourceAvailable(source)) {
      setResult(null);
      setBitset(null);
      setCellValues(null);
      setBusy(false);
      setForecastQueryError(null);
      return;
    }

    setBusy(true);
    setForecastQueryError(null);
    let aggregateSql: string;
    let cellsSql: string;
    try {
      aggregateSql = forecastAggregateSql(dataUrl, forecasts, forecastSelection);
      cellsSql = forecastCellValuesSql(dataUrl, forecasts, forecastSelection);
    } catch (cause) {
      console.error(cause);
      setBusy(false);
      setForecastQueryError("Selecția prognozei nu este validă pentru datele curente.");
      return;
    }
    Promise.all([
      runQuery(dataUrl, aggregateSql),
      runQuery(dataUrl, cellsSql),
    ])
      .then(([aggregate, cells]) => {
        if (epoch !== queryEpoch.current) return;
        const row = aggregate.get(0);
        const value = Number(row?.value ?? 0);
        const nCells = Number(row?.n_cells ?? 0);
        const cellIds = cells.getChild("cell_id")!.toArray() as Uint32Array;
        const vals = cells.getChild("val")!.toArray() as Float64Array;
        const values = new Float32Array(spec.ncols * spec.nrows);
        for (let i = 0; i < cellIds.length; i++) values[cellIds[i]] = vals[i];
        const national = registry.national[forecastSelection.measure] ?? 1;
        setResult({ value, nCells, pctOfNational: value / national, cellIds });
        setBitset(CellBitset.fromIds(spec.ncols * spec.nrows, cellIds));
        setCellValues(values);
      })
      .catch((cause) => {
        if (epoch !== queryEpoch.current) return;
        console.error(cause);
        setResult(null);
        setBitset(null);
        setCellValues(null);
        setForecastQueryError("Prognoza nu a putut fi interogată. Reîncercați după actualizarea datelor.");
      })
      .finally(() => {
        if (epoch === queryEpoch.current) setBusy(false);
      });
    return () => {
      queryEpoch.current++;
    };
  }, [dataUrl, registry, spec, forecasts, forecastSelection, mode]);

  useEffect(() => {
    if (!forecasts || !forecastSelection.date) return;
    const product = forecasts.products[forecastSelection.productId];
    if (!forecastDays(forecasts.sources[product.source]).includes(forecastSelection.date)) {
      setForecastSelection((selection) => ({ ...selection, date: null }));
    }
  }, [forecasts, forecastSelection.productId, forecastSelection.date]);

  // dacă produsul selectat nu mai e relevant pentru prognoza curentă (ex. „ger" vara),
  // trece automat la primul produs activ
  useEffect(() => {
    if (!forecasts) return;
    const active = activeForecastProducts(forecasts);
    if (active.length && !active.includes(forecastSelection.productId)) {
      setForecastSelection((selection) => ({ ...selection, productId: active[0], date: null }));
    }
  }, [forecasts, forecastSelection.productId]);

  const onQueryChange = useCallback((q: QueryState, presetId: string | null) => {
    userInteracted.current = true;
    setMode("query");
    setQuery(q);
    setActivePreset(presetId);
    setResult(null);
    setBitset(null);
    setCellValues(null);
    setForecastQueryError(null);
  }, []);

  const onSelectWarnings = useCallback(() => {
    userInteracted.current = true;
    setMode("warnings");
  }, []);

  const onSelectForecast = useCallback((productId: ForecastSelection["productId"]) => {
    userInteracted.current = true;
    setMode("forecast");
    setForecastSelection((selection) => ({ ...selection, productId, date: null }));
    setResult(null);
    setBitset(null);
    setCellValues(null);
    setForecastQueryError(null);
  }, []);

  // curăță filtrele/măsura venite dintr-un link, față de registrul curent (variabile redenumite/scoase)
  useEffect(() => {
    if (!registry) return;
    setQuery((q) => {
      const known = (id: string) => registry.variables.some((v) => v.id === id);
      const constraints = q.constraints.filter((c) => known(c.varId));
      const measure = registry.measures.some((m) => m.id === q.measure) ? q.measure : "pop_total";
      if (constraints.length === q.constraints.length && measure === q.measure) return q;
      return { measure, constraints };
    });
    setForecastSelection((selection) => ({
      ...selection,
      measure: registry.measures.some((measure) => measure.id === selection.measure)
        ? selection.measure
        : "pop_total",
    }));
  }, [registry]);

  const onShare = useCallback((): string => {
    const s: ShareState = {
      mode,
      query,
      preset: activePreset,
      warn: warnSelection,
      forecast: forecastSelection,
      view: mapApi.current?.getView(),
      cell: selectedCell,
    };
    return buildShareUrl(s);
  }, [mode, query, activePreset, warnSelection, forecastSelection, selectedCell]);

  if (error) return <div className="fatal">{error}</div>;
  if (!registry || !spec) return <div className="fatal">Se încarcă…</div>;

  return (
    <div className="app">
      <button className="sidebar-toggle" onClick={() => setDrawerOpen((v) => !v)} title="Meniu">
        ☰
      </button>
      {drawerOpen && <div className="drawer-backdrop active" onClick={() => setDrawerOpen(false)} />}
      <Sidebar
        registry={registry}
        mode={mode}
        query={query}
        activePreset={activePreset}
        result={result}
        busy={busy}
        forecastQueryError={forecastQueryError}
        onQueryChange={onQueryChange}
        onSelectWarnings={onSelectWarnings}
        warnings={warnings}
        warnSelection={warnSelection}
        onSelectWarning={setWarnSelection}
        forecasts={forecasts}
        forecastSelection={forecastSelection}
        onSelectForecast={onSelectForecast}
        onForecastChange={setForecastSelection}
        dashboardOpen={dashboardOpen}
        onToggleDashboard={() => setDashboardOpen((v) => !v)}
        onShare={onShare}
        dataUrl={dataUrl}
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((v) => !v)}
      />
      <div className="map-wrap">
        <MapView
          dataUrl={dataUrl}
          spec={spec}
          bitset={bitset}
          cellValues={cellValues}
          selectedCell={selectedCell}
          showWarnings={mode === "warnings"}
          showHospitals={
            mode === "query" && query.constraints.some((c) => c.varId === "dist_hospital_km")
          }
          warnSelection={warnSelection}
          initialView={SHARED?.view}
          mapApiRef={mapApi}
          onCellClick={setSelectedCell}
        />
        <SearchBox dataUrl={dataUrl} onPick={(e) => mapApi.current?.focusBounds(e.b)} />
        {mode === "query" && result && (
          <DensityLegend registry={registry} measure={query.measure} />
        )}
        {mode === "warnings" && hasAnyWarnings(warnings) && warnings && (
          <WarningsLegend meta={warnings} />
        )}
        {mode === "forecast" && forecasts && registry && (
          <div className="legend-stack">
            <ForecastLegend meta={forecasts} selection={forecastSelection} />
            <DensityLegend registry={registry} measure={forecastSelection.measure} />
          </div>
        )}
        {selectedCell != null && !dashboardOpen && (
          <ProfilePanel
            dataUrl={dataUrl}
            routingUrl={routingUrl}
            registry={registry}
            forecasts={forecasts}
            cellId={selectedCell}
            onRoutes={(r) => mapApi.current?.showRoutes(r)}
            onClose={() => {
              mapApi.current?.showRoutes(null);
              setSelectedCell(null);
            }}
          />
        )}
        {dashboardOpen && (
          <Dashboard
            dataUrl={dataUrl}
            registry={registry}
            query={query}
            onClose={() => setDashboardOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
