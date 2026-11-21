import { useState } from "react";
import type { AnalyzeResponse, ChecklistTemplate, CoverageItemUpdate, Sample } from "../types/api";
import { ClinicalNoteView } from "./ClinicalNoteView";
import { CoverageView } from "./CoverageView";
import { SidePanel } from "./EvidencePanel";
import { FactsView } from "./FactsView";
import { PatientExplanationView } from "./PatientExplanationView";
import { PatientHeader } from "./PatientHeader";
import { ReviewQueue } from "./ReviewQueue";
import { SummaryCards, reviewCount, type TabId } from "./SummaryCards";
import { TranscriptView } from "./TranscriptView";
import type { PanelSelection } from "./common";

export function ResultsWorkspace({
  result,
  sample,
  templates,
  onUpdateItem,
  onNewAnalysis,
  onDelete,
}: {
  result: AnalyzeResponse;
  sample: Sample | null;
  templates: ChecklistTemplate[];
  onUpdateItem: (templateId: string, itemId: string, update: CoverageItemUpdate) => Promise<void>;
  onNewAnalysis: () => void;
  onDelete: () => Promise<void>;
}) {
  const [tab, setTab] = useState<TabId>("note");
  const [selection, setSelection] = useState<PanelSelection | null>(null);
  const [focusSegment, setFocusSegment] = useState<string | null>(null);

  const toReview = reviewCount(result);
  const tabs: { id: TabId; label: string; count?: number; attn?: boolean }[] = [
    { id: "note", label: "Clinical note" },
    { id: "patient", label: "Patient summary" },
    { id: "coverage", label: "Coverage" },
    { id: "review", label: "Review", count: toReview || undefined, attn: toReview > 0 },
    { id: "facts", label: "Facts", count: result.facts.length },
    { id: "transcript", label: "Transcript" },
  ];
  const selectionKey = selection ? JSON.stringify(selection) : "none";

  return (
    <div className="results">
      <PatientHeader
        result={result}
        onSelect={setSelection}
        onNewAnalysis={onNewAnalysis}
        onDelete={() => {
          if (window.confirm("Delete this saved encounter from the server?")) void onDelete();
        }}
      />
      <div className="page">
        <SummaryCards result={result} onSelect={setSelection} onTab={setTab} />
        {result.warnings.some((w) => /speaker/i.test(w)) && (
          <div className="banner banner-warn">{result.warnings.find((w) => /speaker/i.test(w))}</div>
        )}

        <div className="tabs" role="tablist" aria-label="Result views">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls="tab-panel"
              className={`tab${tab === t.id ? " tab-active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.count !== undefined && <span className={`tab-count${t.attn ? " tab-count-attn" : ""}`}>{t.count}</span>}
            </button>
          ))}
        </div>

        <div className="workspace">
          <div className="card tab-panel" id="tab-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            <div key={tab} className="fade-in">
              {tab === "note" && (
                <>
                  <ClinicalNoteView result={result} onSelect={setSelection} onShowCoverage={() => setTab("coverage")} />
                  {sample?.reference_note && (
                    <details className="reference-note">
                      <summary>Compare with the ACI-Bench reference note (human-written)</summary>
                      <p className="small muted">Written by the dataset authors for the full encounter.</p>
                      <pre>{sample.reference_note}</pre>
                    </details>
                  )}
                </>
              )}
              {tab === "patient" && (
                <PatientExplanationView
                  result={result}
                  selectedStatementId={selection?.kind === "statement" ? selection.statementId : null}
                  onSelect={setSelection}
                />
              )}
              {tab === "coverage" && (
                <CoverageView
                  reports={result.coverage_reports}
                  selectedItemId={selection?.kind === "review" ? selection.itemId : null}
                  onSelect={setSelection}
                />
              )}
              {tab === "review" && <ReviewQueue result={result} onSelect={setSelection} onTab={setTab} />}
              {tab === "facts" && <FactsView result={result} onSelect={setSelection} />}
              {tab === "transcript" && <TranscriptView result={result} focusSegmentId={focusSegment} onSelect={setSelection} />}
            </div>
          </div>
          <div key={selectionKey} className="panel-slot slide-in">
            <SidePanel
              result={result}
              templates={templates}
              selection={selection}
              onClose={() => setSelection(null)}
              onUpdateItem={onUpdateItem}
              onJump={(sid) => {
                setFocusSegment(sid);
                setTab("transcript");
              }}
            />
          </div>
        </div>
        <details className="notices">
          <summary>About this result</summary>
          <ul>
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      </div>
    </div>
  );
}
