import { useCallback, useEffect, useState } from "react";
import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "./App.css";
import { ResultsWorkspace } from "./components/ResultsWorkspace";
import { TranscriptInput, type AnalyzeOptions } from "./components/TranscriptInput";
import { ApiError, api, getSessionToken } from "./services/api";
import type { AnalyzeResponse, ChecklistTemplate, CoverageItemUpdate, PublicConfig, Sample, SampleSummary } from "./types/api";

const HASH_PREFIX = "#/encounter/";

function encounterIdFromHash(): string | null {
  return window.location.hash.startsWith(HASH_PREFIX) ? window.location.hash.slice(HASH_PREFIX.length) : null;
}

function PasswordGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <section className="input-card gate">
      <h2>Demo access</h2>
      <p className="muted">This public demo is protected by a shared password to limit API usage.</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await api.login(password);
            onUnlocked();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Login failed.");
          }
        }}
      >
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" />
        <button type="submit" className="btn btn-primary">
          Continue
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}

export default function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [templates, setTemplates] = useState<ChecklistTemplate[]>([]);
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [transcript, setTranscript] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    Promise.all([api.config(), api.templates(), api.samples()])
      .then(([cfg, tpl, smp]) => {
        setConfig(cfg);
        setTemplates(tpl.templates);
        setSamples(smp.samples);
        setLocked(cfg.demo_gate_enabled && !getSessionToken());
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load configuration."));
  }, []);

  const loadEncounter = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.encounter(id));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setLocked(true);
      setError(e instanceof Error ? `Could not load saved encounter: ${e.message}` : "Could not load encounter.");
      window.location.hash = "";
    } finally {
      setLoading(false);
    }
  }, []);

  // Restore a saved encounter on refresh / shared link.
  useEffect(() => {
    const id = encounterIdFromHash();
    if (id && config && !locked && !result) void loadEncounter(id);
  }, [config, locked, result, loadEncounter]);

  async function handleAnalyze(opts: AnalyzeOptions) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.analyze({
        transcript: opts.transcript,
        language: "en",
        template_ids: opts.templateIds,
        provider: opts.provider,
        patient: {
          display_name: opts.patientName.trim() || undefined,
          temp_personnummer: opts.tempPersonnummer.trim() || undefined,
        },
      });
      setResult(res);
      if (res.persisted) window.location.hash = `${HASH_PREFIX}${res.encounter_id}`;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setLocked(true);
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadSample(id: string): Promise<Sample | null> {
    setError(null);
    try {
      const s = await api.sample(id);
      setSample(s);
      setTranscript(s.transcript);
      return s;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load sample.");
      return null;
    }
  }

  async function handleUpdateItem(templateId: string, itemId: string, update: CoverageItemUpdate) {
    if (!result) return;
    setResult(await api.updateItem(result.encounter_id, templateId, itemId, update));
  }

  function handleNew() {
    setResult(null);
    window.location.hash = "";
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">TC</span>
          <span className="brand-name">TraceCare</span>
          <span className="brand-tagline">Every medical statement, connected to its source.</span>
        </div>
        <span className="tag tag-neutral">Prototype · synthetic data only · not a medical device</span>
      </header>

      <main className="main">
      {error && (
        <div className="banner banner-error" role="alert">
          {error}
        </div>
      )}

      {locked ? (
        <PasswordGate onUnlocked={() => setLocked(false)} />
      ) : result ? (
        <ResultsWorkspace
          result={result}
          templates={templates}
          sample={sample && sample.transcript === transcript ? sample : null}
          onUpdateItem={handleUpdateItem}
          onNewAnalysis={handleNew}
          onDelete={async () => {
            try {
              await api.deleteEncounter(result.encounter_id);
              handleNew();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Delete failed.");
            }
          }}
        />
      ) : (
        <TranscriptInput
          config={config}
          templates={templates}
          samples={samples}
          transcript={transcript}
          setTranscript={setTranscript}
          loadedSample={sample && sample.transcript === transcript ? sample : null}
          onLoadSample={handleLoadSample}
          onAnalyze={handleAnalyze}
          loading={loading}
        />
      )}

      </main>
      <footer className="app-footer small muted">
        TraceCare is a hackathon prototype. It does not provide diagnosis, treatment advice, triage, or emergency
        guidance, and it does not assess clinicians. All output requires review by a qualified clinician. Sample data:
        synthetic transcripts and role-played ACI-Bench encounters; plain-language style references from PLABA.
      </footer>
    </div>
  );
}
