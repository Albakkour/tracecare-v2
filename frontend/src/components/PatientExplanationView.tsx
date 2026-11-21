import { useEffect, useRef, useState } from "react";
import type { AnalyzeResponse } from "../types/api";
import { FactBadge, copyText, type PanelSelection } from "./common";
import { isClinician } from "./SummaryCards";
import { useToast } from "./Toast";
import { IconAlert, IconFile } from "./icons";

const ORDER = ["your_concern", "what_you_told", "findings", "assessment", "plan", "follow_up"];

export function PatientExplanationView({
  result,
  selectedStatementId,
  onSelect,
}: {
  result: AnalyzeResponse;
  selectedStatementId: string | null;
  onSelect: (sel: PanelSelection) => void;
}) {
  const pe = result.patient_explanation;
  const factIndex = new Map(result.facts.map((f) => [f.fact_id, f]));
  const [showSources, setShowSources] = useState(false);
  const toast = useToast();
  const selectedRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedStatementId]);

  const sections = ORDER.map((id) => ({ id, heading: pe.section_headings[id] ?? id, items: pe.statements.filter((s) => s.section === id) }))
    .filter((s) => s.items.length);

  return (
    <section className="document">
      <div className="doc-toolbar">
        <div>
          <h2>{pe.language === "sv" ? "Sammanfattning av besöket" : "After-visit summary"}</h2>
          <p className="small muted">{pe.intro}</p>
        </div>
        <div className="btn-row">
          <label className="toggle">
            <input type="checkbox" checked={showSources} onChange={(e) => setShowSources(e.target.checked)} />
            <span>Show sources</span>
          </label>
          <button
            type="button"
            className="btn btn-primary btn-small"
            onClick={async () => toast((await copyText(pe.plain_text)) ? "Summary copied to clipboard" : "Copy failed", "success")}
            disabled={!pe.plain_text}
          >
            <IconFile /> Copy summary
          </button>
        </div>
      </div>

      {sections.length === 0 && <p className="muted">No source-linked facts were available to summarise.</p>}
      {sections.map((sec) => (
        <div key={sec.id} className="doc-section">
          <h3>{sec.heading}</h3>
          <ul className="doc-list">
            {sec.items.map((s) => {
              const flagged = s.meaning_checks.length > 0;
              const selected = s.statement_id === selectedStatementId;
              return (
                <li
                  key={s.statement_id}
                  ref={selected ? selectedRef : undefined}
                  className={`doc-item${flagged ? " doc-item-flag" : ""}${selected ? " doc-item-selected" : ""}`}
                >
                  <p>
                    {s.text}
                    {flagged && (
                      <button type="button" className="flag-chip" onClick={() => onSelect({ kind: "statement", statementId: s.statement_id })}>
                        <IconAlert size={13} /> Check meaning
                      </button>
                    )}
                  </p>
                  {showSources && (
                    <div className="doc-sources">
                      {s.fact_ids.map((id) => {
                        const f = factIndex.get(id);
                        if (!f) return null;
                        return (
                          <div key={id} className="doc-source">
                            <FactBadge factId={id} fact={f} onSelect={onSelect} />
                            <span className="muted">{isClinician(f) ? "Doctor" : "You"}:</span> “{f.supporting_quote}”
                          </div>
                        );
                      })}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {pe.not_established.length > 0 && (
        <div className="doc-section">
          <h3>{pe.section_headings.not_established ?? "Not discussed in this conversation"}</h3>
          <p className="small muted">Not found in the transcript. This does not mean anything is wrong or absent.</p>
          <ul className="doc-list doc-list-plain">
            {pe.not_established.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="doc-disclaimer">{pe.disclaimer}</p>
    </section>
  );
}
