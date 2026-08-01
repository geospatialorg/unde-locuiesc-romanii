import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { fmtInt } from "../lib/format";

interface Props {
  centers: number[];
  seriesA: number[];
  seriesB?: number[] | null;
  labelA: string;
  labelB?: string;
  unit?: string;
  measureLabel: string;
  pct?: boolean; // seriile sunt normalizate la procente din fiecare arie
}

function tooltipPlugin(
  labelA: string,
  labelB: string | undefined,
  unit: string | undefined,
  measureLabel: string,
  pct: boolean | undefined,
  hasSeriesB: boolean
): uPlot.Plugin {
  let tooltip: HTMLDivElement | null = null;
  let title: HTMLDivElement | null = null;
  const valueNodes: HTMLSpanElement[] = [];
  const rows = [
    { label: labelA, color: "#d6452b" },
    ...(hasSeriesB ? [{ label: labelB ?? "B", color: "#0b62d6" }] : []),
  ];

  return {
    hooks: {
      ready: (plot) => {
        tooltip = document.createElement("div");
        tooltip.className = "analysis-tooltip";
        title = document.createElement("div");
        title.className = "analysis-tooltip-title";
        tooltip.append(title);

        for (const series of rows) {
          const row = document.createElement("div");
          row.className = "analysis-tooltip-row";
          const key = document.createElement("span");
          key.className = "analysis-tooltip-key";
          const swatch = document.createElement("i");
          swatch.style.background = series.color;
          key.append(swatch, series.label);
          const value = document.createElement("span");
          value.className = "analysis-tooltip-value";
          valueNodes.push(value);
          row.append(key, value);
          tooltip.append(row);
        }
        document.body.append(tooltip);
        plot.root.setAttribute("aria-label", "Histogramă interactivă");
      },
      setCursor: (plot) => {
        const { idx, left, top } = plot.cursor;
        if (!tooltip || !title || idx == null || left == null || top == null || left < 0 || top < 0) {
          if (tooltip) tooltip.style.visibility = "hidden";
          return;
        }

        const center = Number(plot.data[0][idx]);
        title.textContent = `${center.toLocaleString("ro-RO", { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ""}`;
        for (let i = 0; i < rows.length; i++) {
          const value = Number(plot.data[i + 1][idx]);
          valueNodes[i].textContent = pct
            ? `${value.toLocaleString("ro-RO", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
            : `${fmtInt(value)} ${measureLabel}`;
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

/** Histogramă cu bare (uPlot): populația pe intervale ale variabilei; A roșu, B albastru. */
export function HistChart({ centers, seriesA, seriesB, labelA, labelB, unit, measureLabel, pct }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || centers.length === 0) return;

    const data: uPlot.AlignedData = seriesB
      ? [centers, seriesA, seriesB]
      : [centers, seriesA];

    const bars = uPlot.paths.bars!({ size: [0.85, 100] });
    const mk = (label: string, stroke: string, fill: string): uPlot.Series => ({
      label,
      stroke,
      fill,
      width: 1,
      paths: bars,
      points: { show: false },
    });
    const series: uPlot.Series[] = [
      {},
      mk(labelA, "#d6452b", "rgba(214,69,43,0.55)"),
    ];
    if (seriesB) series.push(mk(labelB ?? "B", "#0b62d6", "rgba(11,98,214,0.45)"));

    plotRef.current?.destroy();
    plotRef.current = new uPlot(
      {
        width: el.clientWidth,
        height: 220,
        series,
        scales: { x: { time: false } },
        axes: [
          { label: unit },
          {
            size: 64,
            values: (_u, ticks) => ticks.map((t) => (t >= 1e6 ? `${(t / 1e6).toFixed(1)}M` : t >= 1e3 ? `${Math.round(t / 1e3)}k` : String(t))),
          },
        ],
        legend: { live: false, show: !!seriesB },
        cursor: {
          points: { show: false },
        },
        plugins: [tooltipPlugin(labelA, labelB, unit, measureLabel, pct, !!seriesB)],
      },
      data,
      el
    );
    return () => {
      plotRef.current?.destroy();
      plotRef.current = null;
    };
  }, [centers, seriesA, seriesB, labelA, labelB, unit, measureLabel, pct]);

  if (centers.length === 0) return <p className="dash-note">fără date pentru acest interval</p>;
  return (
    <div>
      <div ref={ref} className="chart" />
      <p className="dash-axis-note">
        pe orizontală: valoarea variabilei{unit ? ` (${unit})` : ""} · pe verticală:{" "}
        {pct
          ? "procentul din populația fiecărei arii care trăiește la acea valoare"
          : `câte persoane trăiesc la acea valoare (total: ${fmtInt(seriesA.reduce((s, x) => s + x, 0))})`}
      </p>
    </div>
  );
}
