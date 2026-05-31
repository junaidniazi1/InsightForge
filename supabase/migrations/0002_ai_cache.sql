-- Phase 5: AI outputs cache
-- Caches Gemini-generated summary / story / insights per dataset_version so we
-- don't burn free-tier quota on every page load. Each row is unique per
-- (version, type). Refresh = upsert.

create table if not exists public.ai_outputs (
  id                   uuid primary key default gen_random_uuid(),
  dataset_version_id   uuid not null references public.dataset_versions (id) on delete cascade,
  output_type          text not null check (output_type in ('summary','story','insights')),
  content              jsonb not null,
  created_at           timestamptz not null default now(),
  unique (dataset_version_id, output_type)
);

create index if not exists ai_outputs_version_idx
  on public.ai_outputs (dataset_version_id);

alter table public.ai_outputs enable row level security;

-- Readable by whoever owns the underlying dataset.
create policy "ai_outputs_select_own"
  on public.ai_outputs for select
  using (
    exists (
      select 1
      from public.dataset_versions v
      join public.datasets d on d.id = v.dataset_id
      where v.id = ai_outputs.dataset_version_id and d.user_id = auth.uid()
    )
  );

-- Writes go through the backend (service-role bypasses RLS), but the policy
-- exists so the table is fully RLS-covered.
create policy "ai_outputs_insert_own"
  on public.ai_outputs for insert
  with check (
    exists (
      select 1
      from public.dataset_versions v
      join public.datasets d on d.id = v.dataset_id
      where v.id = ai_outputs.dataset_version_id and d.user_id = auth.uid()
    )
  );

create policy "ai_outputs_update_own"
  on public.ai_outputs for update
  using (
    exists (
      select 1
      from public.dataset_versions v
      join public.datasets d on d.id = v.dataset_id
      where v.id = ai_outputs.dataset_version_id and d.user_id = auth.uid()
    )
  );
