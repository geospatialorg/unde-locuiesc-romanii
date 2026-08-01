import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { runQuery } from "../lib/duck";
import { countyAnnualSql, countyDailySql } from "../query/sql";

type Period = "current" | "history";

const TOOLTIP_SERIES = [
  { label: "T max", color: "#d6452b", unit: "°C" },
  { label: "T min", color: "#2b6bd6", unit: "°C" },
  { label: "Precip", color: "#2b9950", unit: "mm" },
];

function tooltipPlugin(period: Period): uPlot.Plugin {
  let tooltip: HTMLDivElement | null = null;
  let title: HTMLDivElement | null = null;
  const valueNodes: HTMLSpanElement[] = [];

  return {
    hooks: {
      ready: (plot) => {
        tooltip = document.createElement("div");
        tooltip.className = "climate-tooltip";
        title = document.createElement("div");
        title.className = "climate-tooltip-title";
        tooltip.append(title);

        for (const series of TOOLTIP_SERIES) {
          const row = document.createElement("div");
          row.className = "climate-tooltip-row";
          const key = document.createElement("span");
          key.className = "climate-tooltip-key";
          const swatch = document.createElement("i");
          swatch.style.background = series.color;
          key.append(swatch, series.label);
          const value = document.createElement("span");
          value.className = "climate-tooltip-value";
          valueNodes.push(value);
          row.append(key, value);
          tooltip.append(row);
        }
        document.body.append(tooltip);
        plot.root.setAttribute("aria-label", "Grafic climatic interactiv");
      },
      setCursor: (plot) => {
        const { idx, left, top } = plot.cursor;
        if (!tooltip || !title || idx == null || left == null || top == null || left < 0 || top < 0) {
          if (tooltip) tooltip.style.visibility = "hidden";
          return;
        }

        const timestamp = Number(plot.data[0][idx]);
        const date = new Date(timestamp * 1000);
        title.textContent = period === "history"
          ? String(date.getUTCFullYear())
          : date.toLocaleDateString("ro-RO", {
              day: "numeric",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            });

        for (let i = 0; i < TOOLTIP_SERIES.length; i++) {
          const value = Number(plot.data[i + 1][idx]);
          valueNodes[i].textContent = Number.isFinite(value)
            ? `${value.toLocaleString("ro-RO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${TOOLTIP_SERIES[i].unit}`
            : "–";
        }

        const pointerX = plot.rect.left + left;
        const pointerY = plot.rect.top + top;
        const x = Math.max(8, Math.min(pointerX + 12, window.innerWidth - tooltip.offsetWidth - 8));
        let y = pointerY + 12;
        if (y + tooltip.offsetHeight > window.innerHeight - 8) {
          y = Math.max(8, pointerY - tooltip.offsetHeight - 12);
        }
        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
        tooltip.style.visibility = "visible";
      },
      destroy: () => {
        tooltip?.remove();
        tooltip = null;
        title = null;
        valueNodes.length = 0;
      },
    },
  };
}

export function ClimateChart({
  dataUrl,
  countyMn,
  climateYear,
}: {
  dataUrl: string;
  countyMn: string;
  climateYear: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);
  const [period, setPeriod] = useState<Period>("current");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setFailed(false);
    const sql = period === "current" ? countyDailySql(countyMn) : countyAnnualSql(countyMn);
    runQuery(dataUrl, sql)
      .then((t) => {
        if (disposed || !ref.current) return;
        const n = t.numRows;
        const xs = new Float64Array(n);
        const tmin = new Float64Array(n);
        const tmax = new Float64Array(n);
        const precip = new Float64Array(n);
        for (let i = 0; i < n; i++) {
          const r = t.get(i)!;
          const d = r["date"];
          xs[i] = (d instanceof Date ? d.getTime() : Number(d)) / 1000;
          tmin[i] = Number(r["tmin"]);
          tmax[i] = Number(r["tmax"]);
          precip[i] = Number(r["precip"]);
        }
        plotRef.current?.destroy();
        plotRef.current = new uPlot(
          {
            width: ref.current.clientWidth,
            height: 180,
            series: [
              {},
              {
                label: period === "current" ? "T max" : "T max medie",
                stroke: "#d6452b",
                width: 1,
                scale: "temp",
              },
              {
                label: period === "current" ? "T min" : "T min medie",
                stroke: "#2b6bd6",
                width: 1,
                scale: "temp",
              },
              {
                label: period === "current" ? "Precip" : "Precip medie",
                stroke: "#2b9950",
                width: 1,
                scale: "mm",
              },
            ],
            axes: [
              {},
              { scale: "temp", label: "°C" },
              { scale: "mm", side: 1, label: "mm/zi", grid: { show: false } },
            ],
            scales: { temp: {}, mm: { range: (_u, _min, max) => [0, Math.max(max, 5)] } },
            legend: { live: false },
            plugins: [tooltipPlugin(period)],
          },
          [xs, tmax, tmin, precip] as unknown as uPlot.AlignedData,
          ref.current
        );
        setLoading(false);
      })
      .catch(() => {
        if (disposed) return;
        plotRef.current?.destroy();
        plotRef.current = null;
        setLoading(false);
        setFailed(true);
      });
    return () => {
      disposed = true;
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [dataUrl, countyMn, period]);

  return (
    <div className="climate-chart">
      <div className="climate-period" role="group" aria-label="Perioada graficului climatic">
        <button
          type="button"
          className={period === "current" ? "active" : undefined}
          aria-pressed={period === "current"}
          onClick={() => setPeriod("current")}
        >
          {climateYear} · zilnic
        </button>
        <button
          type="button"
          className={period === "history" ? "active" : undefined}
          aria-pressed={period === "history"}
          onClick={() => setPeriod("history")}
        >
          1961–{climateYear} · anual
        </button>
      </div>
      <div className="chart-host">
        <div ref={ref} className="chart" />
        {loading && <span className="chart-status">Se încarcă…</span>}
        {failed && <span className="chart-status">Datele climatice nu au putut fi încărcate.</span>}
      </div>
      {period === "history" && (
        <p className="climate-note">{climateYear} este un an parțial; mediile includ zilele disponibile.</p>
      )}
    </div>
  );
}
