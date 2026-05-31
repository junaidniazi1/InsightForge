-- InsightForge initial schema
-- Run this in the Supabase SQL Editor (Project → SQL → New query → paste → Run).
-- It creates all tables, RLS policies, a private "datasets" storage bucket,
-- a profiles auto-create trigger, and a trigger that creates the "raw"
-- dataset_versions row when a dataset is inserted.

-- ---------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------
-- profiles  (1:1 with auth.users)
-- ---------------------------------------------------------------
create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  email       text,
  full_name   text,
  created_at  timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own"
  on public.profiles for select using (auth.uid() = id);
create policy "profiles_update_own"
  on public.profiles for update using (auth.uid() = id);
create policy "profiles_insert_self"
  on public.profiles for insert with check (auth.uid() = id);

-- Auto-create profile row on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', ''));
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------
-- datasets
-- ---------------------------------------------------------------
create table if not exists public.datasets (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,
  name          text not null,
  source_type   text not null check (source_type in ('file_csv','file_excel','db_connection')),
  storage_path  text,                       -- nullable for db_connection
  row_count     bigint,
  column_count  integer,
  status        text not null default 'uploaded'
                check (status in ('uploaded','profiling','profiled','cleaned','error')),
  created_at    timestamptz not null default now()
);

create index if not exists datasets_user_idx on public.datasets (user_id, created_at desc);

alter table public.datasets enable row level security;
create policy "datasets_select_own" on public.datasets for select using (auth.uid() = user_id);
create policy "datasets_insert_own" on public.datasets for insert with check (auth.uid() = user_id);
create policy "datasets_update_own" on public.datasets for update using (auth.uid() = user_id);
create policy "datasets_delete_own" on public.datasets for delete using (auth.uid() = user_id);

-- ---------------------------------------------------------------
-- dataset_versions
-- ---------------------------------------------------------------
create table if not exists public.dataset_versions (
  id              uuid primary key default gen_random_uuid(),
  dataset_id      uuid not null references public.datasets (id) on delete cascade,
  version_no      integer not null,
  label           text not null check (label in ('raw','cleaned')),
  storage_path    text,
  cleaning_steps  jsonb not null default '[]'::jsonb,
  created_at      timestamptz not null default now(),
  unique (dataset_id, version_no)
);

create index if not exists dataset_versions_dataset_idx
  on public.dataset_versions (dataset_id, version_no desc);

alter table public.dataset_versions enable row level security;

create policy "dataset_versions_select_own"
  on public.dataset_versions for select using (
    exists (select 1 from public.datasets d
            where d.id = dataset_versions.dataset_id and d.user_id = auth.uid())
  );
create policy "dataset_versions_insert_own"
  on public.dataset_versions for insert with check (
    exists (select 1 from public.datasets d
            where d.id = dataset_versions.dataset_id and d.user_id = auth.uid())
  );
create policy "dataset_versions_update_own"
  on public.dataset_versions for update using (
    exists (select 1 from public.datasets d
            where d.id = dataset_versions.dataset_id and d.user_id = auth.uid())
  );

-- Auto-create the v1 "raw" version row when a dataset is inserted
create or replace function public.handle_new_dataset()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.dataset_versions (dataset_id, version_no, label, storage_path)
  values (new.id, 1, 'raw', new.storage_path);
  return new;
end;
$$;

drop trigger if exists on_dataset_created on public.datasets;
create trigger on_dataset_created
  after insert on public.datasets
  for each row execute function public.handle_new_dataset();

-- ---------------------------------------------------------------
-- data_profiles
-- ---------------------------------------------------------------
create table if not exists public.data_profiles (
  id                   uuid primary key default gen_random_uuid(),
  dataset_version_id   uuid not null references public.dataset_versions (id) on delete cascade,
  profile_json         jsonb not null,
  created_at           timestamptz not null default now()
);

alter table public.data_profiles enable row level security;

create policy "data_profiles_select_own"
  on public.data_profiles for select using (
    exists (
      select 1 from public.dataset_versions v
      join public.datasets d on d.id = v.dataset_id
      where v.id = data_profiles.dataset_version_id and d.user_id = auth.uid()
    )
  );
create policy "data_profiles_insert_own"
  on public.data_profiles for insert with check (
    exists (
      select 1 from public.dataset_versions v
      join public.datasets d on d.id = v.dataset_id
      where v.id = data_profiles.dataset_version_id and d.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------
-- dashboards + charts
-- ---------------------------------------------------------------
create table if not exists public.dashboards (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  dataset_id  uuid not null references public.datasets (id) on delete cascade,
  name        text not null,
  layout      jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

alter table public.dashboards enable row level security;
create policy "dashboards_all_own" on public.dashboards
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table if not exists public.charts (
  id            uuid primary key default gen_random_uuid(),
  dashboard_id  uuid not null references public.dashboards (id) on delete cascade,
  chart_type    text not null,
  config        jsonb not null default '{}'::jsonb,
  position      integer not null default 0
);

alter table public.charts enable row level security;
create policy "charts_all_own" on public.charts
  for all using (
    exists (select 1 from public.dashboards d
            where d.id = charts.dashboard_id and d.user_id = auth.uid())
  )
  with check (
    exists (select 1 from public.dashboards d
            where d.id = charts.dashboard_id and d.user_id = auth.uid())
  );

-- ---------------------------------------------------------------
-- db_connections (credentials encrypted by the backend before insert)
-- ---------------------------------------------------------------
create table if not exists public.db_connections (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users (id) on delete cascade,
  name                   text not null,
  db_type                text not null check (db_type in ('postgres','mysql')),
  host                   text not null,
  port                   integer not null,
  database               text not null,
  username               text not null,
  encrypted_credentials  bytea not null,
  created_at             timestamptz not null default now()
);

alter table public.db_connections enable row level security;
create policy "db_connections_all_own" on public.db_connections
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------
-- ai_conversations
-- ---------------------------------------------------------------
create table if not exists public.ai_conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  dataset_id  uuid references public.datasets (id) on delete cascade,
  role        text not null check (role in ('user','assistant','system')),
  content     text not null,
  created_at  timestamptz not null default now()
);

create index if not exists ai_conv_user_dataset_idx
  on public.ai_conversations (user_id, dataset_id, created_at);

alter table public.ai_conversations enable row level security;
create policy "ai_conversations_all_own" on public.ai_conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------
-- analysis_jobs
-- ---------------------------------------------------------------
create table if not exists public.analysis_jobs (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users (id) on delete cascade,
  dataset_id   uuid references public.datasets (id) on delete cascade,
  job_type     text not null,
  status       text not null default 'queued'
               check (status in ('queued','running','succeeded','failed')),
  result_json  jsonb,
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists analysis_jobs_user_idx
  on public.analysis_jobs (user_id, created_at desc);

alter table public.analysis_jobs enable row level security;
create policy "analysis_jobs_select_own" on public.analysis_jobs
  for select using (auth.uid() = user_id);
-- Inserts/updates happen from the backend with the service-role key, which bypasses RLS.

-- ---------------------------------------------------------------
-- Storage bucket  (private; objects keyed by <user_id>/<dataset_id>/...)
-- ---------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('datasets', 'datasets', false)
on conflict (id) do nothing;

-- Users can read/write only inside their own folder: first path segment == auth.uid()
create policy "datasets_storage_select_own"
  on storage.objects for select
  using (bucket_id = 'datasets' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "datasets_storage_insert_own"
  on storage.objects for insert
  with check (bucket_id = 'datasets' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "datasets_storage_update_own"
  on storage.objects for update
  using (bucket_id = 'datasets' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "datasets_storage_delete_own"
  on storage.objects for delete
  using (bucket_id = 'datasets' and (storage.foldername(name))[1] = auth.uid()::text);
