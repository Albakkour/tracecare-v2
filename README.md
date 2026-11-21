# TraceCare

**Every medical statement, connected to its source.**

TraceCare is a prototype for evidence-grounded clinical documentation and patient communication. It covers hackathon ideas 1 ("Show the receipts") and 5 ("Do you understand your own medical record?"):

1. **Draft clinical note** from a doctor–patient transcript: what the patient reported, plus the clinician's examination findings, assessment, plan, prescriptions and follow-up, each documented as stated. Every sentence links to the exact transcript turn.
2. **After-visit summary** for the patient in plain English or Swedish, sectioned (why you came, what you said, what the doctor found and thinks, treatment, follow-up) and copyable in one go. Sentences whose meaning may have changed are flagged.
3. **Consultation coverage**: 20 symptom checklists plus a general fallback, with separate *clinician question* and *information capture* metrics, and detection of **symptoms nobody followed up**.
4. **Record explainer**: paste a clinical note and get a side-by-side plain-language version, sentence by sentence, with risky simplifications highlighted and dropped content flagged.
5. **Review list**: every item that needs a clinician's attention, in one place, each linking to where it applies.
6. **Evaluation** on ACI-Bench (human vs speech-recognition transcripts) and PLABA (meaning-check calibration), shown in the app.

See [docs/CHALLENGE_GAP_ANALYSIS.md](docs/CHALLENGE_GAP_ANALYSIS.md) for requirement-by-requirement coverage and remaining gaps.

The product is not a diagnostic, triage, treatment, or clinician-performance assessment system. Coverage percentages describe only the transcript against a selected demo checklist. They are not measures of clinical quality or standard of care. All clinical documentation requires professional review.

> **Prototype for synthetic or role-played data only.** Not a medical device. Do not enter real patient data.

## Public Demo

- PUBLIC_DEMO_URL: `ADD_AFTER_DEPLOYMENT`
- PUBLIC_API_URL (health): `ADD_AFTER_DEPLOYMENT/api/health`

**Deploy on Vercel: follow [docs/DEPLOY_VERCEL.md](docs/DEPLOY_VERCEL.md)** (step-by-step). Railway/Render alternatives: [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md). Do not fill these in until a deployment actually works.

## How it works

```text
transcript ─► parser (segment IDs S001…, exact char offsets)            [Python]
          ─► provider proposes facts + checklist evidence as JSON        [Claude or rule-based demo]
          ─► Pydantic validation + evidence validator                    [Python]
               • segment IDs exist • quote appears verbatim in the cited segment
               • speaker plausibility • unique fact IDs • allow-listed template/item IDs
          ─► coverage calculator (two separate metrics)                  [Python]
          ─► clinical note from controlled templates                     [Python]
          ─► patient explanation from accepted facts + meaning checks    [Claude or demo; checked in Python]
          ─► React workspace: click any [F001] badge to see the source
```

The LLM only *proposes*. TraceCare's backend validates every reference, calculates the percentages, and decides what may be shown as source-linked. Unsupported facts are rejected and never appear in outputs. Questionable ones are shown as **Needs review**. A valid quote proves the text exists in the transcript. It does not prove the clinical interpretation is right, so nothing is labelled "clinically verified".

**Coverage formulas** (equal weights; N = items that are not `unclear_needs_review` or `not_applicable`):

- Clinician question coverage = (asked_and_addressed + asked_but_unanswered) / N
- Information capture coverage = (asked_and_addressed + volunteered_not_asked) / N
- `not_found_in_transcript` stays in N and is marked provisional. If N = 0, the result is "Coverage not available".
- Reviewers can change any item's status or mark it not applicable (a reason is required). The backend recalculates both metrics.

## Repository layout

```text
backend/            FastAPI + Pydantic + SQLAlchemy
  app/api/          routes
  app/services/     parser, evidence validator, coverage calculator, note generator, patient explainer, pipeline
  app/llm/          provider interface, Claude provider, rule-based demo provider, prompts
  app/templates/    symptom_templates.json (versioned demo checklists)
  app/samples/      bundled synthetic + ACI-Bench sample transcripts
  tests/            pytest suite (no live API calls)
frontend/           React + TypeScript + Vite
supabase/migrations/001_initial_schema.sql
scripts/            build_samples.py (datasets → samples), evaluate_aci.py (offline evaluation)
data/               dataset notes (raw datasets are git-ignored)
docs/               blueprint, implementation prompt, deployment guide
```

## Run locally

Prerequisites: Python 3.11+ (tested on 3.13) and Node.js 20+.

**Backend** (terminal 1):

```bash
cd backend
python3 -m venv .venv            # or: uv venv .venv --python 3.13
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # optional; defaults work without it
uvicorn app.main:app --reload --port 8000
```

Check it: <http://localhost:8000/api/health> → `{"status":"ok",...}`. API docs: <http://localhost:8000/docs>.

**Frontend** (terminal 2):

```bash
cd frontend
npm install
cp .env.example .env             # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:5173>, choose a sample, click **Load sample transcript**, then **Analyze consultation**.

### Demo mode vs Claude

- With no `ANTHROPIC_API_KEY`, the app runs in **demo mode**: a deterministic, rule-based provider (no AI, no network, no cost) that is clearly labelled in the UI. Its output goes through exactly the same validation.
- To use Claude, set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`, default `claude-opus-5-5`) in `backend/.env` and restart the backend. A provider selector then appears in the UI.
- API access is billed separately from a Claude.ai / Claude Code subscription. If the app reports an authentication or billing error, check the key and API billing in the Anthropic Console.

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

The 82 tests cover segmentation and stable IDs, exact and normalized quote validation, invalid segment IDs, speaker mismatch, duplicate fact IDs, negation and uncertain-dosage preservation, missing information never becoming a negative, every coverage formula rule (volunteered, asked but unanswered, not applicable, unclear/pending, not found, zero denominator), generated statements that cite unknown facts, a mocked LLM that fabricates a fact, prompt-injection text in a transcript, reviewer overrides with recalculation and persistence, the demo password gate, rate limiting, temporary-personnummer validation (real personnummer are rejected), patient-name detection, production-config checks, the reported regressions (missing items hidden as pending; review controls disappearing after a save), the 21-template registry, clinician statements, follow-up detection, English/Swedish meaning checks, the record explainer, and the Claude provider against a mocked HTTP transport (request shape, API errors, timeouts, malformed output). Tests never call the live API.

Frontend type check and build: `cd frontend && npm run build`.

## Datasets — how they are used

See also the in-app **Evaluation** page and [data/README.md](data/README.md).

- **ACI-Bench** (role-played consultations):
  - Four encounters are bundled as samples, with their human-written reference notes for comparison; the reference notes are also sample records for the record explainer.
  - `scripts/evaluate_aci.py` runs the full pipeline on all 207 human transcripts and the ASR transcripts, measuring traceability, validation outcomes, checklist coverage, follow-up gaps and agreement with the reference notes.
  - D2N114 (swapped speaker labels) demonstrates speaker-mismatch detection.
- **PLABA** (sentence-aligned plain-language adaptations): `scripts/evaluate_plaba.py` calibrates the meaning-change checks on 9,000+ human sentence pairs (false-alarm rate) and on deliberately corrupted rewrites (detection rate). A few pairs are style examples in the Claude prompts. Not used for training, by design.
- **Synthetic** transcripts (including your back-pain, knee-pain and stomach-pain cases) cover negation, uncertainty, unanswered questions, volunteered details, third-party speakers, embedded instructions, and an unexplored symptom.

Re-run the evaluations after changing the pipeline:

```bash
cd backend
.venv/bin/python -I ../scripts/evaluate_aci.py ../data/aci-bench-corpus        # writes app/evaluation/aci.json
.venv/bin/python -I ../scripts/evaluate_plaba.py ../data/rnpmf-osfstorage-archive  # writes app/evaluation/plaba.json
```

## Patient identity (synthetic)

Each analysis can carry a patient name and a **temporary personnummer** in the reserve-number style
`YYYYMMDD-TNNN` (e.g. `19850412-T123`). The letter `T` means it can never be a real Swedish personal identity
number. The app generates one automatically, shows the derived age, and **rejects real-looking personnummer**,
both in the patient field and inside transcripts. If no name is entered, it is detected from the clinician's
greeting and linked to the source segment.

## Safety and scope

- No diagnoses, treatment recommendations, triage, risk scores, or emergency advice. No clinician ranking.
- Checklist templates are labelled `demo_not_clinically_validated`. They are illustrative, not exhaustive, not mandatory, and not a standard of care.
- "Not found in transcript — review" never means the clinician failed, and it never means a symptom is absent.
- Transcript text is treated as untrusted data. The prompts tell the model to ignore instructions found inside it.
- Secrets live only in the backend environment. The only frontend variable is `VITE_API_BASE_URL`. Transcripts and prompts are never logged.
- Server-side protections: transcript size limit, per-IP rate limit, optional shared demo password, LLM timeout, and output-token cap.

## Project documents

- [Project Blueprint](docs/TRACECARE_PROJECT_BLUEPRINT.md)
- [Claude Code Master Prompt](docs/CLAUDE_IMPLEMENTATION_PROMPT.md)
- [Deploy on Vercel (step by step)](docs/DEPLOY_VERCEL.md)
- [Public MVP Deployment Guide (Railway / Render / Supabase details)](docs/DEPLOYMENT_GUIDE.md)
