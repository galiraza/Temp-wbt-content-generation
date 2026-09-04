-- ============================================================================
-- WBT Content Hub — schema v2, step 1 of 2: enums
--
-- Split from the main migration on purpose. `ALTER TYPE ... ADD VALUE` cannot
-- have its new value USED in the same transaction that adds it, so the enums
-- are established and committed before anything references them.
--
-- Deliberately NOT wrapped in BEGIN/COMMIT — each statement stands alone and
-- every one is guarded, so the file is safe to re-run.
-- ============================================================================

create extension if not exists pgcrypto;   -- gen_random_uuid()

do $$
begin
  if not exists (select 1 from pg_type where typname = 'cg_content_type') then
    create type cg_content_type as enum ('website', 'social', 'blog', 'logo', 'ads');
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_section') then
    create type cg_section as enum
      ('pages', 'posts', 'reels', 'stories', 'reviews', 'blogs', 'scratch', 'revamp', 'ads');
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_run_status') then
    create type cg_run_status as enum
      ('pending', 'generating', 'complete', 'partial', 'failed');
  end if;

  -- v1 called this cg_asset_type and hung it off the asset. It now describes a
  -- VERSION's kind, so it is renamed rather than replaced: a rename keeps every
  -- existing value valid where a new type would need a table rewrite.
  if exists (select 1 from pg_type where typname = 'cg_asset_type')
     and not exists (select 1 from pg_type where typname = 'cg_asset_kind') then
    alter type cg_asset_type rename to cg_asset_kind;
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_asset_kind') then
    create type cg_asset_kind as enum ('content', 'image', 'video');
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_asset_status') then
    create type cg_asset_status as enum ('generating', 'review', 'approved', 'failed');
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_chat_role') then
    create type cg_chat_role as enum ('user', 'assistant');
  end if;

  if not exists (select 1 from pg_type where typname = 'cg_job_status') then
    create type cg_job_status as enum
      ('queued', 'running', 'succeeded', 'failed', 'cancelled');
  end if;
end $$;

-- A per-asset generation can now fail on its own; v1's cg_asset_status had no
-- way to say so. No-op when the type was just created above with the value.
do $$
begin
  if not exists (
    select 1 from pg_enum e join pg_type t on t.oid = e.enumtypid
    where t.typname = 'cg_asset_status' and e.enumlabel = 'failed'
  ) then
    alter type cg_asset_status add value 'failed';
  end if;
end $$;
