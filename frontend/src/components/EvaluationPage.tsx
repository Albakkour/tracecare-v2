import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { EvalSet, EvaluationResults } from "../types/api";

const fmt = (v: number | null | undefined, suffix = "%") => (v === null || v === undefined ? "—" : `${v}${suffix}`);

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

/** Single-series horizontal bar list: one hue, direct value labels, numbers readable as text (table-equivalent). */
function BarList({ data, total }: { data: Record<string, number>; total: number }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <ul className="barlist" aria-label="Checklist template usage">
      {entries.map(([name, v]) => (
        <li key={name} className="barlist-row" title={`${name}: ${v} encounters (${Math.round((100 * v) / total)}%)`}>
          <span className="barlist-label">{name === "msk_pain_demo_v1" ? "Musculoskeletal pain" : name.replace(/_demo_v1$/, "").replaceAll("_", " ")}</span>
          <span className="barlist-track" aria-hidden="true">
            <span className="barlist-bar" style={{ transform: `scaleX(${v / max})` }} />
          </span>
          <span className="barlist-value">{v}</span>
        </li>
      ))}
    </ul>
  );
}

const ROWS: [keyof EvalSet, string, string][] = [
  ["encounters", "Encounters", ""],
  ["statements_resolving_pct", "Generated sentences linked to valid facts", "%"],
  ["facts_per_encounter", "Facts per encounter", ""],
  ["clinician_statements_per_encounter", "Clinician statements per encounter", ""],
  ["encounters_with_coverage_pct", "Encounters with a matching checklist", "%"],
  ["median_question_coverage_pct", "Median clinician question coverage", "%"],
  ["median_information_capture_pct", "Median information capture", "%"],
  ["unexplored_symptoms_per_encounter", "Symptoms not followed up per encounter", ""],
  ["symptoms_also_in_reference_note_pct", "Extracted symptoms also in the reference note", "%"],
];

export function EvaluationPage() {
  const [data, setData] = useState<EvaluationResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.evaluation().then(setData).catch((e) => setError(e instanceof Error ? e.message : "Could not load results."));
  }, []);

  if (error) return <div className="banner banner-error">{error}</div>;
  if (!data) return <div className="page"><p className="muted">Loading evaluation…</p></div>;
  const { aci, plaba } = data;

  return (
    <div className="page eval-page fade-in">
      <header className="page-head">
        <h1>Evaluation on open datasets</h1>
        <p className="muted">
          How TraceCare uses the hackathon datasets, and what we measured. These are engineering checks on role-played
          and research data, not clinical validation.
        </p>
      </header>

      <section className="card">
        <h2>How the datasets are used</h2>
        <div className="uses">
          <div>
            <h3>ACI-Bench (role-played consultations)</h3>
            <ul>
              <li>Four encounters are bundled as samples, and their human-written notes can be compared with TraceCare's draft.</li>
              <li>Their reference notes are bundled as sample records for the record explainer.</li>
              <li>The full pipeline runs on all 207 human transcripts <em>and</em> on the speech-recognition (ASR) versions, to test robustness to transcription errors.</li>
              <li>Parser support for the dataset's <code>[doctor]</code>/<code>[patient]</code> format; one encounter with swapped labels tests speaker-mismatch detection.</li>
            </ul>
          </div>
          <div>
            <h3>PLABA (plain-language adaptations)</h3>
            <ul>
              <li>9,000+ sentence pairs calibrate the meaning-change checks: how often they flag human rewrites, and whether they catch deliberately corrupted ones.</li>
              <li>A few pairs are style examples in the Claude plain-language prompts.</li>
              <li>Not used for training: the project uses a general model plus deterministic validation, by design.</li>
            </ul>
          </div>
        </div>
      </section>

      {plaba && (
        <section className="card">
          <h2>Meaning-change checks on PLABA</h2>
          <p className="small muted">{plaba.sentence_pairs.toLocaleString()} human sentence pairs · generated {plaba.generated}</p>
          <div className="stat-strip">
            <Tile label="Removed negation caught" value={fmt(plaba.corruption_detection.negation_removed?.detected_pct)}
                  hint={`${plaba.corruption_detection.negation_removed?.trials} trials`} />
            <Tile label="Changed number caught" value={fmt(plaba.corruption_detection.number_changed?.detected_pct)}
                  hint={`${plaba.corruption_detection.number_changed?.trials} trials`} />
            <Tile label="Removed hedge caught" value={fmt(plaba.corruption_detection.hedge_removed?.detected_pct)}
                  hint={`${plaba.corruption_detection.hedge_removed?.trials} trials`} />
            <Tile label="Human rewrites sent for review" value={fmt(plaba.human_adaptations.flag_rate_any)}
                  hint={`number ${fmt(plaba.human_adaptations.flag_rate_by_check.number)} · negation ${fmt(plaba.human_adaptations.flag_rate_by_check.negation)}`} />
          </div>
          <p className="small muted">
            {plaba.human_adaptations.interpretation} Many of these are human writers dropping statistics on purpose.
          </p>
          {plaba.examples_flagged_human.length > 0 && (
            <details className="examples">
              <summary>Examples of flagged human rewrites</summary>
              {plaba.examples_flagged_human.map((e, i) => (
                <div key={i} className="example">
                  <p><strong>Original:</strong> {e.original}</p>
                  <p><strong>Plain:</strong> {e.plain}</p>
                  <p className="small text-attn">{e.flags.join(" ")}</p>
                </div>
              ))}
            </details>
          )}
          <p className="citation">{plaba.citation}</p>
        </section>
      )}

      {aci && (
        <section className="card">
          <h2>Pipeline on ACI-Bench: human vs speech-recognition transcripts</h2>
          <p className="small muted">Engine: {aci.provider} · generated {aci.generated}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  <th scope="col" className="num">Human transcripts</th>
                  <th scope="col" className="num">ASR transcripts</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map(([key, label, suffix]) => (
                  <tr key={key as string}>
                    <td>{label}</td>
                    <td className="num">{fmt(aci.human_transcripts[key] as number, suffix)}</td>
                    <td className="num">{fmt(aci.asr_transcripts?.[key] as number | undefined, suffix)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="mt">Checklist templates applied (human transcripts)</h3>
          <BarList data={aci.human_transcripts.templates_used} total={aci.human_transcripts.encounters} />
          <ul className="small muted">
            {aci.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          <p className="citation">{aci.citation}</p>
        </section>
      )}
    </div>
  );
}
