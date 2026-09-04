-- Content hub schema, v2.
--
-- Client-first, keyed on Command HQ's own uuids. Replaces the first cut of the
-- cg_* tables entirely: the types changed (uuid, enum, jsonb, timestamptz), so
-- migrating the old rows across would cost more than re-deriving them from the
-- source tables, which are untouched and remain the record.
--
-- Applied directly rather than through Alembic because this database is on
-- revision e938358a61e8, which does not exist in the repo, and the migration
-- graph has two open heads. Fix that before relying on `alembic upgrade`.
--
-- Nothing below references, alters or reads any pre-existing table.

begin;

drop table if exists cg_asset_chats     cascade;
drop table if exists cg_asset_versions  cascade;
drop table if exists cg_assets          cascade;
drop table if exists cg_runs            cascade;
drop table if exists cg_section_defaults cascade;
drop table if exists cg_clients         cascade;

drop type if exists cg_content_type cascade;
drop type if exists cg_section      cascade;
drop type if exists cg_asset_type   cascade;
drop type if exists cg_run_status   cascade;
drop type if exists cg_asset_status cascade;

-- --------------------------------------------------------------------------
-- Enums. Invalid states are rejected by the database, not by convention.
-- --------------------------------------------------------------------------

create type cg_content_type as enum ('website', 'social', 'blog', 'logo', 'ads');

-- The sub type within a content type. One enum rather than one per content
-- type: assets are rendered through a single card and queried as one set, and
-- the pairing is enforced by cg_assets_section_ck below.
create type cg_section as enum (
  'pages',                                  -- website
  'posts', 'reels', 'stories', 'reviews',   -- social
  'blogs',                                  -- blog
  'scratch', 'revamp',                      -- logo
  'ads'                                     -- ads
);

create type cg_asset_type   as enum ('content', 'image', 'video');
create type cg_run_status   as enum ('pending', 'generating', 'complete', 'partial', 'failed');
create type cg_asset_status as enum ('generating', 'review', 'approved');

-- --------------------------------------------------------------------------
-- Clients. Three fields, straight from the HQ export.
-- --------------------------------------------------------------------------

create table cg_clients (
  client_id           uuid primary key,   -- HQ's clientId IS the key, no surrogate
  client_name         text not null,
  client_organization uuid,

  -- When this client last had a run. Maintained by cg_runs_touch_client below,
  -- not by whoever inserts the run, so it cannot drift out of step with cg_runs
  -- however a run gets created: the rebuild sync and the generate path both get
  -- it right without either having to remember to.
  last_run_at         timestamptz,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- Recent clients are the default tab in the picker, so this index is what that
-- tab reads. nulls last because a client with no runs sorts after every client
-- that has one, which is the opposite of Postgres's default for desc.
create index cg_clients_recent_idx on cg_clients (last_run_at desc nulls last);

comment on table cg_clients is
  'Clients that have content here. HQ owns the list; this only exists so runs '
  'and assets have something to hang off. Never created through the API.';

-- --------------------------------------------------------------------------
-- Runs. One request, one frozen snapshot of everything it was given.
-- --------------------------------------------------------------------------

create table cg_runs (
  run_id       uuid primary key default gen_random_uuid(),
  client_id    uuid not null references cg_clients (client_id) on delete cascade,
  content_type cg_content_type not null,
  version      int not null,
  status       cg_run_status not null default 'pending',

  -- The whole brief: usps, sitemap, industries, meetings, logo approach. jsonb
  -- because the shape genuinely differs by content_type, and because a run has
  -- to stay reproducible after HQ's record changes underneath it.
  source       jsonb not null default '{}'::jsonb,

  -- Materialised out of source so it can be filtered without touching jsonb.
  client_name  text generated always as (source ->> 'client_name') stored,

  period       text,   -- 'YYYY-MM', blog only
  summary      text,
  requested_by text,

  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),

  constraint cg_runs_version_uq unique (client_id, content_type, version),
  constraint cg_runs_period_ck  check (period is null or period ~ '^\d{4}-\d{2}$')
);

comment on column cg_runs.version is
  'Per (client_id, content_type). Re-requesting the same content type creates '
  'v2 with its own source, which is what makes the run history meaningful.';

create index cg_runs_client_idx  on cg_runs (client_id, content_type, version desc);
create index cg_runs_period_idx  on cg_runs (client_id, period) where period is not null;
create index cg_runs_source_gin  on cg_runs using gin (source jsonb_path_ops);

-- --------------------------------------------------------------------------
-- Assets. No content_type: that lives on the run.
-- --------------------------------------------------------------------------

create table cg_assets (
  asset_id  uuid primary key default gen_random_uuid(),
  run_id    uuid not null references cg_runs (run_id) on delete cascade,
  client_id uuid not null references cg_clients (client_id) on delete cascade,

  section   cg_section     not null,                    -- reels, revamp, pages...
  type      cg_asset_type  not null default 'content',  -- content | image | video
  position  int            not null default 0,
  title     text,
  status    cg_asset_status not null default 'review',

  -- Which version ships, and what Restore sets. There is deliberately no
  -- `display_version`: which version a card happens to be showing is UI state,
  -- and this table is shared with no per-user scoping, so storing it would mean
  -- one person previewing an older version changed what everyone else saw.
  -- Preview lives in React and a reload correctly falls back to active.
  active_version  int not null default 1,

  -- A stable, human readable id for the URL. Stored rather than derived from
  -- the title at render time, because titles get edited and
  -- /sg/social-media/reels/reel-2 should not start pointing at a different reel
  -- when one does.
  slug text,

  approved_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint cg_assets_active_ck check (active_version > 0)
);

create index cg_assets_run_idx    on cg_assets (run_id, section, type, position);
create index cg_assets_client_idx on cg_assets (client_id, section);
create index cg_assets_review_idx on cg_assets (client_id) where status <> 'approved';

-- Unique per CLIENT, not per (client, section). The obvious narrower scope is
-- wrong: a logo asset's URL carries no section by design, so a slug unique only
-- within one made /sg/logos/concept-1/image resolve to whichever of scratch or
-- revamp came first. JOL SOLAR has concept-1 under both, so this was real.
-- One slug per client makes every URL sufficient on its own.
create unique index cg_assets_slug_uq on cg_assets (client_id, slug)
  where slug is not null;

-- --------------------------------------------------------------------------
-- Versions. Five columns; the brief lives on the run, never repeated here.
-- --------------------------------------------------------------------------

create table cg_asset_versions (
  asset_id   uuid not null references cg_assets (asset_id) on delete cascade,
  version    int  not null,
  body       text,
  file_path  text,
  created_at timestamptz not null default now(),
  primary key (asset_id, version)
);

-- --------------------------------------------------------------------------
-- Chat. One instruction per row, against one VERSION, not per asset.
-- No role column: every row is an instruction someone typed, and there is no
-- second speaker in the table to distinguish it from.
-- --------------------------------------------------------------------------

create table cg_asset_chats (
  message_id uuid primary key default gen_random_uuid(),
  asset_id   uuid not null,
  version    int  not null,
  body       text not null,
  created_at timestamptz not null default now(),

  -- Composite FK to the version, so deleting a version takes its conversation
  -- with it and a message can never outlive the text it was about.
  constraint cg_asset_chats_version_fk foreign key (asset_id, version)
    references cg_asset_versions (asset_id, version) on delete cascade
);

create index cg_asset_chats_thread_idx on cg_asset_chats (asset_id, version, created_at);

-- --------------------------------------------------------------------------
-- How many items a run produces per section.
--
-- Two levels in one table: client_id null is the house default, a row with a
-- client_id overrides it for that client. Resolution is coalesce(client, house,
-- hardcoded fallback), so a client who always wants eight reels is one row
-- rather than a branch in the generator, and a missing row can never stop a run.
-- --------------------------------------------------------------------------

create table cg_section_defaults (
  -- Null means the house default. Deliberately nullable, which is why the
  -- identity below is two partial indexes and not a primary key: Postgres
  -- treats nulls as distinct in a unique constraint, so a single
  -- unique (client_id, section) would happily accept two house defaults for
  -- the same section and then the resolution above is a coin toss.
  client_id  uuid references cg_clients (client_id) on delete cascade,
  section    cg_section not null,
  item_count int not null,
  updated_at timestamptz not null default now(),

  constraint cg_section_defaults_count_ck check (item_count between 1 and 50)
);

create unique index cg_section_defaults_global_uq
  on cg_section_defaults (section) where client_id is null;
create unique index cg_section_defaults_client_uq
  on cg_section_defaults (client_id, section) where client_id is not null;

-- Seeded with what the generators produce today, so turning this table on
-- changed no output.
insert into cg_section_defaults (client_id, section, item_count) values
  (null, 'pages',   6),
  (null, 'posts',   8),
  (null, 'reels',   4),
  (null, 'stories', 6),
  (null, 'reviews', 8),
  (null, 'blogs',   4),
  (null, 'scratch', 4),
  (null, 'revamp',  4),
  (null, 'ads',     6);

-- --------------------------------------------------------------------------
-- One trigger, applied to every table that has updated_at.
-- --------------------------------------------------------------------------

create or replace function cg_touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger cg_clients_touch before update on cg_clients
  for each row execute function cg_touch_updated_at();
create trigger cg_runs_touch before update on cg_runs
  for each row execute function cg_touch_updated_at();
create trigger cg_assets_touch before update on cg_assets
  for each row execute function cg_touch_updated_at();

create trigger cg_section_defaults_touch before update on cg_section_defaults
  for each row execute function cg_touch_updated_at();

-- --------------------------------------------------------------------------
-- cg_clients.last_run_at, maintained from cg_runs.
--
-- greatest(coalesce(...)) rather than a plain assignment, because the rebuild
-- sync inserts a client's runs in whatever order the source tables yield them.
-- A plain assignment would leave last_run_at holding the LAST row inserted
-- rather than the most recent run, which is only the same thing by luck.
-- --------------------------------------------------------------------------

create or replace function cg_touch_client_last_run() returns trigger
language plpgsql as $$
begin
  update cg_clients
     set last_run_at = greatest(coalesce(last_run_at, new.created_at), new.created_at)
   where client_id = new.client_id;
  return new;
end $$;

create trigger cg_runs_touch_client
  after insert or update of created_at on cg_runs
  for each row execute function cg_touch_client_last_run();

commit;
