# InsightForge

AI-powered data analysis & dashboard platform. Bring a CSV, Excel file, or a
live database connection — InsightForge profiles the data, suggests a fix for
every quality issue, auto-builds a dashboard, and lets you "ask your data" in
plain English (powered by Gemini).

> **Status: Phase 8 of 8.** Everything through Phase 7 plus auth hardening
> (JWKS), live database connectors (Postgres / MySQL / SQLite), and encrypted
> credential storage.

---

## Architecture

```
┌──────────────────┐        ┌────────────────────┐        ┌──────────────────┐
│   Next.js (TS)   │  REST  │     FastAPI        │  REST  │  Anthropic API   │
│   App Router     ├───────►│   (pandas, numpy,  ├───────►│  /v1/messages    │
│   Tailwind v4    │  JWT   │    scikit-learn,   │        │  (Claude)        │
│                  │        │     statsmodels)   │        │                  │
└────────┬─────────┘        └──────────┬─────────┘        └──────────────────┘
         │ Supabase JS                 │ Supabase REST + Storage
         │ (auth + storage + RLS db)   │ (service-role key)
         ▼                             ▼
   ┌────────────────────────────────────────────┐
   │             Supabase (managed)             │
   │  Postgres · Auth · Storage  (RLS enabled)  │
   └────────────────────────────────────────────┘
```

Two services:

- **`frontend/`** — Next.js 15 (App Router) + React 19 + TS + Tailwind v4.
  Talks to **Supabase** for auth, storage, and app data, and to **FastAPI** for
  all analysis.
- **`backend/`** — FastAPI + pandas (Phase 6 adds scipy, scikit-learn,
  statsmodels). Verifies Supabase user JWTs via JWKS (RS256/ES256) with an
  HS256 fallback for legacy projects, pulls files from Storage, and runs every
  analytics endpoint. From Phase 5 onward this is also the only service that
  calls the Gemini API.

The **Supabase service-role key**, **Claude API key**, and any **DB credentials**
live in the backend's `.env` and never reach the browser.

## Repo layout

```
.
├── README.md
├── SETUP.md                       ← step-by-step setup
├── supabase/
│   └── migrations/
│       └── 0001_init.sql          ← schema, RLS, storage bucket
├── frontend/                      ← Next.js
│   ├── package.json
│   ├── src/
│   │   ├── app/                   ← pages + route handlers
│   │   ├── components/
│   │   ├── lib/supabase/          ← browser / server / middleware clients
│   │   └── middleware.ts          ← session refresh + auth gate
│   └── .env.local.example
└── backend/                       ← FastAPI
    ├── requirements.txt
    ├── app/
    │   ├── main.py
    │   ├── config.py              ← pydantic-settings
    │   ├── deps.py                ← JWT auth dependency
    │   ├── supabase_client.py     ← REST + Storage client
    │   ├── routers/
    │   ├── schemas/
    │   └── services/
    ├── tests/                     ← pytest
    └── .env.example
```

## Quick start

See [SETUP.md](./SETUP.md) for the full walkthrough. TL;DR:

1. Create a Supabase project; run `supabase/migrations/0001_init.sql` in the SQL editor.
2. Copy `backend/.env.example` → `backend/.env` and fill in your Supabase keys.
3. Copy `frontend/.env.local.example` → `frontend/.env.local`.
4. **Backend:**
   ```bash
   cd backend
   python -m venv .venv && .venv/Scripts/activate     # Windows
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
5. **Frontend:**
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```
6. Open http://localhost:3000 → sign up → upload a CSV.

## Build phases

| Phase | Scope | Status |
|------:|-------|--------|
| 1 | Auth · upload · paginated preview · schema + RLS | **✓ done** |
| 2 | Data Health engine: profile + issues + 3 outlier methods + accept-fix UI | **✓ done** |
| 3 | Cleaning hub: 30+ ops, manual toolbox + live preview, pipeline editor, before/after diff, re-profile | **✓ done** |
| 4 | Auto-dashboard: chart recommender + Plotly/ECharts router + KPIs + global filters + grid + save/load | **✓ done** |
| 5 | AI Layer (Gemini): summary, data story, auto-insights, Ask-Your-Data with plan/validate/execute/explain | **✓ done** |
| 6 | Standalone CSV/XLSX download · Auto-clean agent · Chart editing · PDF report export | **✓ done** |
| 7 | Analyst Workbench (stats, hypothesis tests, time-series, clustering, PCA, anomaly, feature importance, baseline modelling) | **✓ done** |
| 8A | Auth hardening (JWKS + HS256 fallback) · README privacy note | **✓ done** |
| 8B | Live database connectors (Postgres / MySQL / SQLite) with encrypted credentials, SSRF guard, read-only enforcement, import wizard | **✓ done** |

## Data & Privacy

InsightForge takes data privacy seriously. Here's what you should know:

### Where your data lives

- **Uploaded files** are stored in a **private** Supabase Storage bucket scoped
  to your user ID via Row-Level Security (RLS). No other user can read, list, or
  modify your files.
- **Structured metadata** (dataset names, profiles, dashboards, cleaning
  history) lives in Supabase Postgres, also protected by RLS.
- **Database connection credentials** (Phase 8B) are encrypted at rest with
  Fernet symmetric encryption before being written to the database. The
  encryption key (`DB_ENCRYPTION_KEY`) is a backend-only env var and never
  leaves the server. Plaintext passwords are **never** stored and **never**
  returned from any API endpoint.

### What the AI layer receives

The Gemini-powered AI features (summary, data story, auto-insights,
Ask-Your-Data) **never see your raw data rows**. The backend's `ai_context`
module builds a privacy-safe payload containing only:

- Column names and data types
- Summary statistics (mean, median, min, max, std, null counts)
- Correlation pairs
- KPI suggestions
- The cleaning-step log

This is enforced in code and covered by automated tests (`test_ai.py`). The AI
receives enough metadata to reason about your data without ever seeing the
actual values.

### Free-tier Gemini note

If you are using the **free tier** of the Gemini API, Google may use your
prompts to improve their models (see
[Google's Terms of Service](https://ai.google.dev/gemini-api/terms)). Because
InsightForge sends only schema and aggregate statistics — never raw data — this
is generally low-risk. If your dataset *schema itself* is sensitive (e.g.,
column names reveal confidential project details), consider:

- Upgrading to a **paid Gemini API tier** (prompts are not used for training).
- Using **Vertex AI** as the backend (enterprise data handling).

### Where secrets live

All secrets are backend-only environment variables:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini AI calls |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase admin access (bypasses RLS) |
| `DB_ENCRYPTION_KEY` | Fernet key for encrypting DB connection passwords |
| `SUPABASE_JWT_SECRET` | Legacy HS256 fallback (optional for new projects) |

These are **never** bundled into the frontend, never committed to git, and
never exposed in any API response.

### How to disable AI entirely

Unset (or leave blank) the `GEMINI_API_KEY` environment variable. The rest of
the application — upload, profiling, cleaning, dashboards, workbench, database
connectors — continues to work normally. AI endpoints will return a clear
"AI unavailable" message.

---

## Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest -v
```

Phase 1 ships unit tests for the data-loader (CSV parse, pagination, NaN/Inf JSON-safety).
Phase 2 adds 19 tests for the profiler (each issue type detected, three outlier methods reported as separate groups, quality score behaves).
Phase 3 adds 36 tests for the cleaner (every category covered, dispatcher safety, diff correctness, Phase-2 fix-string coverage).
Phase 4 adds 27 tests for the chart recommender + chart-data aggregation + engine map.
Phase 5 adds 26 tests for the AI layer (ai_context privacy contract, Gemini backoff, Ask-Your-Data validation + execution, missing-key path). Gemini is fully mocked — no network calls in tests.
Phase 6 adds 16 tests for the auto-clean agent (every issue type mapped to the right fix, no auto-row-removal for outliers, deterministic ordering, plan runs end-to-end through `apply_steps`).
Phase 7 adds 25 stats tests (7A: describe / correlation / 5 hypothesis tests with assumption checks / time-series decompose+ADF) and 19 ML tests (7B: clustering recovers blobs / PCA captures correlated variance / Isolation Forest flags injected anomalies / RF feature importance ranks true driver / linear regression R² > 0.9 / separable classification accuracy > 0.9 / predictions CSV round-trips).
Phase 8A adds 10 auth tests (JWKS verification with mocked RSA key, tampered/expired/wrong-audience rejection, legacy HS256 path, fallback when JWKS unavailable).
Phase 8B adds connector tests (crypto round-trip, SSRF guard, SQL validator, SQLite integration for list/describe/import/query).
Total **190+** passing.
