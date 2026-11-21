import type { AnalyzeResponse, CoverageMetric, MedicalFact } from "../types/api";
import { percent, type PanelSelection } from "./common";
import { IconAlert } from "./icons";

export type TabId = "note" | "patient" | "coverage" | "facts" | "transcript";

function MetricCard({ metric, hint, onClick }: { metric: CoverageMetric | null | undefined; hint: string; onClick: () => void }) {
  return (
    <button type="button" className="summary-card" onClick={onClick}>
      <span className="summary-label">{metric?.label ?? "Coverage"}</span>
      {metric?.available ? (
        <>
          <span className="summary-value">
            {metric.numerator}
            <span className="summary-of"> / {metric.denominator}</span>
            <span className="summary-pct">{percent(metric.percentage)}</span>
          </span>
          <span className="meter" aria-hidden="true">
            <span className="meter-fill" style={{ width: `${metric.percentage ?? 0}%` }} />
          </span>
        </>
      ) : (
        <span className="summary-value summary-na">Not available</span>
      )}
      <span className="summary-hint">{hint}</span>
    </button>
  );
}

function Chips({ facts, kind, onSelect }: { facts: MedicalFact[]; kind: string; onSelect: (s: PanelSelection) => void }) {
  if (!facts.length) return <span className="muted small">None</span>;
  return (
    <div className="chip-row">
      {facts.map((f) => (
        <button
          key={f.fact_id}
          type="button"
          className={`chip chip-${kind}`}
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
  const linked = result.facts.filter((f) => f.evidence_status === "source_linked");
  const reported = linked.filter((f) => f.polarity === "positive" && f.category !== "history");
  const denied = linked.filter((f) => f.polarity === "negative");
  const uncertain = result.facts.filter((f) => f.polarity === "uncertain" || f.evidence_status === "needs_review");
  const pending = report?.pending_review_count ?? 0;
  const notFound = report?.not_found_count ?? 0;
  const reviewCount = pending + uncertain.length + result.rejected_facts.length;

  return (
    <section className="summary" aria-label="At a glance">
      <div className="summary-grid">
        <div className="summary-card summary-static">
          <span className="summary-label">Chief concern</span>
          <span className="summary-concern">{result.chief_concern ?? "Not established"}</span>
          <span className="summary-hint">
            {report ? `${report.template_name} · v${report.template_version}` : "No checklist template matched"}
          </span>
        </div>
        <MetricCard
          metric={report?.question_coverage}
          hint="Topics the clinician asked about"
          onClick={() => onTab("coverage")}
        />
        <MetricCard
          metric={report?.information_capture}
          hint="Topics with information captured (asked or volunteered)"
          onClick={() => onTab("coverage")}
        />
        <button
          type="button"
          className={`summary-card ${reviewCount ? "summary-attention" : ""}`}
          onClick={() => onTab(pending || notFound ? "coverage" : "facts")}
        >
          <span className="summary-label">Needs your review</span>
          <span className="summary-value">
            {reviewCount + notFound}
            {reviewCount + notFound > 0 && <IconAlert size={18} className="summary-icon" />}
          </span>
          <span className="summary-hint">
            {notFound} not found · {pending} pending (not counted) · {uncertain.length} uncertain facts
            {result.rejected_facts.length > 0 && ` · ${result.rejected_facts.length} rejected`}
          </span>
        </button>
      </div>
      <div className="findings-strip">
        <div>
          <span className="findings-label">Reported</span>
          <Chips facts={reported} kind="pos" onSelect={onSelect} />
        </div>
        <div>
          <span className="findings-label">Denied</span>
          <Chips facts={denied} kind="neg" onSelect={onSelect} />
        </div>
        <div>
          <span className="findings-label">Uncertain / review</span>
          <Chips facts={uncertain} kind="unc" onSelect={onSelect} />
        </div>
      </div>
    </section>
  );
}
