# Deploying TraceCare on Vercel (step by step)

This guide puts the whole app online on Vercel. You end up with two Vercel projects built from the same GitHub
repository, plus a managed PostgreSQL database:

| Piece | Where | Root directory | Public URL (example) |
|---|---|---|---|
| Frontend (React + Vite) | Vercel project `tracecare` | `frontend` | `https://tracecare.vercel.app` |
| Backend (FastAPI) | Vercel project `tracecare-api` | `backend` | `https://tracecare-api.vercel.app` |
| Database (PostgreSQL) | Supabase (or Neon from the Vercel Marketplace) | — | — |
| Claude API | Anthropic, called only by the backend | — | — |

Why two projects: Vercel auto-detects FastAPI at `backend/app/main.py` and runs it as a single Vercel Function.
The single-project alternative ("Services") is still in Beta, so two projects is the stable option.
Vercel's filesystem must not be used for data, so SQLite only works locally and production needs PostgreSQL.

> The public demo is for **synthetic / role-played data only**. HTTPS, an EU database region, or a password do
> not make it suitable for real patient data.

---

## What you need to provide

These are the things only you can do (accounts, secrets, and clicks in dashboards):

- [ ] A **GitHub** account and a new repository for this project.
- [ ] A **Vercel** account (Hobby is enough), connected to GitHub.
- [ ] A **Supabase** account (free tier is enough), or Neon from the Vercel Marketplace.
- [ ] An **Anthropic API key** with API billing enabled in Anthropic Console (separate from a Claude subscription).
      Optional: without it, the app runs in demo (rule-based) mode.
- [ ] A **SESSION_SECRET**: generate one (see Step 3).
- [ ] Optional: a **DEMO_ACCESS_PASSWORD** to share with judges (protects your API credit).
- [ ] After deploying: fill in the two URLs in the root `README.md`.

---

## Step 1 — Put the code on GitHub

The folder is not a git repository yet. From the project root:

```bash
cd "tracecare_starter_pack 2"
git init -b main
git add .
git status            # check: no .env, no *.db, no data/aci-bench-corpus, no node_modules, no .venv
git commit -m "TraceCare MVP"
git remote add origin https://github.com/<you>/tracecare.git
git push -u origin main
```

`.gitignore` already excludes `.env` files (including `backend/.env`, which holds your API key), local databases,
virtual environments, `node_modules`, build output and the raw datasets. Check `git status` before you commit anyway.

## Step 2 — Create the database (Supabase)

1. In Supabase choose **New project**. Pick an EU region (e.g. Stockholm `eu-north-1` or Frankfurt) and a strong
   database password.
2. Open **SQL Editor** and run, in order:
   - `supabase/migrations/001_initial_schema.sql`
   - `supabase/migrations/002_rate_limits_and_retention.sql`
   (The backend would also create the tables itself on first use. Running the migrations additionally enables
   Row Level Security and blocks the public Data API.)
3. Click **Connect**, then **Connection string**, and copy the **Transaction pooler** URI (port **6543**). This is
   the right mode for serverless functions, and the backend is configured for it (prepared statements disabled,
   no idle pool). It looks like:
   `postgresql://postgres.<project-ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:6543/postgres`
   Append `?sslmode=require`. This full string is your `DATABASE_URL`.

*Neon alternative:* in Vercel go to **Storage → Marketplace → Neon** and connect it to the backend project. It
injects a connection string into the project's environment variables. Make sure a variable named `DATABASE_URL`
holds the **pooled** connection string. Neon does not need the Supabase SQL files: the backend creates its tables.

## Step 3 — Deploy the backend (FastAPI) on Vercel

1. Vercel dashboard: **Add New… → Project**, then import your GitHub repository.
2. **Project name:** `tracecare-api`. **Root Directory:** click *Edit* and choose `backend`.
   **Framework Preset:** FastAPI (auto-detected from `app/main.py`; choose *Other* if it is not offered).
   Leave the build command empty.
3. Open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `SERVERLESS` | `true` |
   | `DATABASE_URL` | the pooled connection string from Step 2 |
   | `SESSION_SECRET` | output of `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `ANTHROPIC_API_KEY` | your key (optional; omit for demo-only mode) |
   | `ANTHROPIC_MODEL` | e.g. `claude-sonnet-5-5` or `claude-opus-5-5` |
   | `CORS_ORIGINS` | temporarily `https://example.invalid`; you set the real frontend URL in Step 5 |
   | `DEMO_MODE_ENABLED` | `true` (keeps the free demo engine available as a fallback) |
   | `DEMO_ACCESS_PASSWORD` | optional shared password for judges |
   | `ANALYSIS_RATE_LIMIT` | `20/hour` |
   | `MAX_TRANSCRIPT_CHARS` | `30000` |
   | `ENCOUNTER_RETENTION_DAYS` | `7` |

4. Click **Deploy**. Python 3.13 comes from `backend/.python-version`, dependencies from `requirements.txt`, and
   `backend/vercel.json` sets the function's max duration to 300 s (the Hobby maximum). A Claude analysis
   usually takes 20–90 s.
5. Test it, using the URL Vercel shows (e.g. `https://tracecare-api.vercel.app`):
   - `https://tracecare-api.vercel.app/api/health` should return `{"status":"ok",...}`
   - `https://tracecare-api.vercel.app/api/ready` should return `"status":"ready"` with an empty `config_problems`.
     If it says `misconfigured`, the listed problems name exactly which variable to fix (values are never shown).

## Step 4 — Deploy the frontend (React) on Vercel

1. **Add New… → Project**, then import the **same** repository again.
2. **Project name:** `tracecare`. **Root Directory:** `frontend`. **Framework Preset:** Vite (build
   `npm run build`, output `dist`, both already set in `frontend/vercel.json`).
3. Environment variable: `VITE_API_BASE_URL` = `https://tracecare-api.vercel.app` (your backend URL, no trailing
   slash). This is public and not a secret. Never put keys in `VITE_` variables.
4. **Deploy.** `frontend/vercel.json` also sets security headers (CSP, frame blocking, no-referrer, noindex) and
   long-term caching for hashed assets.

## Step 5 — Connect the two (CORS)

1. Backend project → **Settings → Environment Variables** → set `CORS_ORIGINS` to the exact frontend URL, e.g.
   `https://tracecare.vercel.app` (comma-separate several origins, such as a custom domain).
2. Backend project → **Deployments** → open the latest deployment's **⋯** menu → **Redeploy**. Environment
   variable changes only apply to new deployments.

## Step 6 — Smoke test the live app

1. Open the frontend URL in a private window. If you set a demo password, enter it.
2. Load the sample "Synthetic: low back pain (Lisa)" and analyse it with **Claude**. Expect coverage 8 / 9 with
   **Onset** "Not found — review".
3. Click a fact badge: the evidence panel shows the highlighted quote.
4. Coverage tab → **Review** an item → save. The metrics recalculate and the row shows "Reviewed". Reload the page:
   the saved encounter and your review are still there.
5. Try a transcript containing a real-looking personnummer such as `850412-1234`: it must be rejected.
6. From a terminal, check that another origin is blocked:
   ```bash
   curl -s -i -X OPTIONS https://tracecare-api.vercel.app/api/analyze \
     -H 'Origin: https://example.com' -H 'Access-Control-Request-Method: POST' | grep -i access-control-allow-origin \
     || echo "blocked (good)"
   ```
7. Put both URLs in the root `README.md` (`PUBLIC_DEMO_URL`, `PUBLIC_API_URL`) and push. Vercel redeploys
   automatically on every push to `main`.

---

## Operations

- **Logs:** each Vercel project → *Logs*. The backend logs encounter IDs, counts, and error types only: never
  transcripts, prompts, keys, or connection strings.
- **Costs:** set a monthly spend limit in Anthropic Console. The server-side rate limit (`ANALYSIS_RATE_LIMIT`,
  stored in the database so it works across serverless instances) and the optional demo password protect your
  API credit.
- **Data:** encounters are deleted automatically after `ENCOUNTER_RETENTION_DAYS`. Users can also delete one from
  the UI. To wipe everything, run `truncate table public.encounters;` in the Supabase SQL editor.
- **Preview deployments:** pull requests get preview URLs, but the backend's `CORS_ORIGINS` only allows the
  production frontend. Add a preview URL temporarily if you need to test one.
- **Cold starts:** the first request after idle time can take a few seconds longer.
- **Rollback:** Deployments → choose a previous deployment → *Promote to Production*.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Frontend shows "Could not reach the TraceCare API" | `VITE_API_BASE_URL` missing or wrong (redeploy the frontend after changing it), or `CORS_ORIGINS` on the backend does not contain the exact frontend origin (redeploy the backend). |
| `/api/ready` returns 503 "Database not reachable" | Wrong `DATABASE_URL`, password, or missing `?sslmode=require`. Use the pooler URL (IPv4), not the direct `db.<ref>.supabase.co` host. |
| Results are not saved / "Review unavailable" | The database is not reachable (see above); analysis still works but nothing is stored. |
| "Claude API authentication failed" | Key wrong, or API billing not active in Anthropic Console. Demo mode still works. |
| Request ends after ~300 s | Hobby function limit. Use a shorter transcript, a faster model, or `ANTHROPIC_EFFORT=low`. Pro allows up to 800 s (raise `maxDuration` in `backend/vercel.json`). |
| 401 on every analysis | `DEMO_ACCESS_PASSWORD` is set: log in on the start page. Sessions last 8 hours and are signed with `SESSION_SECRET`. Changing the secret logs everyone out. |

## Alternative: one Vercel project (Beta)

Vercel **Services** can serve the frontend and the FastAPI backend from a single project and domain (no CORS),
using a root `vercel.json` with `services` and `/api/(.*)` rewrites. It is labelled Beta, so this guide uses the
two-project setup. Re-check the Services documentation before switching.
