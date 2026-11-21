import type { AnalyzeResponse, CoverageMetric, MedicalFact } from "../types/api";
import { percent, type PanelSelection } from "./common";

export type TabId = "note" | "patient" | "coverage" | "review" | "facts" | "transcript";

export function reviewCount(result: AnalyzeResponse): number {
  const items = result.coverage_reports.flatMap((r) => r.items).filter((i) => !i.reviewed &&
    (i.status === "not_found_in_transcript" || i.status === "unclear_needs_review")).length;
  const facts = result.facts.filter((f) => f.evidence_status === "needs_review").length;
  const meaning = result.patient_explanation.statements.filter((s) => s.meaning_checks.length).length;
  const unexplored = result.symptoms.filter((s) => s.followed_up === false).length;
  return items + facts + meaning + unexplored + result.rejected_facts.length;
}

function Stat({ metric, onClick }: { metric: CoverageMetric | null | undefined; onClick: () => void }) {
  return (
    <button type="button" className="stat stat-button" onClick={onClick}>
      <span className="stat-label">{metric?.label.replace(" coverage", "") ?? "Coverage"}</span>
      {metric?.available ? (
        <>
          <span className="stat-value">
            {metric.numerator}/{metric.denominator}
            <span className="stat-sub">{percent(metric.percentage)}</span>
          </span>
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ transform: `scaleX(${(metric.percentage ?? 0) / 100})` }} />
          </span>
        </>
      ) : (
        <span className="stat-value stat-na">n/a</span>
      )}
    </button>
  );
}

function Chips({ facts, tone, onSelect }: { facts: MedicalFact[]; tone: string; onSelect: (s: PanelSelection) => void }) {
  if (!facts.length) return <span className="muted small">—</span>;
  return (
    <div className="chip-row">
      {facts.map((f) => (
        <button
          key={f.fact_id}
          type="button"
          className={`chip chip-${tone}`}
          onClick={() => onSelect({ kind: "fact", factId: f.fact_id })}
          title={`${f.normalized_value} — show source`}
        >
          {f.concept}
        </button>
      ))}
    </div>
  );
}

export function SummaryCards({
  result,
  onSelect,
  onTab,
}: {
  result: AnalyzeResponse;
  onSelect: (sel: PanelSelection) => void;
  onTab: (tab: TabId) => void;
}) {
  const report = result.coverage_reports.find((r) => r.template_id);
  const patient = result.facts.filter((f) => f.evidence_status === "source_linked" && !isClinician(f));
  const reported = patient.filter((f) => f.polarity === "positive" && f.category !== "history");
  const denied = patient.filter((f) => f.polarity === "negative");
  const uncertain = result.facts.filter((f) => !isClinician(f) && (f.polarity === "uncertain" || f.evidence_status === "needs_review"));
  const toReview = reviewCount(result);
  const templates = result.coverage_reports.filter((r) => r.template_id).length;

  return (
    <section className="overview" aria-label="At a glance">
      <div className="stat-strip">
        <div className="stat stat-wide">
          <span className="stat-label">Chief concern</span>
          <span className="stat-concern">{result.chief_concern ?? "Not established"}</span>
          <span className="stat-hint">
            {report ? `${report.template_name?.replace(" — consultation documentation demo", "")} checklist` : "No checklist matched"}
            {templates > 1 && ` + ${templates - 1} more`}
          </span>
        </div>
        <Stat metric={report?.question_coverage} onClick={() => onTab("coverage")} />
        <Stat metric={report?.information_capture} onClick={() => onTab("coverage")} />
        <button type="button" className={`stat stat-button ${toReview ? "stat-attn" : ""}`} onClick={() => onTab("review")}>
          <span className="stat-label">To review</span>
          <span className="stat-value">{toReview}</span>
          <span className="stat-hint">{toReview ? "Open the review list" : "Nothing flagged"}</span>
        </button>
      </div>
      <div className="findings-strip">
        <div>
          <span className="findings-label">Reported</span>
          <Chips facts={reported} tone="pos" onSelect={onSelect} />
        </div>
        <div>
          <span className="findings-label">Denied</span>
          <Chips facts={denied} tone="neg" onSelect={onSelect} />
        </div>
        <div>
          <span className="findings-label">Uncertain</span>
          <Chips facts={uncertain} tone="unc" onSelect={onSelect} />
        </div>
      </div>
    </section>
  );
}

const CLINICIAN = new Set(["examination", "assessment", "plan", "prescription", "advice", "follow_up"]);
export function isClinician(f: MedicalFact): boolean {
  return CLINICIAN.has(f.category);
}
