import maplibregl from "maplibre-gl";
import type { Feature } from "geojson";
import { useEffect, useRef, type MutableRefObject } from "react";
import { cellRingLonLat, lonLatToCellId, type CellBitset, type GridSpec } from "../lib/grid";
import { createMaskRenderer, type MaskRenderer } from "../map/mask";
import type { WarnSelection } from "./WarningsPanel";
import type { WarnSource } from "../lib/warnings";

/** API imperativ minim al hărții — căutare, trasee rutiere, și citirea poziției pentru partajare. */
export interface MapApi {
  focusBounds(b: [number, number, number, number]): void;
  /** Desenează simultan mai multe trasee; fiecare feature are properties.color. */
  showRoutes(routes: Feature[] | null): void;
  getView(): { center: [number, number]; zoom: number };
}

interface Props {
  dataUrl: string;
  spec: GridSpec;
  bitset: CellBitset | null;
  cellValues: Float32Array | null;
  maskColor?: string;
  selectedCell: number | null;
  showWarnings: boolean;
  showHospitals: boolean;
  warnSelection: WarnSelection | null;
  initialView?: { center: [number, number]; zoom: number };
  mapApiRef: MutableRefObject<MapApi | null>;
  onCellClick(cellId: number | null): void;
}

const WARN_LAYERS = ["warn-general-fill", "warn-general-line", "warn-nowcast-fill", "warn-nowcast-line"];

/** Filtrul pentru stratul unei surse, ținând cont de selecția din panou (cumulat / cod / mesaj). */
function warnFilter(src: WarnSource, sel: WarnSelection | null): maplibregl.FilterSpecification {
  const base: maplibregl.FilterSpecification = ["==", ["get", "source"], src];
  if (!sel) return base;
  if (sel.source !== src) return ["==", ["get", "source"], "__none__"]; // ascunde cealaltă sursă
  if (sel.kind === "message") return ["all", base, ["==", ["get", "group_id"], sel.groupId]];
  return ["all", base, ["==", ["get", "level_code"], sel.code]];
}

export function MapView({
  dataUrl,
  spec,
  bitset,
  cellValues,
  maskColor,
  selectedCell,
  showWarnings,
  showHospitals,
  warnSelection,
  initialView,
  mapApiRef,
  onCellClick,
}: Props) {
  const initialViewRef = useRef(initialView);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const rendererRef = useRef<MaskRenderer | null>(null);
  const loadedRef = useRef(false);
  const bitsetRef = useRef<CellBitset | null>(null);
  bitsetRef.current = bitset;
  const cellValuesRef = useRef<Float32Array | null>(null);
  cellValuesRef.current = cellValues;
  const selectedCellRef = useRef(selectedCell);
  selectedCellRef.current = selectedCell;
  const maskColorRef = useRef(maskColor);
  maskColorRef.current = maskColor;
  const showWarningsRef = useRef(showWarnings);
  showWarningsRef.current = showWarnings;
  const showHospitalsRef = useRef(showHospitals);
  showHospitalsRef.current = showHospitals;
  const routesRef = useRef<Feature[] | null>(null);

  function paintCurrent() {
    const map = mapRef.current;
    const renderer = rendererRef.current;
    if (!map || !renderer || !loadedRef.current) return;
    renderer.paint(bitsetRef.current, cellValuesRef.current, maskColorRef.current);
    const src = map.getSource("mask") as maplibregl.CanvasSource | undefined;
    src?.play();
    src?.pause();
    map.triggerRepaint();
  }

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current!,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: initialViewRef.current?.center ?? [25, 45.9],
      zoom: initialViewRef.current?.zoom ?? 6,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    (window as unknown as { __map?: maplibregl.Map }).__map = map; // handle de depanare
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const mask = createMaskRenderer(spec);
    rendererRef.current = mask;

    map.on("load", () => {
      map.addSource("mask", {
        type: "canvas",
        canvas: mask.canvas,
        coordinates: mask.coordinates,
        animate: false,
      });
      map.addLayer({
        id: "mask",
        type: "raster",
        source: "mask",
        paint: { "raster-opacity": 0.72, "raster-resampling": "nearest" },
      });

      // avertizări: general (județ/zonă) discret dedesubt, nowcasting saturat deasupra
      map.addSource("warnings", { type: "geojson", data: `${dataUrl}/live/warnings.geojson` });
      map.addLayer({
        id: "warn-general-fill",
        type: "fill",
        source: "warnings",
        filter: warnFilter("general", warnSelection),
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.28 },
      });
      map.addLayer({
        id: "warn-general-line",
        type: "line",
        source: "warnings",
        filter: warnFilter("general", warnSelection),
        paint: { "line-color": ["get", "color"], "line-width": 0.8, "line-opacity": 0.6 },
      });
      map.addLayer({
        id: "warn-nowcast-fill",
        type: "fill",
        source: "warnings",
        filter: warnFilter("nowcasting", warnSelection),
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.45 },
      });
      map.addLayer({
        id: "warn-nowcast-line",
        type: "line",
        source: "warnings",
        filter: warnFilter("nowcasting", warnSelection),
        paint: { "line-color": ["get", "color"], "line-width": 1.6 },
      });

      // limite de referință, deasupra umplerilor
      map.addSource("counties", { type: "geojson", data: `${dataUrl}/county.geojson` });
      map.addLayer({
        id: "counties-line",
        type: "line",
        source: "counties",
        paint: { "line-color": "#5b6472", "line-width": 0.8, "line-opacity": 0.7 },
      });
      map.addSource("country", { type: "geojson", data: `${dataUrl}/country_line.geojson` });
      map.addLayer({
        id: "country-line",
        type: "line",
        source: "country",
        paint: { "line-color": "#2b3440", "line-width": 1.6, "line-opacity": 0.9 },
      });

      map.addSource("selected-cell", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "selected-cell",
        type: "line",
        source: "selected-cell",
        paint: { "line-color": "#0b62d6", "line-width": 2.5 },
      });

      // traseele rutiere din fișa celulei (spital, punct de trecere, aeroport…) —
      // culoarea vine din properties.color; contur alb pentru lizibilitate
      map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "route-casing",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 6, "line-opacity": 0.85 },
      });
      map.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 3.2 },
      });

      // spitalele (puncte) — vizibile la întrebările despre accesul la spital
      map.addSource("hospitals", { type: "geojson", data: `${dataUrl}/hospitals.geojson` });
      map.addLayer({
        id: "hospitals",
        type: "circle",
        source: "hospitals",
        layout: { visibility: showHospitalsRef.current ? "visible" : "none" },
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 2.4, 10, 5],
          "circle-color": "#0b62d6",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });

      // vizibilitatea inițială după mod: meteo XOR mască interogare
      const warn = showWarningsRef.current;
      for (const id of WARN_LAYERS) map.setLayoutProperty(id, "visibility", warn ? "visible" : "none");
      map.setLayoutProperty("mask", "visibility", warn ? "none" : "visible");

      loadedRef.current = true;
      paintCurrent();
      applyRoute();
      const selectedSource = map.getSource("selected-cell") as maplibregl.GeoJSONSource;
      selectedSource.setData(
        selectedCellRef.current == null
          ? { type: "FeatureCollection", features: [] }
          : {
              type: "Feature",
              properties: {},
              geometry: {
                type: "Polygon",
                coordinates: [cellRingLonLat(spec, selectedCellRef.current)],
              },
            }
      );
    });

    function applyRoute() {
      if (!loadedRef.current) return;
      const src = map.getSource("route") as maplibregl.GeoJSONSource | undefined;
      src?.setData({ type: "FeatureCollection", features: routesRef.current ?? [] });
    }

    // API pentru căutare: zbor la bbox + marcaj în centrul lui. Setat imediat (nu în `load`):
    // operațiile de cameră nu depind de stil, deci căutarea merge și cât încă se încarcă harta.
    const marker = new maplibregl.Marker({ color: "#0b62d6" });
    let markerAdded = false;
    mapApiRef.current = {
      focusBounds(b) {
        const bounds: [[number, number], [number, number]] = [[b[0], b[1]], [b[2], b[3]]];
        const opts = { padding: 70, maxZoom: 13 };
        const zBefore = map.getZoom();
        map.fitBounds(bounds, { ...opts, duration: 900 });
        // în medii cu rAF suspendat (tab de fundal, browser embedded) animația nu pompează —
        // dacă după 1s camera nu s-a mișcat, sărim direct
        window.setTimeout(() => {
          if (Math.abs(map.getZoom() - zBefore) < 0.01) map.fitBounds(bounds, { ...opts, duration: 0 });
        }, 1000);
        marker.setLngLat([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
        if (!markerAdded) {
          marker.addTo(map);
          markerAdded = true;
        }
      },
      showRoutes(routes) {
        routesRef.current = routes;
        applyRoute();
      },
      getView() {
        const c = map.getCenter();
        return { center: [c.lng, c.lat], zoom: map.getZoom() };
      },
    };

    map.on("click", (ev) => {
      const id = lonLatToCellId(spec, ev.lngLat.lng, ev.lngLat.lat);
      onCellClick(id);
    });
    map.getCanvas().style.cursor = "crosshair";

    // plasa de siguranță: în unele medii embedded containerul are 0×0 la construcție
    // și observer-ele de resize nu se declanșează — verificăm periodic divergența
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(containerRef.current!);
    const sizeCheck = window.setInterval(() => {
      const el = containerRef.current;
      if (!el || el.clientWidth === 0 || el.clientHeight === 0) return;
      const c = map.getCanvas();
      if (Math.abs(c.clientWidth - el.clientWidth) > 1 || Math.abs(c.clientHeight - el.clientHeight) > 1) {
        map.resize();
      }
    }, 500);

    return () => {
      window.clearInterval(sizeCheck);
      ro.disconnect();
      loadedRef.current = false;
      rendererRef.current = null;
      mapApiRef.current = null;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, dataUrl]);

  useEffect(() => {
    paintCurrent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bitset, cellValues, maskColor]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !map.getLayer("warn-general-fill")) return;
    for (const id of ["warn-general-fill", "warn-general-line"])
      map.setFilter(id, warnFilter("general", warnSelection));
    for (const id of ["warn-nowcast-fill", "warn-nowcast-line"])
      map.setFilter(id, warnFilter("nowcasting", warnSelection));
  }, [warnSelection]);

  // comută vizibilitatea la schimbarea modului: meteo XOR mască interogare
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !map.getLayer("mask")) return;
    for (const id of WARN_LAYERS)
      map.setLayoutProperty(id, "visibility", showWarnings ? "visible" : "none");
    map.setLayoutProperty("mask", "visibility", showWarnings ? "none" : "visible");
  }, [showWarnings]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !map.getLayer("hospitals")) return;
    map.setLayoutProperty("hospitals", "visibility", showHospitals ? "visible" : "none");
  }, [showHospitals]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const src = map.getSource("selected-cell") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData(
      selectedCell == null
        ? { type: "FeatureCollection", features: [] }
        : {
            type: "Feature",
            properties: {},
            geometry: { type: "Polygon", coordinates: [cellRingLonLat(spec, selectedCell)] },
          }
    );
  }, [selectedCell, spec]);

  return <div ref={containerRef} className="map" />;
}
