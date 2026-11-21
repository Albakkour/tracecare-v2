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
    <section className="patient-banner" aria-label="Patient and encounter">
      <div className="patient-banner-inner">
        <div className="avatar" aria-hidden="true">
          {initials(p.display_name)}
        </div>
        <div className="patient-main">
          <div className="patient-line">
            <h1 className="patient-name">{p.display_name ?? "Unnamed patient"}</h1>
            <span className="mono patient-pnr" title="Temporary reserve-style number (letter T): never a real personnummer">
              {p.temp_personnummer ?? "No temporary ID"}
            </span>
            {p.temp_personnummer && <span className="badge badge-quiet">Temp ID</span>}
            <span className="badge badge-quiet">Synthetic</span>
          </div>
          <dl className="patient-facts">
            <div>
              <dt>Age</dt>
              <dd>{p.age !== null ? `${p.age} y` : "—"}</dd>
            </div>
            <div>
              <dt>Encounter</dt>
              <dd>{formatDateTime(result.created_at)}</dd>
            </div>
            <div>
              <dt>Engine</dt>
              <dd>{result.provider === "anthropic" ? result.model : "Demo (rule-based)"}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd className={reviewed ? "text-ok" : "text-attn"}>{reviewed ? "Coverage reviewed" : "Draft — needs clinician review"}</dd>
            </div>
            {p.name_source === "detected" && p.name_evidence && (
              <div>
                <dt>Name source</dt>
                <dd>
                  <button
                    type="button"
                    className="link"
                    onClick={() => onSelect({ kind: "evidence", title: "Patient name source", refs: [p.name_evidence!] })}
                  >
                    Detected in {p.name_evidence.segment_id}
                  </button>
                </dd>
              </div>
            )}
          </dl>
        </div>
        <div className="patient-actions">
          <button type="button" className="btn btn-secondary" onClick={onNewAnalysis}>
            <IconPlus /> New analysis
          </button>
          {result.persisted && (
            <button type="button" className="btn btn-ghost" onClick={onDelete} aria-label="Delete saved encounter">
              <IconTrash />
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
