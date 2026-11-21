import type { AnalyzeResponse } from "../types/api";
import { FactBadge, copyText, type PanelSelection } from "./common";
import { useToast } from "./Toast";
import { IconFile } from "./icons";

const CLINICIAN_SECTIONS = new Set(["examination", "assessment", "plan", "clinician_follow_up"]);

function noteText(result: AnalyzeResponse): string {
  const lines = ["DRAFT CLINICAL NOTE — clinician review required", ""];
  for (const sec of result.clinical_note.sections) {
    lines.push(sec.heading.toUpperCase());
    if (!sec.statements.length) lines.push(sec.empty_message);
    for (const s of sec.statements) lines.push(`- ${s.text}${s.fact_ids.length ? ` [${s.fact_ids.join(", ")}]` : ""}`);
    lines.push("");
  }
  return lines.join("\n");
}

export function ClinicalNoteView({
  result,
  onSelect,
  onShowCoverage,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: PanelSelection) => void;
  onShowCoverage: () => void;
}) {
  const factIndex = new Map(result.facts.map((f) => [f.fact_id, f]));
  const toast = useToast();
  const note = result.clinical_note;
  return (
    <section className="document">
      <div className="doc-toolbar">
        <div>
          <h2>Draft clinical note</h2>
          <p className="small muted">Generated from the transcript only. Clinician statements are documented as said, never added.</p>
        </div>
        <button type="button" className="btn btn-secondary btn-small"
                onClick={async () => toast((await copyText(noteText(result))) ? "Note copied to clipboard" : "Copy failed")}>
          <IconFile /> Copy note
        </button>
      </div>
      <div className="draft-ribbon">Draft — clinician review required</div>
      {note.sections.map((section) => {
        const clinician = CLINICIAN_SECTIONS.has(section.section_id);
        if (clinician && section.statements.length === 0) return null;
        return (
          <div key={section.section_id} className={`doc-section${clinician ? " doc-section-clinician" : ""}`}>
            <h3>{section.heading}</h3>
            {section.statements.length === 0 ? (
              <p className="muted small">{section.empty_message}</p>
            ) : (
              <ul className="doc-list">
                {section.statements.map((s) => (
                  <li key={s.statement_id} className={`doc-item${s.needs_review ? " doc-item-flag" : ""}`}>
                    <p>
                      {s.text}{" "}
                      {s.fact_ids.map((id) => (
                        <FactBadge key={id} factId={id} fact={factIndex.get(id)} onSelect={onSelect} />
                      ))}
                      {s.kind === "coverage_gap" && (
                        <button type="button" className="link small" onClick={onShowCoverage}>
                          Review
                        </button>
                      )}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </section>
  );
}
