import { useEffect, useState } from "react";
import { marked } from "marked";

/** Overlay cu documentația proiectului, randată dintr-un fișier Markdown editabil
 * (public/documentatie.md). Conținutul e de încredere (versionat în repo), deci îl
 * randăm direct. */
export function DocsPanel({ onClose }: { onClose(): void }) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${import.meta.env.BASE_URL}documentatie.md`, { cache: "no-cache" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.text();
      })
      .then((md) => {
        if (alive) setHtml(marked.parse(md, { async: false }) as string);
      })
      .catch(() => {
        if (alive) setError(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="docs">
      <div className="dash-head">
        <h2>Documentație — metodă, surse și limitări</h2>
        <button className="remove" onClick={onClose} title="Închide documentația">
          ×
        </button>
      </div>
      <div className="docs-body">
        {error && <p className="docs-error">Documentația nu a putut fi încărcată.</p>}
        {!error && html == null && <p className="docs-loading">se încarcă…</p>}
        {html != null && (
          <article className="docs-md" dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </div>
    </div>
  );
}
