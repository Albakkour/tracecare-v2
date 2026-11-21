import type { AnalyzeResponse } from "../types/api";
import { FactBadge, type EvidenceSelection } from "./common";

export function PatientExplanationView({
  result,
  onSelect,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: EvidenceSelection) => void;
}) {
  const pe = result.patient_explanation;
  const factIndex = new Map(result.facts.map((f) => [f.fact_id, f]));
  return (
    <section>
      <div className="banner banner-info">{pe.disclaimer}</div>
      <p className="lead">{pe.intro}</p>
      {pe.statements.length === 0 ? (
        <p className="muted">No source-linked facts were available to explain.</p>
      ) : (
        <div className="side-by-side">
          <div className="sbs-head">Plain language</div>
          <div className="sbs-head">Original words in the transcript</div>
          {pe.statements.map((s) => {
            const facts = s.fact_ids.map((id) => factIndex.get(id)).filter(Boolean);
            return (
              <div key={s.statement_id} className={`sbs-row${s.needs_review ? " needs-review" : ""}`}>
                <div>
                  <p>
                    {s.text}{" "}
                    {s.fact_ids.map((id) => (
                      <FactBadge key={id} factId={id} fact={factIndex.get(id)} onSelect={onSelect} />
                    ))}
                  </p>
                  {s.meaning_checks.length > 0 && (
                    <div className="meaning-flag">
                      <strong>Meaning may have changed — please review:</strong>
                      <ul>
                        {s.meaning_checks.map((m, i) => (
                          <li key={i}>{m.message}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                <div className="sbs-source">
                  {facts.map((f) => (
                    <button
                      key={f!.fact_id}
                      type="button"
                      className="quote-button"
                      onClick={() => onSelect({ kind: "fact", factId: f!.fact_id })}
                    >
                      <span className="seg-id">{f!.source_segment_ids.join(", ")}</span> “{f!.supporting_quote}”
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {pe.not_established.length > 0 && (
        <div className="not-established">
          <h4>Not established in this conversation</h4>
          <p className="small muted">
            These topics were not found in the transcript. This does not mean anything is wrong or absent.
          </p>
          <ul>
            {pe.not_established.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
