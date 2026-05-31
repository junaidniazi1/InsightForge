# InsightForge — Local Setup

End-to-end walkthrough: create a Supabase project, run the schema, configure
both services, and verify Phase 1 (auth + upload + preview) works.

Estimated time: **~15 minutes**.

---

## 1. Create your Supabase project

1. Go to [supabase.com](https://supabase.com) → **New project**.
2. Pick a name (e.g. `insightforge`), a strong DB password (save it), and a region close to you. Free tier is fine for development.
3. Wait ~1–2 min for provisioning.

## 2. Run the schema

1. Open your project → **SQL Editor** (sidebar) → **New query**.
2. Paste the entire contents of [`supabase/migrations/0001_init.sql`](./supabase/migrations/0001_init.sql) into the editor.
3. Click **Run**. You should see "Success. No rows returned".
4. **For Phase 5 (AI cache):** run [`supabase/migrations/0002_ai_cache.sql`](./supabase/migrations/0002_ai_cache.sql) the same way. It adds the `ai_outputs` table used to cache Gemini summary/story/insights per dataset version.

This creates:

- All 9 tables (`profiles`, `datasets`, `dataset_versions`, `data_profiles`, `dashboards`, `charts`, `db_connections`, `ai_conversations`, `analysis_jobs`).
- **Row Level Security on every table**, scoped to `auth.uid()`.
- A private storage bucket named **`datasets`** with policies that confine each user to their own folder (`<user_id>/...`).
- A trigger that auto-creates a row in `profiles` when a user signs up.
- A trigger that auto-creates the first `dataset_versions` row (label `raw`) whenever a dataset is inserted.

## 3. Collect your Supabase credentials

Project → **Settings** → **API**:

| Value | Where you'll use it | Notes |
|-------|---------------------|-------|
| **Project URL** (`https://xxxx.supabase.co`) | frontend + backend | safe to expose |
| **anon public key** | frontend | safe to expose |
| **service_role secret key** | **backend only** | bypasses RLS — never put in the frontend |
| **JWT secret** (Settings → API → JWT Settings) | backend | used to verify user tokens |

## 4. Configure the backend

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```dotenv
SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_ANON_KEY=eyJ...               # public anon key
SUPABASE_SERVICE_ROLE_KEY=eyJ...       # service_role key — keep secret
SUPABASE_JWT_SECRET=...                # JWT secret (long random string)

# Anthropic — leave blank for Phase 1; needed from Phase 5 onward.
ANTHROPIC_API_KEY=
ANTHROPIC_DEFAULT_MODEL=claude-sonnet-4-6
ANTHROPIC_HEAVY_MODEL=claude-opus-4-7

CORS_ORIGINS=http://localhost:3000
MAX_UPLOAD_BYTES=209715200
```

Install + run:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check: open http://localhost:8000/health — should return `{"status":"ok"}`.

Run tests:

```bash
python -m pytest -v
```

## 5. Configure the frontend

```bash
cd ../frontend
cp .env.local.example .env.local
```

Edit `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Install + run:

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000.

## 6. Smoke-test Phase 1

1. **Sign up** with any email + password (≥8 chars).
   - If you left **Email confirmation** ON in Supabase Auth settings, you'll receive a confirmation link. Click it.
   - To skip email confirmation while developing: Supabase project → **Authentication** → **Providers** → **Email** → toggle off **Confirm email**.
2. After login you'll land on **/sources**.
3. **Upload a CSV** (anything reasonable — try a Kaggle dataset). The file uploads directly to Supabase Storage under `datasets/<your-user-id>/...`.
4. The app redirects to **/sources/[id]** and renders a paginated preview of the file. The preview is served by FastAPI (which downloads the file from Storage server-side using the service-role key and reads it with pandas).
5. Click **Prev / Next** to page through the rows.

### What you'll see in Supabase

- **Authentication → Users**: your new user.
- **Table Editor → profiles**: a row was auto-created by the signup trigger.
- **Table Editor → datasets**: one row per upload.
- **Table Editor → dataset_versions**: one `raw` version row per dataset (auto-created by trigger).
- **Storage → datasets**: your uploaded file under your user-id folder.

## Troubleshooting

- **"missing bearer token"** from FastAPI: the frontend didn't include the access token. Confirm `NEXT_PUBLIC_API_URL` matches the running backend and that you're logged in.
- **"invalid token"** from FastAPI: usually a mismatched `SUPABASE_JWT_SECRET`. Re-copy from Project Settings → API → JWT Settings.
- **CORS error** in browser console: make sure `CORS_ORIGINS` in `backend/.env` includes `http://localhost:3000`.
- **Upload fails with permission error**: confirm the `0001_init.sql` migration ran fully — the storage policies are at the bottom of the file.
- **Big Excel files**: openpyxl loads the whole sheet into memory. Phase 2 will switch large files to background jobs.

## Next

Phase 2 (Data Health engine) will add:

- A profiling endpoint that returns per-column stats, type issues, missing-data patterns, duplicates, outliers (IQR / Z-score / Isolation Forest), and a suggested fix for each issue.
- A "Data Health" page with toggles to accept/reject each suggestion.
