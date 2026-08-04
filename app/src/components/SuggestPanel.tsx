import { useState, type FormEvent } from "react";

// Cheie publică Web3Forms (safe în client — permite doar trimiterea către emailul asociat).
// Dacă lipsește, formularul cade elegant pe mailto. Se setează ca Variable GitHub la build.
const WEB3FORMS_KEY = (import.meta.env.VITE_WEB3FORMS_KEY as string | undefined)?.trim() ?? "";
const CONTACT_EMAIL = "contact@geo-spatial.org";
const SUBJECT = "Propunere de întrebare — Unde locuiesc românii?";

export function SuggestPanel({ onClose }: { onClose(): void }) {
  const [question, setQuestion] = useState("");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;

    // fără cheie de formular → deschidem clientul de email al utilizatorului
    if (!WEB3FORMS_KEY) {
      const body = encodeURIComponent(q + (email ? `\n\n— ${email}` : ""));
      window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(SUBJECT)}&body=${body}`;
      setState("ok");
      return;
    }

    setState("sending");
    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          access_key: WEB3FORMS_KEY,
          subject: SUBJECT,
          from_name: "Unde locuiesc românii?",
          intrebare: q,
          email_contact: email || "(nespecificat)",
          botcheck: "", // honeypot — completat de boți, respins de Web3Forms
        }),
      });
      setState(res.ok ? "ok" : "error");
      if (res.ok) setQuestion("");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="docs suggest">
      <div className="dash-head">
        <h2>💡 Propune o întrebare</h2>
        <button className="remove" onClick={onClose} title="Închide">
          ×
        </button>
      </div>
      <div className="docs-body">
        {state === "ok" ? (
          <p className="suggest-ok">
            Mulțumim! Propunerea ta a plecat spre noi. 🎉 Promitem să ne uităm la toate ideile.
          </p>
        ) : (
          <form className="suggest-form" onSubmit={submit}>
            <p>
              Ce întrebare ai vrea să poți pune despre unde locuiesc românii? Scrie-o cu cuvintele
              tale — ne ajută să prioritizăm ce adăugăm.
            </p>
            <label>
              <span>Întrebarea ta</span>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                required
                placeholder="Ex.: Câți români locuiesc în zone cu risc de alunecări de teren?"
              />
            </label>
            <label>
              <span>Email (opțional, dacă vrei un răspuns)</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nume@exemplu.ro"
              />
            </label>
            {/* honeypot anti-spam (ascuns pentru oameni) */}
            <input type="text" name="botcheck" tabIndex={-1} autoComplete="off" aria-hidden="true"
              style={{ position: "absolute", left: "-9999px" }} />
            <button type="submit" className="suggest-submit" disabled={state === "sending"}>
              {state === "sending" ? "se trimite…" : "Trimite propunerea"}
            </button>
            {state === "error" && (
              <p className="suggest-err">
                Nu am putut trimite acum. Scrie-ne direct la{" "}
                <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
              </p>
            )}
            <p className="suggest-alt">
              Sau scrie-ne oricând direct la <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
