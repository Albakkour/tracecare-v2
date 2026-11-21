import { useState } from "react";
import type { CoverageMetric, CoverageReport } from "../types/api";
import { QuoteButton, StatusBadge, percent, type PanelSelection } from "./common";
import { IconCheck, IconInfo } from "./icons";

function Metric({ metric, explanation }: { metric: CoverageMetric | null; explanation: string }) {
  if (!metric) return null;
  return (
    <div className="metric">
      <div className="metric-label">{metric.label}</div>
      {metric.available ? (
        <>
          <div className="metric-value">
            {metric.numerator} / {metric.denominator}
            <span className="metric-pct">{percent(metric.percentage)}</span>
          </div>
          <div className="meter" aria-hidden="true">
            <div className="meter-fill" style={{ transform: `scaleX(${(metric.percentage ?? 0) / 100})` }} />
          </div>
        </>
      ) : (
        <div className="metric-value muted">Coverage not available</div>
      )}
      <div className="small muted">{explanation}</div>
    </div>
  );
}

export function CoverageView({
  reports,
  selectedItemId,
  onSelect,
}: {
  reports: CoverageReport[];
  selectedItemId: string | null;
  onSelect: (sel: PanelSelection) => void;
}) {
  const [active, setActive] = useState(0);
  const withTemplate = reports.filter((r) => r.template_id);
  const shown = withTemplate.length ? [withTemplate[Math.min(active, withTemplate.length - 1)]] : reports;
  return (
    <section>
      {withTemplate.length > 1 && (
        <div className="segmented" role="tablist" aria-label="Checklist">
          {withTemplate.map((r, i) => (
            <button key={r.template_id} type="button" role="tab" aria-selected={i === active}
                    className={i === active ? "segmented-active" : ""} onClick={() => setActive(i)}>
              {r.template_name?.replace(" — consultation documentation demo", "")}
              <span className="count">{r.question_coverage?.numerator}/{r.question_coverage?.denominator}</span>
            </button>
          ))}
        </div>
      )}
      <p className="callout">
        <IconInfo size={18} />
        <span>
          Coverage compares this transcript with a <strong>demo checklist</strong>. It is not a clinician performance or
          quality score. Topics not found may have been irrelevant or appropriately not discussed.
        </span>
      </p>
      {shown.map((report, idx) => {
        if (!report.template_id) {
          return (
            <div key={idx} className="empty-state">
              <h3>Coverage not available</h3>
              <p>{report.message}</p>
            </div>
          );
        }
        const reviewed = report.items.filter((i) => i.reviewed).length;
        return (
          <div key={report.template_id} className="coverage-report fade-in">
            <div className="section-head">
              <div>
                <h2>{report.template_name}</h2>
                <div className="small muted">
                  <code>{report.template_id}</code> · v{report.template_version} · demo template, not clinically validated
                </div>
              </div>
              <span className={`tag ${report.review_status === "reviewed" ? "tag-ok" : "tag-review"}`}>
                {report.review_status === "reviewed" ? "All items reviewed" : `${reviewed} / ${report.items.length} reviewed`}
              </span>
            </div>

            <div className="metrics">
              <Metric metric={report.question_coverage} explanation="Asked & answered + asked, no answer" />
              <Metric metric={report.information_capture} explanation="Asked & answered + volunteered" />
            </div>
            <div className="count-pills">
              <span className="pill">Counted: {report.assessable_count}</span>
              <span className={`pill ${report.not_found_count ? "pill-attn" : ""}`}>
                Not found: {report.not_found_count} (counted, provisional)
              </span>
              <span className={`pill ${report.pending_review_count ? "pill-attn" : ""}`}>
                Pending: {report.pending_review_count} (not counted until reviewed)
              </span>
              <span className="pill">Not applicable: {report.not_applicable_count}</span>
            </div>

            <div className="table-wrap">
              <table className="coverage-table">
                <thead>
                  <tr>
                    <th scope="col">Topic</th>
                    <th scope="col">Status</th>
                    <th scope="col">Clinician asked</th>
                    <th scope="col">Information captured</th>
                    <th scope="col">
                      <span className="sr-only">Review</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.map((item) => {
                    const open = () => onSelect({ kind: "review", templateId: report.template_id!, itemId: item.item_id });
                    const attention = item.status === "unclear_needs_review" || item.status === "not_found_in_transcript";
                    return (
                      <tr
                        key={item.item_id}
                        className={`${attention && !item.reviewed ? "row-attn" : ""} ${selectedItemId === item.item_id ? "row-selected" : ""}`}
                        onClick={open}
                      >
                        <td>
                          <strong>{item.label}</strong>
                          {item.not_applicable_reason && <div className="small muted">Reason: {item.not_applicable_reason}</div>}
                        </td>
                        <td>
                          <StatusBadge status={item.status} />
                        </td>
                        <td>
                          <QuoteButton refs={item.question_evidence} title={`${item.label}: clinician question`} onSelect={onSelect} max={70} />
                        </td>
                        <td>
                          <QuoteButton refs={item.information_evidence} title={`${item.label}: information captured`} onSelect={onSelect} max={70} />
                        </td>
                        <td className="cell-action">
                          <button
                            type="button"
                            className={`btn btn-small ${item.reviewed ? "btn-done" : "btn-secondary"}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              open();
                            }}
                            aria-label={`${item.reviewed ? "Reviewed — change review for" : "Review"} ${item.label}`}
                          >
                            {item.reviewed ? (
                              <>
                                <IconCheck /> Reviewed
                              </>
                            ) : (
                              "Review"
                            )}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </section>
  );
}
