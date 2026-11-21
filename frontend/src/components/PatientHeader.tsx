import type { AnalyzeResponse } from "../types/api";
import { formatDateTime, initials, type PanelSelection } from "./common";
import { IconPlus, IconTrash } from "./icons";

export function PatientHeader({
  result,
  onSelect,
  onNewAnalysis,
  onDelete,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: PanelSelection) => void;
  onNewAnalysis: () => void;
  onDelete: () => void;
}) {
  const p = result.patient;
  const reviewed = result.status === "reviewed";
  return (
    <section className="patient-header" aria-label="Patient and encounter">
      <div className="patient-id">
        <div className="avatar" aria-hidden="true">
          {initials(p.display_name)}
        </div>
        <div>
          <h1 className="patient-name">
            {p.display_name ?? "Unnamed patient"}
            <span className="tag tag-neutral">Synthetic</span>
          </h1>
          <dl className="patient-meta">
            <div>
              <dt>Temp. personnummer</dt>
              <dd className="mono">
                {p.temp_personnummer ?? "—"}
                {p.temp_personnummer && (
                  <span className="tag tag-temp" title="Temporary reserve-style number (letter T): never a real personnummer">
                    TEMP
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>Age</dt>
              <dd>{p.age !== null ? `${p.age} years` : "—"}</dd>
            </div>
            <div>
              <dt>Encounter</dt>
              <dd>{formatDateTime(result.created_at)}</dd>
            </div>
            <div>
              <dt>Analysed by</dt>
              <dd>{result.provider === "anthropic" ? `Claude (${result.model})` : "Demo (rule-based)"}</dd>
            </div>
          </dl>
          {p.name_source === "detected" && p.name_evidence && (
            <p className="small muted">
              Name detected from the transcript —{" "}
              <button
                type="button"
                className="link"
                onClick={() =>
                  onSelect({ kind: "evidence", title: "Patient name source", refs: [p.name_evidence!] })
                }
              >
                show source ({p.name_evidence.segment_id})
              </button>
            </p>
          )}
        </div>
      </div>
      <div className="patient-actions">
        <span className={`tag ${reviewed ? "tag-ok" : "tag-review"}`}>
          {reviewed ? "Coverage reviewed" : "Draft · clinician review required"}
        </span>
        <div className="btn-row">
          <button type="button" className="btn btn-secondary" onClick={onNewAnalysis}>
            <IconPlus /> New analysis
          </button>
          {result.persisted && (
            <button type="button" className="btn btn-ghost" onClick={onDelete} aria-label="Delete saved encounter">
              <IconTrash /> Delete
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
