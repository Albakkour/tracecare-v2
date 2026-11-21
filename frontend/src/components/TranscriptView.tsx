import type { AnalyzeResponse } from "../types/api";
import { SpeakerChip, type EvidenceSelection } from "./common";

export function TranscriptView({
  result,
  onSelect,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: EvidenceSelection) => void;
}) {
  const citing = new Map<string, string[]>();
  for (const f of result.facts) {
    for (const sid of f.source_segment_ids) citing.set(sid, [...(citing.get(sid) ?? []), f.fact_id]);
  }
  const findings = result.validation_findings;
  return (
    <section>
      {result.parse_warnings.length > 0 && (
        <div className="banner banner-warn">
          {result.parse_warnings.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}
      <h3>Validation findings ({findings.length})</h3>
      {findings.length === 0 ? (
        <p className="muted">No validation issues were recorded.</p>
      ) : (
        <ul className="findings">
          {findings.map((f, i) => (
            <li key={i} className={`finding finding-${f.severity}`}>
              <span className="tag">{f.severity}</span> <code>{f.code}</code>
              {f.ref_id && <span className="muted"> · {f.ref_id}</span>} — {f.message}
            </li>
          ))}
        </ul>
      )}
      <h3>Segmented transcript ({result.segments.length} segments)</h3>
      <ol className="transcript">
        {result.segments.map((s) => (
          <li key={s.segment_id} className={`turn turn-${s.speaker}`}>
            <div className="segment-head">
              <span className="seg-id">{s.segment_id}</span>
              <SpeakerChip speaker={s.speaker} label={s.speaker_label} />
              {(citing.get(s.segment_id) ?? []).map((id) => (
                <button key={id} type="button" className="fact-badge" onClick={() => onSelect({ kind: "fact", factId: id })}>
                  [{id}]
                </button>
              ))}
            </div>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
