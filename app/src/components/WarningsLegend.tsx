import { levelsPresent, type WarningsMeta } from "../lib/warnings";

/** Legenda codurilor de severitate afișate pe hartă în modul meteo. */
export function WarningsLegend({ meta }: { meta: WarningsMeta }) {
  const levels = levelsPresent(meta);
  if (levels.length === 0) return null;
  return (
    <div className="warn-legend">
      <div className="warn-legend-title">Coduri de avertizare</div>
      <div className="warn-legend-rows">
        {levels.map((l) => (
          <span key={l.code} className="warn-legend-row">
            <span className="swatch" style={{ background: l.color }} /> Cod {l.name.toLowerCase()}
          </span>
        ))}
      </div>
      <div className="warn-legend-note">
        Un buletin poate cuprinde zone la coduri diferite; fiecare zonă e colorată după codul ei.
      </div>
    </div>
  );
}
