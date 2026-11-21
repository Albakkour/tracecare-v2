import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { ChecklistTemplate, ProviderName, PublicConfig, Sample, SampleSummary } from "../types/api";
import { IconFile, IconRefresh, IconShield, IconUser } from "./icons";

export interface AnalyzeOptions {
  transcript: string;
  templateIds: string[];
  provider: ProviderName | undefined;
  patientName: string;
  tempPersonnummer: string;
}

const TEMP_PNR_RE = /^(\d{4})(\d{2})(\d{2})-T\d{3}$/i;
const REAL_PNR_RE = /^(19|20)?\d{6}[-+]?\d{4}$/;

function ageFromPnr(pnr: string): number | null {
  const m = TEMP_PNR_RE.exec(pnr.trim());
  if (!m) return null;
  const birth = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(birth.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  if (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())) age--;
  return age;
}

function pnrError(pnr: string): string | null {
  const v = pnr.trim();
  if (!v) return null;
  if (REAL_PNR_RE.test(v.replace(/\s/g, ""))) return "Real personnummer are not accepted. Use a temporary T-number.";
  if (!TEMP_PNR_RE.test(v)) return "Use the format YYYYMMDD-TNNN, e.g. 19850412-T123.";
  return ageFromPnr(v) === null ? "Invalid date." : null;
}

export function TranscriptInput({
  config,
  templates,
  samples,
  transcript,
  setTranscript,
  loadedSample,
  onLoadSample,
  onAnalyze,
  loading,
}: {
  config: PublicConfig | null;
  templates: ChecklistTemplate[];
  samples: SampleSummary[];
  transcript: string;
  setTranscript: (t: string) => void;
  loadedSample: Sample | null;
  onLoadSample: (id: string) => Promise<Sample | null>;
  onAnalyze: (opts: AnalyzeOptions) => void;
  loading: boolean;
}) {
  const [sampleId, setSampleId] = useState("");
  const [templateChoice, setTemplateChoice] = useState<string>("all");
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [patientName, setPatientName] = useState("");
  const [pnr, setPnr] = useState("");
  const maxChars = config?.max_transcript_chars ?? 30000;
  const tooLong = transcript.length > maxChars;
  const providers = config?.providers ?? [];
  const effectiveSampleId = sampleId || samples[0]?.sample_id || "";
  const pnrProblem = pnrError(pnr);
  const age = ageFromPnr(pnr);

  async function newTempId() {
    try {
      setPnr((await api.tempPatientId()).temp_personnummer);
    } catch {
      /* the field stays editable */
    }
  }

  useEffect(() => {
    if (!pnr) void newTempId();
    // Generate one temporary number on first load only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="input-page">
      <div className="intro">
        <h1>Analyse a consultation</h1>
        <p className="muted">
          Turn a doctor–patient transcript into an evidence-linked draft note, a patient-friendly explanation, and a
          transparent coverage report.
        </p>
        <p className="callout callout-warn">
          <IconShield size={18} />
          <span>
            Synthetic or role-played data only. Never enter real patient data or a real personnummer.
          </span>
        </p>
      </div>

      <section className="card form-card" aria-labelledby="patient-h">
        <h2 id="patient-h">
          <IconUser /> Patient
        </h2>
        <div className="form-grid">
          <label className="field">
            <span className="field-label">Name</span>
            <input
              type="text"
              value={patientName}
              maxLength={80}
              onChange={(e) => setPatientName(e.target.value)}
              autoComplete="off"
            />
            <span className="field-help">Optional. If empty, a name is detected from the clinician's greeting.</span>
          </label>
          <div className="field">
            <label className="field-label" htmlFor="pnr">
              Temporary personnummer
            </label>
            <div className="input-with-btn">
              <input
                id="pnr"
                type="text"
                className="mono"
                value={pnr}
                onChange={(e) => setPnr(e.target.value)}
                aria-invalid={Boolean(pnrProblem)}
                aria-describedby="pnr-help"
                autoComplete="off"
              />
              <button type="button" className="btn btn-secondary" onClick={newTempId} aria-label="Generate a new temporary personnummer">
                <IconRefresh /> New
              </button>
            </div>
            {pnrProblem ? (
              <span className="field-error" id="pnr-help">{pnrProblem}</span>
            ) : (
              <span className="field-help" id="pnr-help">
                Format YYYYMMDD-TNNN. The letter T marks a temporary reserve number that can never be a real
                personnummer.{age !== null && ` Age: ${age} years.`}
              </span>
            )}
          </div>
        </div>
      </section>

      <section className="card form-card" aria-labelledby="transcript-h">
        <div className="section-head">
          <h2 id="transcript-h">
            <IconFile /> Transcript
          </h2>
          <div className="sample-picker">
            <label className="sr-only" htmlFor="sample">
              Sample transcript
            </label>
            <select id="sample" value={effectiveSampleId} onChange={(e) => setSampleId(e.target.value)}>
              {samples.map((s) => (
                <option key={s.sample_id} value={s.sample_id}>
                  {s.title}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!effectiveSampleId || loading}
              onClick={async () => {
                const s = await onLoadSample(effectiveSampleId);
                if (s?.suggested_template_id) setTemplateChoice(s.suggested_template_id);
                if (s?.patient_name) setPatientName(s.patient_name);
              }}
            >
              Load sample
            </button>
          </div>
        </div>
        {loadedSample && (
          <p className="small muted">
            {loadedSample.description}
            {loadedSample.citation && <> Source: {loadedSample.citation}</>}
          </p>
        )}
        <label className="field">
          <span className="field-label">Transcript text (one speaker turn per line)</span>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={14}
            spellCheck={false}
            aria-describedby="transcript-help"
          />
          <span className={`field-help ${tooLong ? "field-error" : ""}`} id="transcript-help">
            Label each line, e.g. <code>Doctor: …</code> / <code>Patient: …</code> or <code>[doctor] …</code>. Speakers
            are never guessed. {transcript.length.toLocaleString()} / {maxChars.toLocaleString()} characters.
          </span>
        </label>

        <div className="form-grid form-grid-3">
          <label className="field">
            <span className="field-label">Checklist template</span>
            <select value={templateChoice} onChange={(e) => setTemplateChoice(e.target.value)}>
              <option value="all">Auto-match a configured template</option>
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.display_name} (v{t.version})
                </option>
              ))}
            </select>
            <span className="field-help">Demo templates: illustrative, not clinically validated.</span>
          </label>
          <label className="field">
            <span className="field-label">Language</span>
            <select value="en" disabled>
              <option value="en">English</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Analysis engine</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value as ProviderName | "")} disabled={providers.length < 2}>
              <option value="">Default ({config?.default_provider === "anthropic" ? "Claude" : "Demo"})</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {p === "anthropic" ? `Claude (${config?.model})` : "Demo — rule-based, no AI"}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <div className="action-bar">
        <span className="small muted">
          {loading ? "Analysing — this can take up to a minute with Claude." : "The result is a draft that requires clinician review."}
        </span>
        <button
          type="button"
          className="btn btn-primary btn-large"
          disabled={loading || !transcript.trim() || tooLong || Boolean(pnrProblem)}
          onClick={() =>
            onAnalyze({
              transcript,
              templateIds: templateChoice === "all" ? [] : [templateChoice],
              provider: provider || undefined,
              patientName,
              tempPersonnummer: pnr,
            })
          }
        >
          {loading ? (
            <>
              <span className="spinner" aria-hidden="true" /> Analysing…
            </>
          ) : (
            "Analyse consultation"
          )}
        </button>
      </div>
    </div>
  );
}
