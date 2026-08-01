import { useEffect, useState } from "react";
import { runQuery } from "../lib/duck";
import { fmtInt, fmtPct } from "../lib/format";
import type { Registry } from "../lib/registry";
import {
  byLevelSql,
  byMessageSql,
  combinedTotalSql,
  hasAnyWarnings,
  type WarnSource,
  type WarningMessage,
  type WarningsMeta,
} from "../lib/warnings";

export type WarnSelection =
  | { kind: "level"; source: WarnSource; code: string }
  | { kind: "message"; source: WarnSource; groupId: string };

interface Props {
  dataUrl: string;
  registry: Registry;
  meta: WarningsMeta;
  selection: WarnSelection | null;
  onSelect(sel: WarnSelection | null): void;
}

interface LevelPop {
  pop: number;
  nCells: number;
}
type PopBySource = Record<WarnSource, Map<string, LevelPop>>;

const SOURCE_LABEL: Record<WarnSource, string> = {
  nowcasting: "Nowcasting (imediate, ore)",
  general: "Atenționări / avertizări (intervale lungi)",
};

const isLevel = (s: WarnSelection | null, src: WarnSource, code: string) =>
  s?.kind === "level" && s.source === src && s.code === code;
const isMsg = (s: WarnSelection | null, gid: string) =>
  s?.kind === "message" && s.groupId === gid;

export function WarningsPanel({ dataUrl, registry, meta, selection, onSelect }: Props) {
  const [measure, setMeasure] = useState("pop_total");
  const [pop, setPop] = useState<PopBySource | null>(null);
  const [combined, setCombined] = useState<number | null>(null);
  const [msgPop, setMsgPop] = useState<Map<string, number>>(new Map());
  const [openSource, setOpenSource] = useState<WarnSource | null>("general");

  useEffect(() => {
    let alive = true;
    setPop(null);
    setCombined(null);
    Promise.all([
      runQuery(dataUrl, byLevelSql(dataUrl, measure)),
      runQuery(dataUrl, combinedTotalSql(dataUrl, measure)),
      runQuery(dataUrl, byMessageSql(dataUrl, measure)),
    ])
      .then(([lv, tot, msg]) => {
        if (!alive) return;
        const acc: PopBySource = { nowcasting: new Map(), general: new Map() };
        for (let i = 0; i < lv.numRows; i++) {
          const r = lv.get(i)!;
          const src = String(r["source"]) as WarnSource;
          acc[src]?.set(String(r["level_code"]), {
            pop: Number(r["pop"]),
            nCells: Number(r["n_cells"]),
          });
        }
        setPop(acc);
        setCombined(Number(tot.get(0)?.["pop"] ?? 0));
        const mp = new Map<string, number>();
        for (let i = 0; i < msg.numRows; i++) {
          const r = msg.get(i)!;
          mp.set(String(r["group_id"]), Number(r["pop"]));
        }
        setMsgPop(mp);
      })
      .catch(() => {
        setPop({ nowcasting: new Map(), general: new Map() });
        setCombined(0);
      });
    return () => {
      alive = false;
    };
  }, [dataUrl, measure, meta]);

  const national = registry.national[measure] ?? 1;
  const measureLabel = registry.measures.find((m) => m.id === measure)?.label ?? "persoane";
  const genLocal = new Date(meta.generated_utc).toLocaleString("ro-RO", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  });

  if (!hasAnyWarnings(meta))
    return (
      <section className="warn-panel none">
        <p className="warn-empty">Nu sunt avertizări meteo active în acest moment.</p>
        <p className="warn-gen">actualizat {genLocal} · MeteoRomania</p>
      </section>
    );

  const selMsg =
    selection?.kind === "message"
      ? [...meta.sources.nowcasting.messages, ...meta.sources.general.messages].find(
          (m) => m.group_id === selection.groupId
        )
      : null;
  const distinctPop = selMsg ? msgPop.get(selMsg.group_id) ?? selMsg.affected_pop : null;

  return (
    <section className="warn-panel">
      <div className="warn-total-row">
        <div>
          <div className="warn-total" onClick={() => onSelect(null)} title="Vezi cumulat">
            {selMsg
              ? distinctPop == null
                ? "…"
                : fmtInt(distinctPop)
              : combined == null
                ? "…"
                : fmtInt(combined)}
          </div>
          <div className="warn-total-sub">
            {selMsg ? (
              <>
                {measureLabel} · doar mesajul selectat ·{" "}
                {distinctPop == null ? "" : fmtPct(distinctPop / national)} din total
              </>
            ) : (
              <>
                {measureLabel} sub cel puțin o avertizare ·{" "}
                {combined == null ? "" : fmtPct(combined / national)} din total
              </>
            )}
          </div>
        </div>
        <select value={measure} onChange={(e) => setMeasure(e.target.value)} title="Măsura">
          {registry.measures.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {selection && (
        <button className="warn-clear" onClick={() => onSelect(null)}>
          ✕ afișează cumulat (toate mesajele)
        </button>
      )}

      {(["nowcasting", "general"] as WarnSource[]).map((src) => (
        <SourceBlock
          key={src}
          src={src}
          meta={meta}
          pop={pop?.[src] ?? null}
          msgPop={msgPop}
          selection={selection}
          onSelect={onSelect}
          open={openSource === src}
          onToggleOpen={() => setOpenSource(openSource === src ? null : src)}
        />
      ))}

      <p className="warn-gen">
        actualizat {genLocal} · surse: MeteoRomania (nowcasting + atenționări/avertizări)
      </p>
    </section>
  );
}

function SourceBlock({
  src,
  meta,
  pop,
  msgPop,
  selection,
  onSelect,
  open,
  onToggleOpen,
}: {
  src: WarnSource;
  meta: WarningsMeta;
  pop: Map<string, LevelPop> | null;
  msgPop: Map<string, number>;
  selection: WarnSelection | null;
  onSelect(sel: WarnSelection | null): void;
  open: boolean;
  onToggleOpen(): void;
}) {
  const s = meta.sources[src];
  if (s.n_messages === 0)
    return (
      <div className="warn-source empty">
        <div className="warn-source-title">{SOURCE_LABEL[src]}</div>
        <div className="warn-source-none">niciun mesaj activ</div>
      </div>
    );

  return (
    <div className="warn-source">
      <div className="warn-source-title">{SOURCE_LABEL[src]}</div>

      <div className="warn-levels">
        {s.levels.map((l) => {
          const live = pop?.get(l.code);
          const active = isLevel(selection, src, l.code);
          const dimmed = selection && !active;
          return (
            <button
              key={l.code}
              className={"warn-level" + (active ? " active" : "") + (dimmed ? " dim" : "")}
              onClick={() => onSelect(active ? null : { kind: "level", source: src, code: l.code })}
              title="Filtrează pe acest cod de severitate"
            >
              <span className="swatch" style={{ background: l.color }} />
              <span className="warn-level-name">Cod {l.name.toLowerCase()}</span>
              <span className="warn-level-pop">{fmtInt(live ? live.pop : l.pop)}</span>
            </button>
          );
        })}
      </div>

      <button className="warn-toggle" onClick={onToggleOpen}>
        {open ? "ascunde" : "vezi distinct"}{" "}
        {s.n_messages === 1 ? "mesajul" : `cele ${s.n_messages} mesaje`}
      </button>
      {open && (
        <ul className="warn-list">
          {s.messages.map((m) => (
            <MessageRow
              key={m.group_id}
              m={m}
              livePop={msgPop.get(m.group_id)}
              selected={isMsg(selection, m.group_id)}
              dimmed={!!selection && !isMsg(selection, m.group_id)}
              onClick={() =>
                onSelect(
                  isMsg(selection, m.group_id)
                    ? null
                    : { kind: "message", source: src, groupId: m.group_id }
                )
              }
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageRow({
  m,
  livePop,
  selected,
  dimmed,
  onClick,
}: {
  m: WarningMessage;
  livePop: number | undefined;
  selected: boolean;
  dimmed: boolean;
  onClick(): void;
}) {
  const when =
    m.source === "nowcasting"
      ? m.start && m.end
        ? `${m.start.slice(11)}–${m.end.slice(11)}`
        : ""
      : m.interval ?? "";
  const scope =
    m.source === "general" && m.counties
      ? `${m.counties.length} județe${m.n_zones ? ` + ${m.n_zones} zone` : ""}`
      : m.area_text;
  return (
    <li
      className={"warn-item" + (selected ? " selected" : "") + (dimmed ? " dim" : "")}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="warn-item-head">
        <span className="swatch" style={{ background: m.color }} />
        <strong>Cod {m.level_name.toLowerCase()}</strong>
        <span className="warn-item-time">{when}</span>
      </div>
      <div className="warn-item-phen">
        {m.kind}: {m.phenomenon}
      </div>
      <div className="warn-item-area">{scope}</div>
      {m.level_mix && m.level_mix.length > 1 && (
        <div className="warn-item-mix">
          acoperă zone la coduri diferite:{" "}
          {m.level_mix.map((x, i) => (
            <span key={x.code} className="mix-chip">
              <span className="swatch sm" style={{ background: x.color }} />
              {x.n} cod {x.name.toLowerCase()}
              {i < m.level_mix!.length - 1 ? " · " : ""}
            </span>
          ))}
        </div>
      )}
      <div className="warn-item-pop">
        ≈ {fmtInt(livePop ?? m.affected_pop)} persoane · {m.entity}
      </div>
    </li>
  );
}
