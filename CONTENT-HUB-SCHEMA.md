# WBT Content Hub — schema & API handoff

Branch `wbt-web` in `E:\02-webuildtrades\Paid_Ads_Generation`.
Verified against the live Supabase DB (`aydgxlvtsvetqyumesyw`, aws-0-eu-west-2) on 2026-09-04.

## Environment gotcha (read first)

Two `.env` files exist with **different Supabase projects**. `backend/.env` wins, because
`load_dotenv()` in `backend/app/config.py` resolves upward from that file and finds
`backend/.env` before the repo-root `.env`.

| File | Project | State |
|---|---|---|
| `backend/.env` | `aydgxlvtsvetqyumesyw` @ aws-**0** | 34 tables — **the real one** |
| `.env` (repo root) | `fpxjilofbklkilffvaul` @ aws-**1** | 11 tables — near-empty, wrong |

If hub endpoints return 503 / "relation does not exist", the process is reading the root
`.env`. Do **not** run migrations to fix that. Also note `alembic current` fails on the real
DB — it is stamped `e938358a61e8`, a revision absent from `alembic/versions/` on this
branch. Resolve that before writing any new migration.

## Local run (no Docker)

```
# backend  -> http://127.0.0.1:8001
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8001 --host 127.0.0.1

# frontend -> http://localhost:3001
cd frontend && npx next dev -p 3001
```

Auth: **every** route requires header `X-API-Key: <API_KEY from .env>`.
Exempt: `/docs`, `/openapi.json`, `/redoc`, `/health`.
Frontend reads `NEXT_PUBLIC_API_URL` (currently `http://localhost:8001`). Set
`NEXT_PUBLIC_APP_URL` to match the port actually in use, or `/` redirects to the wrong host.

## Postgres enums

```
cg_content_type  website | social | blog | logo | ads
cg_section       pages | posts | reels | stories | reviews | blogs | scratch | revamp | ads
cg_asset_type    content | image | video
cg_asset_status  generating | review | approved
cg_run_status    pending | generating | complete | partial | failed
```

Sections per content type (`SECTIONS_BY_CONTENT_TYPE` in `models/content_generation/run.py`):

```
website -> (pages,)
social  -> (posts, reels, stories, reviews)   # the only one that fans out
blog    -> (blogs,)
logo    -> (scratch, revamp)
ads     -> (ads,)
```

## Tables (6, live)

Shape: `cg_clients 1─* cg_runs 1─* cg_assets 1─* cg_asset_versions 1─* cg_asset_chats`,
plus `cg_section_defaults`. Every FK is `ON DELETE CASCADE`, and the ORM sets
`passive_deletes=True` throughout so the database does the cascading.

### cg_clients — 13 rows

```
client_id            uuid   PK          -- Command HQ's uuid; NO surrogate id, no server default
client_name          text   not null
client_organization  uuid   null
last_run_at          timestamptz null   -- set by trigger cg_runs_touch_client, read-only here
created_at           timestamptz not null default now()
updated_at           timestamptz not null default now()
```

HQ owns the client list; rows are never created through the API.

### cg_runs — 26 rows

One generation request, for one client and one content type.

```
run_id        uuid  PK default gen_random_uuid()
client_id     uuid  not null -> cg_clients(client_id) CASCADE
content_type  cg_content_type not null
version       int   not null                 -- per (client_id, content_type)
status        cg_run_status not null default 'pending'
source        jsonb not null default '{}'    -- the FROZEN brief; shape differs per content type
client_name   text  null                     -- GENERATED ALWAYS AS (source->>'client_name') STORED
period        text  null                     -- 'YYYY-MM', blog only, CHECK ~ '^\d{4}-\d{2}$'
summary       text  null
requested_by  text  null
created_at / updated_at  timestamptz not null default now()

UNIQUE (client_id, content_type, version)    -- cg_runs_version_uq
```

**`client_name` is a generated column** — Postgres rejects any INSERT/UPDATE that names it.
It is mapped with `FetchedValue()`; never include it in a write.

`source` is jsonb rather than columns because its shape genuinely differs by content type
(website carries a sitemap, logo an approach, blog a month), and because a run must stay
reproducible after HQ's record changes underneath it. Copying the brief in at request time
is what makes the version history mean anything.

### cg_assets — 165 rows

One generated item: a page group, post, reel, blog, logo, ad. One shape for all of them,
because the UI renders them through the same card and queries them as one set.

```
asset_id        uuid PK default gen_random_uuid()
run_id          uuid not null -> cg_runs(run_id) CASCADE
client_id       uuid not null -> cg_clients(client_id) CASCADE  -- denormalised off run, avoids a join
section         cg_section not null
type            cg_asset_type not null default 'content'
position        int  not null default 0
title           text null
status          cg_asset_status not null default 'review'
active_version  int  not null default 1      -- CHECK > 0; names a row in cg_asset_versions
slug            text null                    -- URL segment, UNIQUE PER CLIENT (not per section)
approved_at     timestamptz null
created_at / updated_at timestamptz not null default now()
```

There is **no `content_type`** here — it lives on the run.

There is **no `display_version`**. Which version a card shows is UI state, and this table has
no per-user scoping, so storing it would mean one person previewing an older version changed
what everyone else saw. Preview belongs in React; a reload then falls back to the active
version, which is the behaviour you want anyway.

### cg_asset_versions — 183 rows

```
asset_id    uuid  PK part -> cg_assets(asset_id) CASCADE
version     int   PK part
body        text  null        -- text content
file_path   text  null        -- Supabase Storage path, for image/video assets
created_at  timestamptz not null default now()

PRIMARY KEY (asset_id, version)
```

Composite PK on purpose: the version number *is* the identity. A surrogate id would let two
rows claim version 3 of the same asset. The brief is not repeated here — it belongs to the
run, and copying it per version would let the two drift.

### cg_asset_chats — 0 rows

The refinement conversation, threaded per **version**, not per asset.

```
message_id  uuid PK default gen_random_uuid()
asset_id    uuid not null
version     int  not null
body        text not null
created_at  timestamptz not null default now()

FOREIGN KEY (asset_id, version) -> cg_asset_versions(asset_id, version) CASCADE
```

Per asset would be the obvious choice and it is the wrong one: every message is about a
specific piece of text, so a thread that outlives the version it discusses reads as a
conversation about content nobody can see any more. Keying on `(asset_id, version)` means
restoring an older version brings back its own thread.

It is a single **composite** FK, not two independent ones — that is what stops a message
existing on a version that was never written. No `role` column: every row is something a
person typed, so there is no second speaker to distinguish it from.

### cg_section_defaults — 9 rows

How many items a run produces for one section. Two levels in one table.

```
client_id   uuid null -> cg_clients(client_id) CASCADE   -- NULL = house default
section     cg_section not null
item_count  int not null                                 -- CHECK between 1 and 50
updated_at  timestamptz not null default now()
```

No PK column; the identity is `(client_id, section)`. Because Postgres treats NULLs as
distinct in a unique constraint, this needs **two partial unique indexes**, not one:

```
cg_section_defaults_global_uq (section)             WHERE client_id IS NULL
cg_section_defaults_client_uq (client_id, section)  WHERE client_id IS NOT NULL
```

Resolution: `coalesce(client row, global row, FALLBACK_ITEM_COUNTS)`, the last in
`models/content_generation/settings.py` —
`pages 6, posts 8, reels 4, stories 6, reviews 8, blogs 4, scratch 4, revamp 4, ads 6`.
So a client who always wants eight reels is one row, not a branch in the generator.

### Indexes worth knowing

```
cg_assets_run_idx     (run_id, section, type, position)
cg_assets_client_idx  (client_id, section)
cg_assets_review_idx  (client_id) WHERE status <> 'approved'
cg_assets_slug_uq     (client_id, slug) UNIQUE WHERE slug IS NOT NULL
cg_runs_client_idx    (client_id, content_type, version DESC)
cg_runs_period_idx    (client_id, period) WHERE period IS NOT NULL
cg_runs_source_gin    GIN (source jsonb_path_ops)
cg_asset_chats_thread_idx (asset_id, version, created_at)
```

### Conventions to preserve

- `updated_at` has **no `onupdate`** anywhere in this schema. A Postgres trigger
  (`cg_touch_updated_at`) sets it; duplicating that in Python would let a direct SQL edit
  and an ORM edit disagree.
- Every enum is declared `create_type=False`. The types already exist (applied by
  `models/content_generation/schema.sql`), and SQLAlchemy attempting CREATE TYPE or
  DROP TYPE around them would fail or, worse, succeed.

## API — prefix `/api/content-generation`

Router `backend/app/routers/content_generation.py`, registered in `main.py`.

```
GET    /clients                                   -> [HubClientOut]
GET    /clients/{client_id}/overview              -> HubOverviewOut
GET    /clients/{client_id}/assets                -> [HubAssetOut]
         ?content_type=<required>&section=&period=&version=
GET    /clients/{client_id}/assets/by-slug/{slug} -> HubAssetDetailOut
GET    /clients/{client_id}/draft                 -> HubDraftOut
POST   /clients/{client_id}/runs                  -> HubRunOut           202
GET    /assets/{asset_id}                         -> HubAssetDetailOut
POST   /assets/{asset_id}/approve                 -> HubAssetOut
POST   /assets/{asset_id}/restore                 -> HubAssetOut
POST   /assets/{asset_id}/image                   -> HubAssetOut
GET    /assets/{asset_id}/chat                    -> [HubChatMessageOut]
POST   /assets/{asset_id}/chat?version=           -> HubChatMessageOut   201
POST   /sync                                      -> HubSyncOut
GET    /settings                                  -> [HubSectionDefaultOut]
PUT    /settings/{section}                        -> [HubSectionDefaultOut]
DELETE /settings/{section}                        -> [HubSectionDefaultOut]
```

`POST /clients/{id}/runs` returns **202, not 201**: the run exists, the work it describes has
not happened yet. A website run is up to seventeen agent calls, so it runs behind a
`BackgroundTasks` rather than holding the connection open for minutes.

`GET /clients/{id}/assets/by-slug/{slug}` takes no section parameter, because
`(client_id, slug)` is unique by index. It returns the same detail shape as
`/assets/{asset_id}`, so a page reached by slug and one reached by id render identically.

Path params are typed `uuid.UUID`, so a malformed id is a 422. But `HubClientOut.client_id`
is a plain `str`: the HQ export is the source, and one badly formed id there should return a
row the UI can ignore rather than failing the whole list.

## Response shapes (`backend/app/schemas/content_generation.py`)

```python
HubClientOut       client_id: str, client_name, client_organization?, asset_count=0,
                   last_run_at?, meta=""
HubSectionOut      id: str, label: str, count: int   # id is str: blog's sub tabs are periods
HubContentTypeOut  id: HubContentType, label, count, unit,
                   single/table/monthly/logo: bool, sections: [HubSectionOut]
HubRunOut          run_id, content_type, version, status, period?, summary?, requested_by?,
                   client_name?, asset_count=0, approved_count=0, approved_label="", created_at?
HubOverviewOut     client: HubClientOut, content_types: [HubContentTypeOut], runs: [HubRunOut]
HubVersionOut      version, body?, file_path?, created_at?, is_active: bool
HubAssetOut        asset_id, run_id, client_id, content_type?, section, type, position,
                   title?, slug?, status, active_version, body?, file_path?,
                   approved_at?, created_at?, updated_at?
HubAssetDetailOut  asset: HubAssetOut, versions: [HubVersionOut], active_version: int
HubChatMessageOut  message_id, asset_id, version, body, created_at?
HubSyncOut         extra="allow" — the sync decides what it counts

# inputs
HubChatMessageCreate  body: str (min_length=1)   # version is a QUERY param, not a field
HubRunCreate          content_type, source: dict = {}, period?, requested_by?
HubSectionDefaultIn   item_count: int (1..50)
HubDraftOut           content_type, source: dict, run_id?, version?
```

`HubAssetOut.body` / `.file_path` are the **active version's**, folded in by every route that
returns an asset — an asset row holds no content of its own. `content_type` comes off the
run, and is null only when a caller built the object without the run to hand.

`HubRunOut` deliberately omits `source`: it is the largest thing in the schema and the
history is ~20 of these. Put it on a run-detail route if one is ever needed.

`HubOverviewOut` is one call rather than one per tab — every badge must be right before the
panel first paints, and switching tabs should not wait on the network.

`HubAssetDetailOut` repeats `active_version` even though it also sits on `asset`, because the
version list is what the panel renders and every row needs comparing against it.

`HubDraftOut` returns the merged `source` of the most recent run, so reopening a form shows
what was used last time rather than an empty sheet. Nothing in it comes from the Command HQ
export — that was asked for explicitly: the client picker says who the run is for, the form
says what to generate, and prefilling the second from the first put stale answers in front of
someone who was there to type fresh ones.

## Frontend

Page `frontend/app/content-generation/`, shared client `frontend/lib/api.ts`, types
`frontend/lib/types.ts`. Public asset routes live under `frontend/app/sg/` and address
assets by `(client_id, slug)` — which is why `slug` is unique per client rather than per
section: a logo URL carries no section, so a section-scoped slug would let
`/sg/logos/concept-1/image` resolve to the wrong asset.

## Project skills

`wbt-hub-models`, `wbt-hub-api`, `wbt-hub-ui`, `wbt-hub-sync` — invoke the matching one
before changing models, routes, the UI, or the backfill from the six original request tables.
