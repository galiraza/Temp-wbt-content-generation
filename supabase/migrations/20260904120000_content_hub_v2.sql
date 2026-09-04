-- ============================================================================
-- WBT Content Hub — schema v2, step 2 of 2: tables, indexes, functions, triggers
--
-- Run 20260904115900_content_hub_v2_enums.sql FIRST.
--
-- Target shape, per the agreed rules:
--
--   1. One asset = one item. It carries ONE content stream and ONE image
--      stream, each with its own independent version counter.
--   2. All content source and fields for a version live in a single jsonb
--      column (`cg_asset_versions.data`). Fields promoted to real columns are
--      GENERATED from it, so there is never a second source of truth.
--   3. Regeneration:
--        image   <- the asset's ACTIVE content version (never a stored copy)
--        content <- the ACTIVE run's `source`, sliced for that section
--      `cg_asset_versions.source_run_id` records which run's brief produced a
--      version, so provenance survives a newer run.
--   4. Generation is per asset, not per run: `cg_asset_jobs` is the unit of
--      work, so assets fan out in parallel and retry individually.
--
-- Safe to run on a fresh project AND on the live DB (aydgxlvtsvetqyumesyw).
-- Every step is guarded, so re-running is a no-op.
--
-- NOTE ON ALEMBIC: the live DB is stamped `e938358a61e8`, a revision absent
-- from alembic/versions/. Resolve that stamp before adding an Alembic revision
-- on top of this file — this migration is applied as SQL, not through Alembic.
-- ============================================================================

begin;

-- ----------------------------------------------------------------- functions

-- updated_at is set by trigger, never by the ORM: duplicating it in Python
-- would let a direct SQL edit and an ORM edit disagree.
create or replace function cg_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Reading an int out of the jsonb payload without letting a bad value break
-- the insert. Declared immutable so GENERATED columns can call it.
create or replace function cg_jsonb_int(payload jsonb, key text)
returns int
language plpgsql
immutable
as $$
begin
  return nullif(payload ->> key, '')::int;
exception when others then
  return null;
end;
$$;


-- --------------------------------------------------------------------- tables

-- Command HQ owns the client list; rows are never created through the API.
create table if not exists cg_clients (
  client_id           uuid primary key,
  client_name         text not null,
  client_organization uuid null,
  last_run_at         timestamptz null,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- One generation request, for one client and one content type.
create table if not exists cg_runs (
  run_id       uuid primary key default gen_random_uuid(),
  client_id    uuid not null references cg_clients(client_id) on delete cascade,
  content_type cg_content_type not null,
  version      int not null,
  status       cg_run_status not null default 'pending',

  -- The FROZEN brief. jsonb because its shape genuinely differs per content
  -- type, and because a run must stay reproducible after HQ's record changes
  -- underneath it. Copying the brief in at request time is what makes the
  -- version history mean anything.
  source       jsonb not null default '{}',

  period       text null,
  summary      text null,
  requested_by text null,
  error_message text null,
  started_at   timestamptz null,
  completed_at timestamptz null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),

  constraint cg_runs_version_uq unique (client_id, content_type, version),
  constraint cg_runs_period_ck check (period is null or period ~ '^\d{4}-\d{2}$')
);

-- client_name is GENERATED — Postgres rejects any INSERT/UPDATE naming it.
-- Map it with FetchedValue(); never include it in a write.
alter table cg_runs
  add column if not exists client_name text
  generated always as (source ->> 'client_name') stored;

alter table cg_runs add column if not exists error_message text null;
alter table cg_runs add column if not exists started_at   timestamptz null;
alter table cg_runs add column if not exists completed_at timestamptz null;

-- One generated item: a page group, post, reel, blog, logo, ad.
-- No content_type here — it lives on the run. No `type` either: an asset is the
-- item, and content vs image is a property of its versions.
create table if not exists cg_assets (
  asset_id   uuid primary key default gen_random_uuid(),
  run_id     uuid not null references cg_runs(run_id) on delete cascade,
  -- denormalised off the run so client-scoped queries need no join
  client_id  uuid not null references cg_clients(client_id) on delete cascade,
  section    cg_section not null,
  position   int not null default 0,
  title      text null,
  slug       text null,
  status     cg_asset_status not null default 'review',
  error_message text null,
  approved_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Two active pointers, because the two streams version independently.
-- There is still NO display_version: which version a card previews is UI state,
-- and this table has no per-user scoping, so storing it would mean one person
-- previewing an older version changed what everyone else saw.
alter table cg_assets add column if not exists active_content_version int not null default 1;
alter table cg_assets add column if not exists active_image_version   int null;
alter table cg_assets add column if not exists error_message          text null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'cg_assets_active_content_ck') then
    alter table cg_assets add constraint cg_assets_active_content_ck
      check (active_content_version > 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'cg_assets_active_image_ck') then
    alter table cg_assets add constraint cg_assets_active_image_ck
      check (active_image_version is null or active_image_version > 0);
  end if;
end $$;

-- One state of one stream of an asset, kept forever.
create table if not exists cg_asset_versions (
  asset_id   uuid not null references cg_assets(asset_id) on delete cascade,
  version    int not null,
  body       text null,       -- text content
  file_path  text null,       -- Supabase Storage path, for image/video
  created_at timestamptz not null default now()
);

alter table cg_asset_versions add column if not exists kind cg_asset_kind not null default 'content';

-- THE single jsonb column: all content source and fields for this version.
--   blog    meta_title, meta_description, general_notes, gmb_post, gmb_faq,
--           funnel_stage, service_areas[], keywords[], qc_score, qc_breakdown,
--           qc_fixes[], revision_attempts, word_count
--   social  hashtags[], name, review, theme
--   website subtitle, word_count, passes
--   media   slot_label, aspect_ratio, duration_seconds, layout_variant
alter table cg_asset_versions add column if not exists data jsonb not null default '{}';

-- Which run's `source` produced this version. Regeneration reads the ACTIVE
-- run, which may be newer than the run that first created the asset, so origin
-- (cg_assets.run_id) and provenance (this) are not the same question.
alter table cg_asset_versions
  add column if not exists source_run_id uuid null references cg_runs(run_id) on delete set null;

alter table cg_asset_versions add column if not exists created_by text null;

-- Promoted from `data` for list views. GENERATED, so the jsonb stays the only
-- place either value is written — same treatment as cg_runs.client_name.
alter table cg_asset_versions
  add column if not exists word_count int generated always as (cg_jsonb_int(data, 'word_count')) stored;
alter table cg_asset_versions
  add column if not exists qc_score int generated always as (cg_jsonb_int(data, 'qc_score')) stored;


-- ---- version PK: (asset_id, kind, version) --------------------------------
-- The version number is the identity within a stream. A surrogate id would let
-- two rows claim version 3 of the same asset's content.
do $$
begin
  -- the chat FK points at the old PK, so it goes first
  if exists (select 1 from pg_constraint where conname = 'cg_asset_chats_asset_id_version_fkey') then
    alter table cg_asset_chats drop constraint cg_asset_chats_asset_id_version_fkey;
  end if;

  if exists (
    select 1 from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    where t.relname = 'cg_asset_versions' and c.contype = 'p'
      and array_length(c.conkey, 1) = 2
  ) then
    alter table cg_asset_versions drop constraint cg_asset_versions_pkey;
  end if;

  if not exists (
    select 1 from pg_constraint c
    join pg_class t on t.oid = c.conrelid
    where t.relname = 'cg_asset_versions' and c.contype = 'p'
  ) then
    alter table cg_asset_versions add primary key (asset_id, kind, version);
  end if;

  if not exists (select 1 from pg_constraint where conname = 'cg_asset_versions_version_ck') then
    alter table cg_asset_versions add constraint cg_asset_versions_version_ck check (version > 0);
  end if;

  -- An image version with no file is meaningless; content is free-form because
  -- a row may exist while its generation is still running.
  if not exists (select 1 from pg_constraint where conname = 'cg_asset_versions_media_ck') then
    alter table cg_asset_versions add constraint cg_asset_versions_media_ck
      check (kind = 'content' or file_path is not null);
  end if;
end $$;


-- The refinement conversation, threaded per VERSION of one STREAM.
-- Per asset would be the obvious choice and it is the wrong one: every message
-- is about a specific piece of text or a specific image, so a thread that
-- outlives what it discusses reads as a conversation about content nobody can
-- see any more.
create table if not exists cg_asset_chats (
  message_id uuid primary key default gen_random_uuid(),
  asset_id   uuid not null,
  version    int not null,
  body       text not null,
  created_at timestamptz not null default now()
);

alter table cg_asset_chats add column if not exists kind cg_asset_kind not null default 'content';
-- v1 had no `role`, on the reasoning that every row was something a person
-- typed. The chat now has assistant turns, each carrying an approvable
-- candidate — {title, body, hashtags} for copy, {file_path} for an image —
-- and approving one INSERTs a new version.
alter table cg_asset_chats add column if not exists role cg_chat_role not null default 'user';
alter table cg_asset_chats add column if not exists proposal jsonb null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'cg_asset_chats_version_fkey') then
    alter table cg_asset_chats
      add constraint cg_asset_chats_version_fkey
      foreign key (asset_id, kind, version)
      references cg_asset_versions (asset_id, kind, version) on delete cascade;
  end if;
end $$;


-- The unit of work for parallel, per-asset generation. One row per attempt at
-- one stream of one asset, so a fan-out is trackable and a single asset retries
-- without re-running its nineteen siblings.
create table if not exists cg_asset_jobs (
  job_id        uuid primary key default gen_random_uuid(),
  asset_id      uuid not null references cg_assets(asset_id) on delete cascade,
  run_id        uuid not null references cg_runs(run_id) on delete cascade,
  kind          cg_asset_kind not null default 'content',
  status        cg_job_status not null default 'queued',
  attempt       int not null default 1,

  -- Which run's source this attempt read, and the slice of it actually passed
  -- to the prompt. Storing the slice is what makes a failed generation
  -- reproducible without replaying the whole intake phase.
  source_run_id uuid null references cg_runs(run_id) on delete set null,
  instructions  jsonb not null default '{}',

  -- Set on success: the version this attempt produced.
  result_version int null,

  error_message text null,
  started_at    timestamptz null,
  finished_at   timestamptz null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  constraint cg_asset_jobs_attempt_ck check (attempt > 0)
);


-- How many items a run produces for one section. Two levels in one table:
-- a NULL client_id is the house default.
create table if not exists cg_section_defaults (
  client_id  uuid null references cg_clients(client_id) on delete cascade,
  section    cg_section not null,
  item_count int not null,
  updated_at timestamptz not null default now(),
  constraint cg_section_defaults_count_ck check (item_count between 1 and 50)
);

-- Postgres treats NULLs as distinct in a unique constraint, so this needs two
-- PARTIAL unique indexes rather than one.
create unique index if not exists cg_section_defaults_global_uq
  on cg_section_defaults (section) where client_id is null;
create unique index if not exists cg_section_defaults_client_uq
  on cg_section_defaults (client_id, section) where client_id is not null;


-- Prompt templates, addressed per (content_type, section, kind) so generation
-- is one asset per call instead of one action that writes everything.
-- `input_keys` names the run-source keys a template needs, which is what lets
-- the dispatcher build `cg_asset_jobs.instructions` without hard-coding a slice
-- per section in Python.
create table if not exists cg_section_prompts (
  prompt_id    uuid primary key default gen_random_uuid(),
  content_type cg_content_type not null,
  section      cg_section not null,
  kind         cg_asset_kind not null default 'content',
  name         text not null,
  template     text not null,
  input_keys   text[] not null default '{}',
  version      int not null default 1,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),

  constraint cg_section_prompts_uq unique (content_type, section, kind, version)
);

-- Exactly one active template per (content_type, section, kind).
create unique index if not exists cg_section_prompts_active_uq
  on cg_section_prompts (content_type, section, kind) where is_active;


-- -------------------------------------------------------------------- indexes
create index if not exists cg_runs_client_idx  on cg_runs (client_id, content_type, version desc);
create index if not exists cg_runs_period_idx  on cg_runs (client_id, period) where period is not null;
create index if not exists cg_runs_source_gin  on cg_runs using gin (source jsonb_path_ops);

drop index if exists cg_assets_run_idx;   -- v1 version included the dropped `type`
create index if not exists cg_assets_run_idx    on cg_assets (run_id, section, position);
create index if not exists cg_assets_client_idx on cg_assets (client_id, section);
create index if not exists cg_assets_review_idx on cg_assets (client_id) where status <> 'approved';
-- slug is unique per CLIENT, not per section: a logo URL carries no section, so
-- a section-scoped slug would let /sg/logos/concept-1/image hit the wrong asset.
create unique index if not exists cg_assets_slug_uq
  on cg_assets (client_id, slug) where slug is not null;

create index if not exists cg_asset_versions_data_gin on cg_asset_versions using gin (data jsonb_path_ops);
create index if not exists cg_asset_versions_run_idx  on cg_asset_versions (source_run_id) where source_run_id is not null;

drop index if exists cg_asset_chats_thread_idx;
create index if not exists cg_asset_chats_thread_idx on cg_asset_chats (asset_id, kind, version, created_at);

create index if not exists cg_asset_jobs_queue_idx on cg_asset_jobs (status, created_at)
  where status in ('queued', 'running');
create index if not exists cg_asset_jobs_asset_idx on cg_asset_jobs (asset_id, kind, created_at desc);
create index if not exists cg_asset_jobs_run_idx   on cg_asset_jobs (run_id, status);


-- --------------------------------------------------- helper functions / views

-- Resolution order: client row, then house row, then the built-in fallback.
-- A client who always wants eight reels is one row, not a branch in the
-- generator.
create or replace function cg_section_item_count(p_client uuid, p_section cg_section)
returns int
language sql
stable
as $$
  select coalesce(
    (select item_count from cg_section_defaults
      where client_id = p_client and section = p_section),
    (select item_count from cg_section_defaults
      where client_id is null and section = p_section),
    case p_section
      when 'pages'   then 6
      when 'posts'   then 8
      when 'reels'   then 4
      when 'stories' then 6
      when 'reviews' then 8
      when 'blogs'   then 12
      when 'scratch' then 4
      when 'revamp'  then 4
      when 'ads'     then 6
    end
  );
$$;

-- The next version number in one stream. The composite PK is what actually
-- prevents a duplicate under concurrency — on conflict, retry.
create or replace function cg_next_version(p_asset uuid, p_kind cg_asset_kind)
returns int
language sql
stable
as $$
  select coalesce(max(version), 0) + 1
  from cg_asset_versions
  where asset_id = p_asset and kind = p_kind;
$$;

-- The active CONTENT of an asset. Image generation reads this rather than a
-- stored copy of the copy, which is what keeps "image from active content"
-- true by construction instead of by convention.
create or replace function cg_active_content(p_asset uuid)
returns cg_asset_versions
language sql
stable
as $$
  select v.*
  from cg_asset_versions v
  join cg_assets a on a.asset_id = v.asset_id
  where v.asset_id = p_asset
    and v.kind = 'content'
    and v.version = a.active_content_version;
$$;

-- The source a content regeneration must read: the ACTIVE (highest-version)
-- run for that client and content type.
create or replace function cg_active_run_source(p_client uuid, p_content_type cg_content_type)
returns jsonb
language sql
stable
as $$
  select source
  from cg_runs
  where client_id = p_client and content_type = p_content_type
  order by version desc
  limit 1;
$$;

-- One row per asset with both active streams folded in — the shape the hub's
-- asset list actually renders, so the API stops assembling it in Python.
create or replace view cg_asset_current as
select
  a.asset_id,
  a.run_id,
  a.client_id,
  r.content_type,
  r.period,
  a.section,
  a.position,
  a.title,
  a.slug,
  a.status,
  a.error_message,
  a.active_content_version,
  a.active_image_version,
  c.body                             as body,
  c.data                             as data,
  c.word_count                       as word_count,
  c.qc_score                         as qc_score,
  c.source_run_id                    as content_source_run_id,
  i.file_path                        as file_path,
  i.kind                             as media_kind,
  a.approved_at,
  a.created_at,
  a.updated_at
from cg_assets a
join cg_runs r on r.run_id = a.run_id
left join cg_asset_versions c
  on c.asset_id = a.asset_id and c.kind = 'content' and c.version = a.active_content_version
left join cg_asset_versions i
  on i.asset_id = a.asset_id and i.kind in ('image', 'video') and i.version = a.active_image_version;


-- ------------------------------------------------------------------ triggers

-- HQ's client list carries last_run_at, kept current from the run side.
create or replace function cg_runs_touch_client()
returns trigger
language plpgsql
as $$
begin
  update cg_clients
     set last_run_at = greatest(coalesce(last_run_at, new.created_at), new.created_at)
   where client_id = new.client_id;
  return new;
end;
$$;

-- With assets generating in parallel, the run's status is a summary of its
-- assets rather than something a single code path sets at the end.
create or replace function cg_assets_roll_up_run()
returns trigger
language plpgsql
as $$
declare
  target uuid;
  total int;
  still_running int;
  failed int;
begin
  if tg_op = 'DELETE' then target := old.run_id; else target := new.run_id; end if;

  select count(*),
         count(*) filter (where status = 'generating'),
         count(*) filter (where status = 'failed')
    into total, still_running, failed
    from cg_assets where run_id = target;

  if total = 0 then
    return case when tg_op = 'DELETE' then old else new end;
  end if;

  update cg_runs
     set status = case
           when still_running > 0 then 'generating'::cg_run_status
           when failed = total    then 'failed'::cg_run_status
           when failed > 0        then 'partial'::cg_run_status
           else 'complete'::cg_run_status
         end,
         completed_at = case when still_running > 0 then null else now() end
   where run_id = target;

  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'cg_clients_touch') then
    create trigger cg_clients_touch before update on cg_clients
      for each row execute function cg_touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_runs_touch') then
    create trigger cg_runs_touch before update on cg_runs
      for each row execute function cg_touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_assets_touch') then
    create trigger cg_assets_touch before update on cg_assets
      for each row execute function cg_touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_asset_jobs_touch') then
    create trigger cg_asset_jobs_touch before update on cg_asset_jobs
      for each row execute function cg_touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_section_prompts_touch') then
    create trigger cg_section_prompts_touch before update on cg_section_prompts
      for each row execute function cg_touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_section_defaults_touch') then
    create trigger cg_section_defaults_touch before update on cg_section_defaults
      for each row execute function cg_touch_updated_at();
  end if;

  if not exists (select 1 from pg_trigger where tgname = 'cg_runs_touch_client') then
    create trigger cg_runs_touch_client after insert on cg_runs
      for each row execute function cg_runs_touch_client();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'cg_assets_roll_up_run') then
    create trigger cg_assets_roll_up_run after insert or update of status or delete on cg_assets
      for each row execute function cg_assets_roll_up_run();
  end if;
end $$;


-- ------------------------------------------------------------- house defaults
insert into cg_section_defaults (client_id, section, item_count) values
  (null, 'pages',   6),
  (null, 'posts',   8),
  (null, 'reels',   4),
  (null, 'stories', 6),
  (null, 'reviews', 8),
  (null, 'blogs',   12),
  (null, 'scratch', 4),
  (null, 'revamp',  4),
  (null, 'ads',     6)
on conflict do nothing;


-- --------------------------------------------------------- backfill (v1 -> v2)
do $$
declare
  orphan_media int := 0;
begin
  -- Only meaningful while v1's `type` column still exists.
  if exists (
    select 1 from information_schema.columns
    where table_name = 'cg_assets' and column_name = 'type'
  ) then
    -- 1. version rows inherit the kind their asset used to declare
    update cg_asset_versions v
       set kind = a.type
      from cg_assets a
     where a.asset_id = v.asset_id and v.kind = 'content' and a.type <> 'content';

    -- 2. the old single pointer becomes whichever pointer matches the kind
    update cg_assets set active_content_version = active_version where type = 'content';
    update cg_assets set active_image_version   = active_version where type in ('image', 'video');

    -- 3. media assets have no parent link in v1, so they CANNOT be folded into
    --    their content asset automatically. Report them and leave them intact.
    select count(*) into orphan_media from cg_assets where type in ('image', 'video');
    if orphan_media > 0 then
      raise notice
        'v1 left % image/video asset rows with no parent link. They are preserved as-is; re-link them onto their content asset (match on run_id + section + position) before dropping cg_assets.type.',
        orphan_media;
    end if;
  end if;

  -- 4. every existing version was produced by its asset's own run
  update cg_asset_versions v
     set source_run_id = a.run_id
    from cg_assets a
   where a.asset_id = v.asset_id and v.source_run_id is null;
end $$;

-- Left in place deliberately: dropping it before step 3 above is resolved would
-- lose the only clue about which post an orphaned image belonged to.
--   alter table cg_assets drop column type;
--   alter table cg_assets drop column active_version;


-- ------------------------------------------------------------------------ RLS
-- The backend connects straight to Postgres via DATABASE_URL, so RLS does not
-- affect it. Enabling it with no policies closes the PostgREST anon/authenticated
-- surface Supabase exposes by default. Drop this block if any client is ever
-- meant to read these tables with the anon key.
alter table cg_clients          enable row level security;
alter table cg_runs             enable row level security;
alter table cg_assets           enable row level security;
alter table cg_asset_versions   enable row level security;
alter table cg_asset_chats      enable row level security;
alter table cg_asset_jobs       enable row level security;
alter table cg_section_defaults enable row level security;
alter table cg_section_prompts  enable row level security;

commit;
