import type { AnalyzeResponse } from "../types/api";
import { STATUS_LABELS, truncate, type PanelSelection } from "./common";
import type { TabId } from "./SummaryCards";
import { IconCheck } from "./icons";

type Row = {
  key: string;
  tone: "attn" | "danger" | "info";
  title: string;
  detail: string;
  action: string;
  open: () => void;
};

export function ReviewQueue({
  result,
  onSelect,
  onTab,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: PanelSelection) => void;
  onTab: (tab: TabId) => void;
}) {
  const go = (tab: TabId, sel?: PanelSelection) => () => {
    onTab(tab);
    if (sel) onSelect(sel);
  };
  const groups: { title: string; help: string; rows: Row[] }[] = [];

  const coverageRows: Row[] = result.coverage_reports.flatMap((r) =>
    r.items
      .filter((i) => !i.reviewed && (i.status === "not_found_in_transcript" || i.status === "unclear_needs_review"))
      .map((i) => ({
        key: `${r.template_id}-${i.item_id}`,
        tone: "attn" as const,
        title: `${i.label} — ${STATUS_LABELS[i.status]}`,
        detail: `${r.template_name?.replace(" — consultation documentation demo", "")} checklist. ${
          i.status === "unclear_needs_review" ? "Not counted until you decide." : "Counted as a gap until reviewed."}`,
        action: "Review",
        open: go("coverage", { kind: "review", templateId: r.template_id!, itemId: i.item_id }),
      })),
  );
  groups.push({ title: "Checklist topics", help: "Topics not found or unclear in the transcript.", rows: coverageRows });

  groups.push({
    title: "Symptoms nobody followed up",
    help: "The patient mentioned these, but no clinician question or response about them was found.",
    rows: result.symptoms
      .filter((s) => s.followed_up === false)
      .map((s) => ({
        key: s.symptom_id,
        tone: "attn" as const,
        title: s.concept,
        detail: `Mentioned: “${truncate(s.supporting_quote, 90)}”`,
        action: "Show source",
        open: () => onSelect(s.fact_ids[0] ? { kind: "fact", factId: s.fact_ids[0] } : { kind: "evidence", title: s.concept, refs: s.evidence }),
      })),
  });

  groups.push({
    title: "Possible meaning changes in the patient summary",
    help: "A plain-language sentence may have lost a negation, an uncertainty or a number. Compare it with the source.",
    rows: result.patient_explanation.statements
      .filter((s) => s.meaning_checks.length)
      .map((s) => ({
        key: s.statement_id,
        tone: "attn" as const,
        title: `“${truncate(s.text, 100)}”`,
        detail: s.meaning_checks.map((m) => m.message).join(" "),
        action: "Compare",
        open: go("patient", { kind: "statement", statementId: s.statement_id }),
      })),
  });

  groups.push({
    title: "Facts that need review",
    help: "Source-linked, but the speaker, certainty or evidence is questionable. Shown as “needs review” in the note.",
    rows: result.facts
      .filter((f) => f.evidence_status === "needs_review")
      .map((f) => ({
        key: f.fact_id,
        tone: "attn" as const,
        title: `${f.fact_id} · ${f.normalized_value}`,
        detail: f.review_notes.join(" "),
        action: "Show source",
        open: () => onSelect({ kind: "fact", factId: f.fact_id }),
      })),
  });

  groups.push({
    title: "Rejected by validation",
    help: "Proposed by the engine but not found in the transcript. Never shown in the note or summary.",
    rows: result.rejected_facts.map((f) => ({
      key: `rej-${f.fact_id}`,
      tone: "danger" as const,
      title: `${f.fact_id} · ${f.normalized_value}`,
      detail: f.review_notes.join(" "),
      action: "Details",
      open: () => onSelect({ kind: "fact", factId: f.fact_id }),
    })),
  });

  const transcriptIssues = [
    ...result.parse_warnings,
    ...result.warnings.filter((w) => /speaker/i.test(w)),
    ...result.validation_findings.filter((f) => f.code === "statement_unknown_fact").map((f) => f.message),
  ];
  groups.push({
    title: "Transcript and processing notes",
    help: "Problems with the input or with generated sentences that were removed.",
    rows: transcriptIssues.map((w, i) => ({
      key: `t-${i}`, tone: "info" as const, title: w, detail: "", action: "Transcript", open: go("transcript"),
    })),
  });

  const total = groups.reduce((n, g) => n + g.rows.length, 0);
  if (!total) {
    return (
      <div className="empty-state fade-in">
        <IconCheck size={22} />
        <h2>Nothing flagged</h2>
        <p className="muted">All facts are source-linked and every checklist topic has been reviewed or found.</p>
      </div>
    );
  }
  return (
    <section className="review-queue">
      <p className="muted">
        {total} item{total === 1 ? "" : "s"} to check. Each one opens the exact place it refers to.
      </p>
      {groups.filter((g) => g.rows.length).map((g) => (
        <div key={g.title} className="queue-group">
          <h3>
            {g.title} <span className="count">{g.rows.length}</span>
          </h3>
          <p className="small muted">{g.help}</p>
          <ul className="queue-list">
            {g.rows.map((r) => (
              <li key={r.key} className={`queue-row queue-${r.tone}`}>
                <span className="queue-dot" aria-hidden="true" />
                <div className="queue-text">
                  <span className="queue-title">{r.title}</span>
                  {r.detail && <span className="queue-detail">{r.detail}</span>}
                </div>
                <button type="button" className="btn btn-small btn-secondary" onClick={r.open}>
                  {r.action}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
