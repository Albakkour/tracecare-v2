import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Language, ProviderName, PublicConfig, RecordExplainResponse, RecordSample } from "../types/api";
import { copyText } from "./common";
import { useToast } from "./Toast";
import { IconAlert, IconFile } from "./icons";

const RISK_LABEL = { high: "Check carefully", medium: "Compare", low: "OK" } as const;

export function RecordExplainer({ config, onBusy }: { config: PublicConfig | null; onBusy: (b: boolean) => void }) {
  const [samples, setSamples] = useState<RecordSample[]>([]);
  const [sampleId, setSampleId] = useState("");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [result, setResult] = useState<RecordExplainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const toast = useToast();
  const providers = config?.providers ?? [];

  useEffect(() => {
    api.recordSamples().then((r) => setSamples(r.records)).catch(() => setSamples([]));
  }, []);

  async function run() {
    setLoading(true);
    onBusy(true);
    setError(null);
    try {
      setResult(await api.explainRecord(text, language, provider || undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not explain the record.");
    } finally {
      setLoading(false);
      onBusy(false);
    }
  }

  const sentences = new Map(result?.sentences.map((s) => [s.sentence_id, s]) ?? []);
  const high = result?.statements.filter((s) => s.risk === "high").length ?? 0;
  const medium = result?.statements.filter((s) => s.risk === "medium").length ?? 0;
  const rows = result
    ? [
        ...result.statements.map((st) => ({ kind: "st" as const, order: result.sentences.findIndex((s) => s.sentence_id === st.source_sentence_ids[0]), st })),
        ...result.unexplained_sentence_ids.map((id) => ({ kind: "missing" as const, order: result.sentences.findIndex((s) => s.sentence_id === id), id })),
      ].sort((a, b) => a.order - b.order)
    : [];

  return (
    <div className="page fade-in">
      <header className="page-head">
        <h1>Record explainer</h1>
        <p className="muted">
          Paste a clinical note or medical record. Each sentence is rewritten in plain language, points back to the
          original, and is flagged where the meaning may have changed.
        </p>
      </header>

      <section className="card form-card">
        <div className="section-head">
          <h2>Record</h2>
          <div className="sample-picker">
            <label className="sr-only" htmlFor="record-sample">Sample record</label>
            <select id="record-sample" value={sampleId || samples[0]?.record_id || ""} onChange={(e) => setSampleId(e.target.value)}>
              {samples.map((s) => (
                <option key={s.record_id} value={s.record_id}>{s.title}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                const s = samples.find((x) => x.record_id === (sampleId || samples[0]?.record_id));
                if (s) setText(s.text);
              }}
            >
              Load sample
            </button>
          </div>
        </div>
        <label className="field">
          <span className="field-label">Clinical text</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} spellCheck={false} />
          <span className="field-help">Synthetic or role-played records only. Real personnummer are rejected.</span>
        </label>
        <div className="form-grid form-grid-3">
          <label className="field">
            <span className="field-label">Output language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
              <option value="en">English</option>
              <option value="sv">Svenska (needs Claude)</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Engine</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value as ProviderName | "")} disabled={providers.length < 2}>
              <option value="">Default ({config?.default_provider === "anthropic" ? "Claude" : "Demo"})</option>
              {providers.map((p) => (
                <option key={p} value={p}>{p === "anthropic" ? `Claude (${config?.model})` : "Demo — glossary only"}</option>
              ))}
            </select>
          </label>
          <div className="field field-end">
            <button type="button" className="btn btn-primary" disabled={loading || !text.trim()} onClick={run}>
              {loading ? <><span className="spinner" aria-hidden="true" /> Explaining…</> : "Explain record"}
            </button>
          </div>
        </div>
      </section>

      {error && <div className="banner banner-error" role="alert">{error}</div>}

      {result && (
        <section className="card fade-in">
          <div className="doc-toolbar">
            <div>
              <h2>Plain-language version</h2>
              <p className="small muted">
                {result.sentences.length} original sentences · <span className="text-danger">{high} check carefully</span> ·{" "}
                <span className="text-attn">{medium} compare</span>
                {result.unexplained_sentence_ids.length > 0 && <> · <span className="text-danger">{result.unexplained_sentence_ids.length} not explained</span></>}
                {" "}· {result.provider_label}
              </p>
            </div>
            <div className="btn-row">
              <label className="toggle">
                <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} />
                <span>Flagged only</span>
              </label>
              <button type="button" className="btn btn-primary btn-small"
                      onClick={async () => toast((await copyText(result.plain_text)) ? "Plain-language version copied" : "Copy failed")}>
                <IconFile /> Copy
              </button>
            </div>
          </div>
          {result.warnings.map((w) => (
            <p key={w} className="callout callout-warn"><IconAlert size={16} /><span>{w}</span></p>
          ))}
          <div className="record-grid" role="table" aria-label="Original and plain-language sentences">
            <div className="record-head" role="row">
              <span role="columnheader">Original</span>
              <span role="columnheader">Plain language</span>
            </div>
            {rows
              .filter((r) => !flaggedOnly || r.kind === "missing" || r.st.risk !== "low")
              .map((r) =>
                r.kind === "missing" ? (
                  <div key={r.id} className="record-row record-missing" role="row">
                    <div role="cell">
                      <span className="seg-id">{r.id}</span> {sentences.get(r.id)?.text}
                    </div>
                    <div role="cell" className="text-danger">No plain-language version — content may be missing.</div>
                  </div>
                ) : (
                  <div key={r.st.statement_id} className={`record-row record-${r.st.risk}`} role="row">
                    <div role="cell">
                      {sentences.get(r.st.source_sentence_ids[0])?.heading && (
                        <span className="record-heading">{sentences.get(r.st.source_sentence_ids[0])?.heading}</span>
                      )}
                      {r.st.source_sentence_ids.map((id) => (
                        <span key={id} className="record-src"><span className="seg-id">{id}</span> {sentences.get(id)?.text} </span>
                      ))}
                    </div>
                    <div role="cell">
                      <p className="record-plain">
                        {r.st.text}
                        {r.st.risk !== "low" && <span className={`risk risk-${r.st.risk}`}>{RISK_LABEL[r.st.risk]}</span>}
                      </p>
                      {r.st.meaning_checks.map((m, i) => (
                        <p key={i} className="small text-attn">{m.message}</p>
                      ))}
                      {r.st.terms_explained.length > 0 && (
                        <p className="small muted">Terms: {r.st.terms_explained.join(" · ")}</p>
                      )}
                    </div>
                  </div>
                ),
              )}
          </div>
          <p className="doc-disclaimer">{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
