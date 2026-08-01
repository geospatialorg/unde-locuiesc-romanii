import { DENSITY_STOPS } from "../map/mask";
import type { Registry } from "../lib/registry";

/** Legenda densității — gradientul e generat din aceleași opriri ca LUT-ul măștii. */
export function DensityLegend({ registry, measure }: { registry: Registry; measure: string }) {
  const label = registry.measures.find((m) => m.id === measure)?.label ?? "persoane";
  const gradient = `linear-gradient(to right, ${DENSITY_STOPS.map(
    ([r, g, b]) => `rgb(${r},${g},${b})`
  ).join(", ")})`;

  return (
    <div className="density-legend">
      <div className="density-title">{label} pe km²</div>
      <div className="density-bar" style={{ background: gradient }} />
      <div className="density-ticks">
        <span>1</span>
        <span>100</span>
        <span>≥10.000</span>
      </div>
      <div className="density-empty">
        <span className="density-empty-swatch" /> zonă potrivită, nelocuită
      </div>
    </div>
  );
}
