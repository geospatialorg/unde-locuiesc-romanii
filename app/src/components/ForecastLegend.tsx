import type { ForecastMeta, ForecastSelection } from "../lib/forecasts";

export function ForecastLegend({ meta, selection }: { meta: ForecastMeta; selection: ForecastSelection }) {
  const product = meta.products[selection.productId];
  const threshold = selection.productId === "air_poor"
    ? "calitate slabă sau mai rea (AQI european)"
    : `${product.operator} ${product.threshold} ${product.unit}`;
  return (
    <div className="forecast-legend">
      <div className="forecast-legend-title">{product.label}</div>
      <div className="forecast-legend-row">{threshold}</div>
      <div className="forecast-legend-note">
        {selection.date ?? "cel puțin o zi din perioada disponibilă"}
      </div>
    </div>
  );
}
