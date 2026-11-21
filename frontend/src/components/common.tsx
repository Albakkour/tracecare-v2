import type { EvidenceReference, ItemStatus, MedicalFact, Speaker } from "../types/api";

export type PanelSelection =
  | { kind: "fact"; factId: string }
  | { kind: "evidence"; title: string; refs: EvidenceReference[]; note?: string }
  | { kind: "review"; templateId: string; itemId: string }
  | { kind: "statement"; statementId: string };

/** Backwards-compatible alias used by the views. */
export type EvidenceSelection = PanelSelection;

export const STATUS_LABELS: Record<ItemStatus, string> = {
  asked_and_addressed: "Asked & answered",
  asked_but_unanswered: "Asked, no answer",
  volunteered_not_asked: "Volunteered",
  not_found_in_transcript: "Not found — review",
  unclear_needs_review: "Unclear — pending",
  not_applicable: "Not applicable",
};

export const STATUS_HELP: Record<ItemStatus, string> = {
  asked_and_addressed: "Clinician asked and the transcript contains the information. Counts for both metrics.",
  asked_but_unanswered: "Clinician asked, but no usable answer was found. Counts for question coverage only.",
  volunteered_not_asked: "Patient gave the information without being asked. Counts for information capture only.",
  not_found_in_transcript: "No question or information found. Counted in the denominator; provisional until reviewed.",
  unclear_needs_review: "Evidence or speaker attribution is unclear. Excluded from the metrics and shown as pending.",
  not_applicable: "Not relevant for this consultation. Excluded from both metrics; a reason is required.",
};

export const STATUS_ORDER: ItemStatus[] = [
  "asked_and_addressed",
  "asked_but_unanswered",
  "volunteered_not_asked",
  "not_found_in_transcript",
  "unclear_needs_review",
  "not_applicable",
];

export const SPEAKER_LABELS: Record<Speaker, string> = {
  clinician: "Clinician",
  patient: "Patient",
  other: "Other speaker",
  unknown: "Unknown speaker",
};

export function StatusBadge({ status }: { status: ItemStatus }) {
  return (
    <span className={`status status-${status}`} title={STATUS_HELP[status]}>
      <span className="status-dot" aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}

export function SpeakerChip({ speaker, label }: { speaker: Speaker | null; label?: string | null }) {
  const s = speaker ?? "unknown";
  return (
    <span className={`speaker speaker-${s}`} title={label ? `Label in transcript: ${label}` : undefined}>
      {SPEAKER_LABELS[s]}
    </span>
  );
}

export function FactBadge({
  fact,
  factId,
  onSelect,
}: {
  fact?: MedicalFact;
  factId: string;
  onSelect: (sel: PanelSelection) => void;
}) {
  const review = fact?.evidence_status === "needs_review";
  return (
    <button
      type="button"
      className={`fact-badge${review ? " fact-badge-review" : ""}`}
      onClick={() => onSelect({ kind: "fact", factId })}
      aria-label={`Show source of ${factId}${fact ? ` (${fact.concept})` : ""}`}
      title="Show the source in the transcript"
    >
      {factId}
    </button>
  );
}

export function QuoteButton({
  refs,
  title,
  onSelect,
  max = 110,
}: {
  refs: EvidenceReference[];
  title: string;
  onSelect: (sel: PanelSelection) => void;
  max?: number;
}) {
  if (!refs.length) return <span className="muted">—</span>;
  return (
    <div className="quote-list">
      {refs.map((r, i) => (
        <button
          key={`${r.segment_id}-${i}`}
          type="button"
          className="quote-button"
          onClick={(e) => {
            e.stopPropagation();
            onSelect({ kind: "evidence", title, refs: [r] });
          }}
          title="Show this quote in the transcript"
        >
          <span className="seg-id">{r.segment_id}</span>
          <span>“{truncate(r.quote, max)}”</span>
        </button>
      ))}
    </div>
  );
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function percent(value: number | null): string {
  if (value === null) return "n/a";
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function initials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}
