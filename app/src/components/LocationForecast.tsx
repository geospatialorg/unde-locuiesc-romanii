import { useEffect, useState } from "react";
import { runQuery } from "../lib/duck";
import { fmtNum } from "../lib/format";
import { locationForecastSql, type ForecastMeta } from "../lib/forecasts";

interface ForecastRow {
  day: string;
  tmin?: number;
  tmax?: number;
  aqiRank?: number;
  pollutants?: string;
}

const AQI_LABELS = ["Bună", "Acceptabilă", "Moderată", "Slabă", "Foarte slabă", "Extrem de slabă"];

function dayLabel(day: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("ro-RO", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function LocationForecast({
  dataUrl,
  meta,
  cellId,
}: {
  dataUrl: string;
  meta: ForecastMeta;
  cellId: number;
}) {
  const [rows, setRows] = useState<ForecastRow[] | null>(null);

  useEffect(() => {
    let alive = true;
    setRows(null);
    const weatherSql = locationForecastSql(dataUrl, meta, "weather", cellId);
    const airSql = locationForecastSql(dataUrl, meta, "air", cellId);
    Promise.allSettled([
      weatherSql ? runQuery(dataUrl, weatherSql) : Promise.resolve(null),
      airSql ? runQuery(dataUrl, airSql) : Promise.resolve(null),
    ])
      .then(([weatherResult, airResult]) => {
        if (!alive) return;
        const weather = weatherResult.status === "fulfilled" ? weatherResult.value : null;
        const air = airResult.status === "fulfilled" ? airResult.value : null;
        const byDay = new Map<string, ForecastRow>();
        if (weather) {
          for (let i = 0; i < weather.numRows; i++) {
            const row = weather.get(i)!;
            const day = String(row["day"]);
            byDay.set(day, { day, tmin: Number(row["tmin"]), tmax: Number(row["tmax"]) });
          }
        }
        if (air) {
          for (let i = 0; i < air.numRows; i++) {
            const row = air.get(i)!;
            const day = String(row["day"]);
            const item = byDay.get(day) ?? { day };
            item.aqiRank = Number(row["aqi_rank"]);
            item.pollutants = [
              `PM2.5 ${fmtNum(Number(row["pm25_max"]), 0)}`,
              `PM10 ${fmtNum(Number(row["pm10_max"]), 0)}`,
              `NO₂ ${fmtNum(Number(row["no2_max"]), 0)}`,
              `O₃ ${fmtNum(Number(row["o3_max"]), 0)}`,
              `SO₂ ${fmtNum(Number(row["so2_max"]), 0)} µg/m³`,
            ].join(" · ");
            byDay.set(day, item);
          }
        }
        setRows([...byDay.values()].sort((a, b) => a.day.localeCompare(b.day)));
      })
      .catch(() => {
        if (alive) setRows([]);
      });
    return () => {
      alive = false;
    };
  }, [dataUrl, meta, cellId]);

  if (rows == null) return <p className="location-forecast-note">Se încarcă prognoza…</p>;
  if (rows.length === 0) return <p className="location-forecast-note">Prognoza nu este disponibilă.</p>;

  return (
    <div className="location-forecast">
      <div className="location-forecast-head">
        <span>Zi</span><span>ECMWF min / max</span><span>CAMS aer</span>
      </div>
      {rows.map((row) => (
        <div className="location-forecast-row" key={row.day}>
          <strong>{dayLabel(row.day)}</strong>
          <span>{row.tmin != null && row.tmax != null ? `${fmtNum(row.tmin, 1)} / ${fmtNum(row.tmax, 1)} °C` : "–"}</span>
          <div className="location-air-cell">
            {row.aqiRank != null ? (
              <details className="location-air-detail">
                <summary>{AQI_LABELS[row.aqiRank] ?? "–"}</summary>
                <span>{row.pollutants}</span>
              </details>
            ) : "–"}
          </div>
        </div>
      ))}
      <p className="location-forecast-note">
        Aer: categoria PM folosește media mobilă de 24 h; deschide categoria pentru maximele pe poluanți.
      </p>
    </div>
  );
}
