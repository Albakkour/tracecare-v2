import type { AnalyzeResponse } from "../types/api";
import { FactBadge, type EvidenceSelection } from "./common";

export function ClinicalNoteView({
  result,
  onSelect,
  onShowCoverage,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: EvidenceSelection) => void;
  onShowCoverage: () => void;
}) {
  const factIndex = new Map(result.facts.map((f) => [f.fact_id, f]));
  const note = result.clinical_note;
  return (
    <section>
      <div className="banner banner-draft">
        <strong>Draft — clinician review required.</strong> {note.disclaimer.replace(/^Draft — clinician review required\.\s*/, "")}
      </div>
      {note.sections.map((section) => (
        <div key={section.section_id} className="note-section">
          <h3>{section.heading}</h3>
          {section.statements.length === 0 ? (
            <p className="muted">{section.empty_message}</p>
          ) : (
            <ul className="statements">
              {section.statements.map((s) => (
                <li key={s.statement_id} className={s.needs_review ? "needs-review" : undefined}>
                  <span>{s.text}</span>{" "}
                  {s.fact_ids.map((id) => (
                    <FactBadge key={id} factId={id} fact={factIndex.get(id)} onSelect={onSelect} />
                  ))}
                  {s.kind === "coverage_gap" && (
                    <button type="button" className="link small" onClick={onShowCoverage}>
                      see coverage
                    </button>
                  )}
                  {s.needs_review && <span className="tag tag-review">Needs review</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}
