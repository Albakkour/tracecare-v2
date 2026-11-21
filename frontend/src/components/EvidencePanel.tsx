import { useEffect, useState } from "react";
import type {
  AnalyzeResponse,
  ChecklistTemplate,
  CoverageItemUpdate,
  EvidenceReference,
  ItemStatus,
  TranscriptSegment,
} from "../types/api";
import { STATUS_HELP, STATUS_LABELS, STATUS_ORDER, SpeakerChip, StatusBadge, type PanelSelection } from "./common";
import { IconCheck, IconX } from "./icons";

function HighlightedSegment({ segment, refs }: { segment: TranscriptSegment; refs: EvidenceReference[] }) {
  const ref = refs.find((r) => r.segment_id === segment.segment_id && r.start_char !== null && r.end_char !== null);
  if (!ref || ref.start_char === null || ref.end_char === null) return <span>{segment.text}</span>;
  const start = ref.start_char - segment.start_char;
  const end = ref.end_char - segment.start_char;
  return (
    <span>
      {segment.text.slice(0, start)}
      <mark>{segment.text.slice(start, end)}</mark>
      {segment.text.slice(end)}
    </span>
  );
}

function SegmentCard({
  segment,
  refs,
  dim,
  total,
  onJump,
}: {
  segment: TranscriptSegment;
  refs: EvidenceReference[];
  dim?: boolean;
  total?: number;
  onJump?: (segmentId: string) => void;
}) {
  return (
    <div className={`segment-card${dim ? " segment-dim" : ""}`}>
      <div className="segment-head">
        <span className="seg-id">{segment.segment_id}</span>
        <SpeakerChip speaker={segment.speaker} label={segment.speaker_label} />
        {dim ? (
          <span className="small muted">context</span>
        ) : (
          total && <span className="small muted">turn {segment.turn_index} of {total}</span>
        )}
        {!dim && onJump && (
          <button type="button" className="link small push-right" onClick={() => onJump(segment.segment_id)}>
            Show in transcript
          </button>
        )}
      </div>
      <p className="segment-text">
        <HighlightedSegment segment={segment} refs={refs} />
      </p>
    </div>
  );
}

let jumpHandler: ((segmentId: string) => void) | undefined;

function SegmentsWithContext({
  result,
  segmentIds,
  refs,
}: {
  result: AnalyzeResponse;
  segmentIds: string[];
  refs: EvidenceReference[];
}) {
  const index = new Map(result.segments.map((s, i) => [s.segment_id, i]));
  const shown = new Set<string>();
  const cards: React.ReactNode[] = [];
  for (const sid of segmentIds) {
    const i = index.get(sid);
    if (i === undefined) {
      cards.push(
        <div key={`missing-${sid}`} className="segment-card segment-missing">
          Segment {sid} does not exist in this transcript.
        </div>,
      );
      continue;
    }
    const prev = result.segments[i - 1];
    if (prev && !shown.has(prev.segment_id) && !segmentIds.includes(prev.segment_id)) {
      shown.add(prev.segment_id);
      cards.push(<SegmentCard key={`ctx-${prev.segment_id}`} segment={prev} refs={[]} dim />);
    }
    if (!shown.has(sid)) {
      shown.add(sid);
      cards.push(<SegmentCard key={sid} segment={result.segments[i]} refs={refs} total={result.segments.length} onJump={jumpHandler} />);
    }
  }
  return <>{cards}</>;
}

const DISCLAIMER = "A matching quote shows the text exists in the transcript. It does not verify the clinical interpretation.";

function PanelHead({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="panel-head">
      <h2>{title}</h2>
      <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">
        <IconX />
      </button>
    </div>
  );
}

function ReviewForm({
  result,
  templates,
  templateId,
  itemId,
  onUpdate,
  onClose,
}: {
  result: AnalyzeResponse;
  templates: ChecklistTemplate[];
  templateId: string;
  itemId: string;
  onUpdate: (templateId: string, itemId: string, update: CoverageItemUpdate) => Promise<void>;
  onClose: () => void;
}) {
  const report = result.coverage_reports.find((r) => r.template_id === templateId);
  const item = report?.items.find((i) => i.item_id === itemId);
  const definition = templates.find((t) => t.template_id === templateId)?.items.find((i) => i.item_id === itemId);
  const [status, setStatus] = useState<ItemStatus>(item?.status ?? "not_found_in_transcript");
  const [reason, setReason] = useState(item?.not_applicable_reason ?? "");
  const [note, setNote] = useState(item?.reviewer_note ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStatus(item?.status ?? "not_found_in_transcript");
    setReason(item?.not_applicable_reason ?? "");
    setNote(item?.reviewer_note ?? "");
    setState("idle");
    // Reset only when switching to another item.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId, itemId]);

  if (!report || !item) {
    return (
      <aside className="side-panel">
        <PanelHead title="Review" onClose={onClose} />
        <p className="error-text">This checklist item could not be found.</p>
      </aside>
    );
  }
  const needsReason = status === "not_applicable" && !reason.trim();
  const canReview = result.persisted;

  async function save() {
    setState("saving");
    setError(null);
    try {
      await onUpdate(templateId, itemId, {
        status: status !== item!.status ? status : undefined,
        not_applicable_reason: status === "not_applicable" ? reason.trim() : undefined,
        reviewer_note: note.trim() || undefined,
        confirm: true,
      });
      setState("saved");
    } catch (e) {
      setState("error");
      setError(e instanceof Error ? e.message : "Saving failed.");
    }
  }

  return (
    <aside className="side-panel" aria-label={`Review ${item.label}`}>
      <PanelHead title={`Review: ${item.label}`} onClose={onClose} />
      {definition?.description && <p className="small muted">{definition.description}</p>}
      <div className="review-current">
        Current: <StatusBadge status={item.status} />{" "}
        {item.reviewed ? <span className="tag tag-ok">Reviewed</span> : <span className="tag tag-neutral">Provisional</span>}
      </div>
      {item.validation_notes.length > 0 && (
        <ul className="review-notes">
          {item.validation_notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {item.rationale && <p className="small"><strong>Model rationale:</strong> {item.rationale}</p>}

      <h3>Clinician question</h3>
      {item.question_evidence.length ? (
        <SegmentsWithContext result={result} segmentIds={item.question_evidence.map((r) => r.segment_id)} refs={item.question_evidence} />
      ) : (
        <p className="muted small">No clinician question found.</p>
      )}
      <h3>Information captured</h3>
      {item.information_evidence.length ? (
        <SegmentsWithContext result={result} segmentIds={item.information_evidence.map((r) => r.segment_id)} refs={item.information_evidence} />
      ) : (
        <p className="muted small">No information found.</p>
      )}

      {canReview ? (
        <form
          className="review-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!needsReason) void save();
          }}
        >
          <fieldset>
            <legend>Your decision</legend>
            {STATUS_ORDER.map((s) => (
              <label key={s} className={`radio-row${status === s ? " radio-row-active" : ""}`}>
                <input type="radio" name="status" value={s} checked={status === s} onChange={() => setStatus(s)} />
                <span>
                  <strong>{STATUS_LABELS[s]}</strong>
                  <span className="radio-help">{STATUS_HELP[s]}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {status === "not_applicable" && (
            <label className="field">
              <span className="field-label">Reason (required)</span>
              <input type="text" value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
              {needsReason && <span className="field-error">Please give a reason.</span>}
            </label>
          )}
          <label className="field">
            <span className="field-label">Reviewer note (optional)</span>
            <input type="text" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="btn-row">
            <button type="submit" className="btn btn-primary" disabled={state === "saving" || needsReason}>
              {state === "saving" ? "Saving…" : status === item.status ? "Confirm as reviewed" : "Save decision"}
            </button>
          </div>
          <div aria-live="polite" className="save-feedback">
            {state === "saved" && (
              <span className="success-text">
                <IconCheck /> Saved — metrics recalculated: asked {report.question_coverage?.numerator}/
                {report.question_coverage?.denominator}, captured {report.information_capture?.numerator}/
                {report.information_capture?.denominator}.
              </span>
            )}
            {state === "error" && <span className="error-text">{error}</span>}
          </div>
        </form>
      ) : (
        <p className="banner banner-warn small">This result was not saved, so review decisions cannot be stored.</p>
      )}
      <p className="small muted">{DISCLAIMER}</p>
    </aside>
  );
}

function StatementPanel({ result, statementId, onClose }: { result: AnalyzeResponse; statementId: string; onClose: () => void }) {
  const st = result.patient_explanation.statements.find((s) => s.statement_id === statementId);
  if (!st) {
    return (
      <aside className="side-panel">
        <PanelHead title="Sentence" onClose={onClose} />
        <p className="error-text">This sentence could not be found.</p>
      </aside>
    );
  }
  const facts = result.facts.filter((f) => st.fact_ids.includes(f.fact_id));
  return (
    <aside className="side-panel">
      <PanelHead title="Compare with the source" onClose={onClose} />
      <div className="compare-block">
        <span className="compare-label">Plain-language sentence</span>
        <p className="compare-text">{st.text}</p>
      </div>
      {st.meaning_checks.length > 0 && (
        <ul className="review-notes">
          {st.meaning_checks.map((m, i) => (
            <li key={i}>{m.message}</li>
          ))}
        </ul>
      )}
      {facts.map((f) => (
        <div key={f.fact_id} className="compare-block">
          <span className="compare-label">
            {f.fact_id} · {f.concept} · polarity <span className={`polarity polarity-${f.polarity}`}>{f.polarity}</span>
          </span>
          <p className="compare-text">{f.normalized_value}</p>
          <SegmentsWithContext result={result} segmentIds={f.source_segment_ids} refs={f.evidence} />
        </div>
      ))}
      <p className="small muted">
        The checks are heuristics: a flag means “compare carefully”, not “wrong”. Correct the summary before sharing it.
      </p>
    </aside>
  );
}

export function SidePanel({
  result,
  templates,
  selection,
  onClose,
  onUpdateItem,
  onJump,
}: {
  result: AnalyzeResponse;
  templates: ChecklistTemplate[];
  selection: PanelSelection | null;
  onClose: () => void;
  onUpdateItem: (templateId: string, itemId: string, update: CoverageItemUpdate) => Promise<void>;
  onJump?: (segmentId: string) => void;
}) {
  jumpHandler = onJump;
  if (selection?.kind === "statement") {
    return <StatementPanel result={result} statementId={selection.statementId} onClose={onClose} />;
  }
  if (!selection) {
    return (
      <aside className="side-panel side-panel-empty">
        <h2>Evidence</h2>
        <p className="muted">
          Select a fact badge such as <span className="fact-badge static">F001</span>, a quote, or a checklist row to see
          the original words in the transcript and record your review.
        </p>
      </aside>
    );
  }

  if (selection.kind === "review") {
    return (
      <ReviewForm
        result={result}
        templates={templates}
        templateId={selection.templateId}
        itemId={selection.itemId}
        onUpdate={onUpdateItem}
        onClose={onClose}
      />
    );
  }

  if (selection.kind === "evidence") {
    return (
      <aside className="side-panel">
        <PanelHead title={selection.title} onClose={onClose} />
        {selection.note && <p className="muted">{selection.note}</p>}
        <SegmentsWithContext result={result} segmentIds={selection.refs.map((r) => r.segment_id)} refs={selection.refs} />
        <p className="small muted">{DISCLAIMER}</p>
      </aside>
    );
  }

  const fact =
    result.facts.find((f) => f.fact_id === selection.factId) ??
    result.rejected_facts.find((f) => f.fact_id === selection.factId);
  if (!fact) {
    return (
      <aside className="side-panel">
        <PanelHead title={selection.factId} onClose={onClose} />
        <p className="error-text">Unknown fact ID — this reference could not be resolved.</p>
      </aside>
    );
  }
  const statusLabel =
    fact.evidence_status === "source_linked"
      ? "Source-linked: quote found in the cited segment"
      : fact.evidence_status === "needs_review"
        ? "Needs review"
        : "Rejected by validation — not used in outputs";
  const details: [string, string | null][] = [
    ["Value", fact.normalized_value],
    ["Polarity", fact.polarity],
    ["Certainty", fact.certainty],
    ["Category", fact.category],
    ["Duration", fact.duration],
    ["Frequency", fact.frequency],
    ["Severity", fact.severity],
    ["Location", fact.location],
  ];

  return (
    <aside className="side-panel">
      <PanelHead title={`${fact.fact_id} · ${fact.concept}`} onClose={onClose} />
      <div className={`evidence-status evidence-${fact.evidence_status}`}>{statusLabel}</div>
      <dl className="fact-dl">
        {details
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="fact-dl-row">
              <dt>{k}</dt>
              <dd className={k === "Polarity" ? `polarity polarity-${v}` : undefined}>{v}</dd>
            </div>
          ))}
      </dl>
      {fact.review_notes.length > 0 && (
        <ul className="review-notes">
          {fact.review_notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      <h3>Source in transcript</h3>
      <SegmentsWithContext result={result} segmentIds={fact.source_segment_ids} refs={fact.evidence} />
      <p className="small muted">{DISCLAIMER}</p>
    </aside>
  );
}
