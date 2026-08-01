import { useRef, useState } from "react";
import { loadGazetteer, searchGazetteer, type GazEntry } from "../lib/gazetteer";

interface Props {
  dataUrl: string;
  onPick(e: GazEntry): void;
}

/** Căutare UAT + localități, cu potrivire fără diacritice; indexul se încarcă la primul focus. */
export function SearchBox({ dataUrl, onPick }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<GazEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const entriesRef = useRef<GazEntry[] | null>(null);

  async function ensureIndex(): Promise<GazEntry[]> {
    entriesRef.current ??= await loadGazetteer(dataUrl);
    return entriesRef.current;
  }

  async function update(value: string) {
    setQ(value);
    const entries = await ensureIndex();
    const h = searchGazetteer(entries, value);
    setHits(h);
    setSel(0);
    setOpen(h.length > 0);
  }

  function pick(e: GazEntry) {
    setQ(`${e.n} (${e.j})`);
    setOpen(false);
    onPick(e);
  }

  function onKeyDown(ev: React.KeyboardEvent) {
    if (!open) return;
    if (ev.key === "ArrowDown") {
      ev.preventDefault();
      setSel((s) => Math.min(s + 1, hits.length - 1));
    } else if (ev.key === "ArrowUp") {
      ev.preventDefault();
      setSel((s) => Math.max(s - 1, 0));
    } else if (ev.key === "Enter" && hits[sel]) {
      ev.preventDefault();
      pick(hits[sel]);
    } else if (ev.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="search-box">
      <input
        type="search"
        placeholder="Caută UAT sau localitate…"
        value={q}
        onChange={(e) => void update(e.target.value)}
        onFocus={() => {
          void ensureIndex();
          if (hits.length > 0) setOpen(true);
        }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        aria-label="Caută UAT sau localitate"
      />
      {open && (
        <ul className="search-hits" role="listbox">
          {hits.map((h, i) => (
            <li
              key={`${h.k}-${h.n}-${h.j}-${i}`}
              role="option"
              aria-selected={i === sel}
              className={i === sel ? "sel" : ""}
              onMouseDown={(ev) => {
                ev.preventDefault();
                pick(h);
              }}
              onMouseEnter={() => setSel(i)}
            >
              <span className="hit-name">{h.n}</span>
              <span className={"hit-kind" + (h.k === "u" ? " uat" : "")}>{h.t}</span>
              <span className="hit-county">{h.j}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
