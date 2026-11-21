import { useCallback, useEffect, useState } from "react";
import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "./App.css";
import { EvaluationPage } from "./components/EvaluationPage";
import { RecordExplainer } from "./components/RecordExplainer";
import { ResultsWorkspace } from "./components/ResultsWorkspace";
import { ToastProvider, useToast } from "./components/Toast";
import { TranscriptInput, type AnalyzeOptions } from "./components/TranscriptInput";
import { ApiError, api, getSessionToken } from "./services/api";
import type { AnalyzeResponse, ChecklistTemplate, CoverageItemUpdate, PublicConfig, Sample, SampleSummary } from "./types/api";

type Route = { page: "consultation"; encounterId: string | null } | { page: "record" } | { page: "evaluation" };

function parseRoute(): Route {
  const h = window.location.hash;
  if (h.startsWith("#/encounter/")) return { page: "consultation", encounterId: h.slice("#/encounter/".length) };
  if (h === "#/record") return { page: "record" };
  if (h === "#/evaluation") return { page: "evaluation" };
  return { page: "consultation", encounterId: null };
}

function PasswordGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <section className="card gate fade-in">
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
        <label className="sr-only" htmlFor="gate-pw">Password</label>
        <input id="gate-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" className="btn btn-primary">Continue</button>
      </form>
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}

function Shell() {
  const [route, setRoute] = useState<Route>(parseRoute);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [templates, setTemplates] = useState<ChecklistTemplate[]>([]);
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [transcript, setTranscript] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const toast = useToast();

  useEffect(() => {
    const onHash = () => setRoute(parseRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

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

  useEffect(() => {
    if (route.page !== "consultation") return;
    if (route.encounterId && config && !locked && result?.encounter_id !== route.encounterId) void loadEncounter(route.encounterId);
    if (!route.encounterId && result) setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route, config, locked]);

  async function handleAnalyze(opts: AnalyzeOptions) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.analyze({
        transcript: opts.transcript,
        language: opts.language,
        template_ids: opts.templateIds,
        provider: opts.provider,
        patient: {
          display_name: opts.patientName.trim() || undefined,
          temp_personnummer: opts.tempPersonnummer.trim() || undefined,
        },
      });
      setResult(res);
      if (res.persisted) window.location.hash = `#/encounter/${res.encounter_id}`;
      window.scrollTo({ top: 0, behavior: "smooth" });
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
    const updated = await api.updateItem(result.encounter_id, templateId, itemId, update);
    setResult(updated);
    toast("Review saved — metrics recalculated");
  }

  const nav: { href: string; label: string; active: boolean }[] = [
    { href: result ? `#/encounter/${result.encounter_id}` : "#/", label: "Consultation", active: route.page === "consultation" },
    { href: "#/record", label: "Record explainer", active: route.page === "record" },
    { href: "#/evaluation", label: "Evaluation", active: route.page === "evaluation" },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/" aria-label="TraceCare home">
          <span className="brand-mark" aria-hidden="true">TC</span>
          <span className="brand-name">TraceCare</span>
        </a>
        <nav className="topnav" aria-label="Main">
          {nav.map((n) => (
            <a key={n.label} href={n.href} className={n.active ? "topnav-active" : undefined} aria-current={n.active ? "page" : undefined}>
              {n.label}
            </a>
          ))}
        </nav>
        <span className="env-badge">Prototype · synthetic data</span>
        {(loading || busy) && <div className="progress-bar" role="progressbar" aria-label="Working" />}
      </header>

      <main className="main">
        {error && (
          <div className="page">
            <div className="banner banner-error" role="alert">{error}</div>
          </div>
        )}
        {locked ? (
          <PasswordGate onUnlocked={() => setLocked(false)} />
        ) : route.page === "record" ? (
          <RecordExplainer config={config} onBusy={setBusy} />
        ) : route.page === "evaluation" ? (
          <EvaluationPage />
        ) : result ? (
          <ResultsWorkspace
            key={result.encounter_id}
            result={result}
            templates={templates}
            sample={sample && sample.transcript === transcript ? sample : null}
            onUpdateItem={handleUpdateItem}
            onNewAnalysis={() => {
              setResult(null);
              window.location.hash = "#/";
            }}
            onDelete={async () => {
              try {
                await api.deleteEncounter(result.encounter_id);
                setResult(null);
                window.location.hash = "#/";
                toast("Encounter deleted");
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

      <footer className="app-footer">
        TraceCare is a hackathon prototype. It does not diagnose, give treatment advice or triage, and it does not assess
        clinicians. All output requires review by a qualified clinician. Data: synthetic transcripts, ACI-Bench
        (role-played encounters) and PLABA.
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}
