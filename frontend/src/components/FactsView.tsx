import type { AnalyzeResponse, MedicalFact } from "../types/api";
import { FactBadge, truncate, type EvidenceSelection } from "./common";

function FactTable({ facts, onSelect }: { facts: MedicalFact[]; onSelect: (sel: EvidenceSelection) => void }) {
  return (
    <div className="table-wrap">
      <table className="facts-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Category</th>
            <th>Fact</th>
            <th>Polarity</th>
            <th>Certainty</th>
            <th>Source</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {facts.map((f) => (
            <tr key={f.fact_id} className={f.evidence_status !== "source_linked" ? "row-review" : undefined}>
              <td>
                <FactBadge factId={f.fact_id} fact={f} onSelect={onSelect} />
              </td>
              <td>{f.category}</td>
              <td>
                {f.normalized_value}
                {[f.duration, f.frequency, f.severity, f.location].some(Boolean) && (
                  <div className="small muted">
                    {[f.duration && `duration: ${f.duration}`, f.frequency && `frequency: ${f.frequency}`,
                      f.severity && `severity: ${f.severity}`, f.location && `location: ${f.location}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
              </td>
              <td className={`polarity polarity-${f.polarity}`}>{f.polarity}</td>
              <td>{f.certainty}</td>
              <td>
                <span className="seg-id">{f.source_segment_ids.join(", ")}</span>
                <div className="small">“{truncate(f.supporting_quote, 90)}”</div>
              </td>
              <td>
                {f.evidence_status === "source_linked" && <span className="tag tag-ok">Source-linked</span>}
                {f.evidence_status === "needs_review" && <span className="tag tag-review">Needs review</span>}
                {f.evidence_status === "rejected" && <span className="tag tag-rejected">Rejected</span>}
                {f.review_notes.map((n, i) => (
                  <div key={i} className="small muted">
                    {n}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FactsView({ result, onSelect }: { result: AnalyzeResponse; onSelect: (sel: EvidenceSelection) => void }) {
  return (
    <section>
      <p className="muted">
        Atomic facts proposed by the provider and checked by TraceCare: every segment ID and quote was validated against
        the transcript. “Source-linked” means the quote exists in the cited segment — not that the interpretation is
        clinically verified.
      </p>
      {result.facts.length === 0 ? <p className="muted">No facts were extracted.</p> : <FactTable facts={result.facts} onSelect={onSelect} />}
      {result.symptoms.length > 0 && (
        <>
          <h3>Patient-mentioned symptoms</h3>
          <ul className="symptom-list">
            {result.symptoms.map((s) => (
              <li key={s.symptom_id}>
                <strong>{s.concept}</strong> <span className={`polarity polarity-${s.polarity}`}>({s.polarity})</span>
                {s.template_id ? (
                  <span className="small"> → template <code>{s.template_id}</code></span>
                ) : (
                  <span className="small muted"> → no configured template</span>
                )}{" "}
                {s.fact_ids.map((id) => (
                  <FactBadge key={id} factId={id} onSelect={onSelect} />
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
      {result.rejected_facts.length > 0 && (
        <>
          <h3>Rejected by validation (not used in any output)</h3>
          <FactTable facts={result.rejected_facts} onSelect={onSelect} />
        </>
      )}
    </section>
  );
}
