import { useState } from "react";
import type { AnalyzeResponse, ChecklistTemplate, CoverageItemUpdate, Sample } from "../types/api";
import { ClinicalNoteView } from "./ClinicalNoteView";
import { CoverageView } from "./CoverageView";
import { SidePanel } from "./EvidencePanel";
import { FactsView } from "./FactsView";
import { PatientExplanationView } from "./PatientExplanationView";
import { PatientHeader } from "./PatientHeader";
import { SummaryCards, type TabId } from "./SummaryCards";
import { TranscriptView } from "./TranscriptView";
import type { PanelSelection } from "./common";
import { IconInfo } from "./icons";

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

  const report = result.coverage_reports.find((r) => r.template_id);
  const attention = (report?.pending_review_count ?? 0) + (report?.not_found_count ?? 0);
  const findingsCount = result.validation_findings.length;
  const tabs: { id: TabId; label: string; count?: number; attn?: boolean }[] = [
    { id: "note", label: "Clinical note" },
    { id: "patient", label: "Patient explanation" },
    { id: "coverage", label: "Coverage", count: attention || undefined, attn: attention > 0 },
    { id: "facts", label: "Facts", count: result.facts.length },
    { id: "transcript", label: "Transcript", count: findingsCount || undefined },
  ];

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
      <SummaryCards result={result} onSelect={setSelection} onTab={setTab} />

      <details className="notices">
        <summary>
          <IconInfo size={16} /> About this result ({result.warnings.length + result.parse_warnings.length} notices)
        </summary>
        <ul>
          {[...result.parse_warnings, ...result.warnings].map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </details>

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
          {tab === "note" && (
            <>
              <ClinicalNoteView result={result} onSelect={setSelection} onShowCoverage={() => setTab("coverage")} />
              {sample?.reference_note && (
                <details className="reference-note">
                  <summary>Compare with the ACI-Bench reference note (human-written)</summary>
                  <p className="small muted">
                    Written by the dataset authors for the full encounter. It includes examination findings and plans,
                    which TraceCare deliberately does not generate.
                  </p>
                  <pre>{sample.reference_note}</pre>
                </details>
              )}
            </>
          )}
          {tab === "patient" && <PatientExplanationView result={result} onSelect={setSelection} />}
          {tab === "coverage" && (
            <CoverageView
              reports={result.coverage_reports}
              selectedItemId={selection?.kind === "review" ? selection.itemId : null}
              onSelect={setSelection}
            />
          )}
          {tab === "facts" && <FactsView result={result} onSelect={setSelection} />}
          {tab === "transcript" && <TranscriptView result={result} onSelect={setSelection} />}
        </div>
        <SidePanel
          result={result}
          templates={templates}
          selection={selection}
          onClose={() => setSelection(null)}
          onUpdateItem={onUpdateItem}
        />
      </div>
    </div>
  );
}
