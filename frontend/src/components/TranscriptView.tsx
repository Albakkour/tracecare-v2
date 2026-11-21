import { useEffect, useRef } from "react";
import type { AnalyzeResponse } from "../types/api";
import { SpeakerChip, type PanelSelection } from "./common";

export function TranscriptView({
  result,
  focusSegmentId,
  onSelect,
}: {
  result: AnalyzeResponse;
  focusSegmentId: string | null;
  onSelect: (sel: PanelSelection) => void;
}) {
  const focusRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    focusRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusSegmentId]);

  const citing = new Map<string, string[]>();
  for (const f of result.facts) {
    for (const sid of f.source_segment_ids) citing.set(sid, [...(citing.get(sid) ?? []), f.fact_id]);
  }
  return (
    <section>
      {result.parse_warnings.length > 0 && (
        <div className="banner banner-warn">
          {result.parse_warnings.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}
      <div className="doc-toolbar">
        <div>
          <h2>Transcript</h2>
          <p className="small muted">
            {result.segments.length} turns. Badges show which facts were taken from each turn.
          </p>
        </div>
      </div>
      <ol className="transcript">
        {result.segments.map((s) => {
          const focused = s.segment_id === focusSegmentId;
          return (
            <li
              key={`${s.segment_id}-${focused ? focusSegmentId : ""}`}
              ref={focused ? focusRef : undefined}
              className={`turn turn-${s.speaker}${focused ? " turn-focus" : ""}`}
            >
              <div className="segment-head">
                <span className="seg-id">{s.segment_id}</span>
                <SpeakerChip speaker={s.speaker} label={s.speaker_label} />
                {(citing.get(s.segment_id) ?? []).map((id) => (
                  <button key={id} type="button" className="fact-badge" onClick={() => onSelect({ kind: "fact", factId: id })}>
                    {id}
                  </button>
                ))}
              </div>
              <p>{s.text}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
