# Per-asset agentic generation — implementation plan

How to take the current run-scoped pipelines to a per-asset model where every
asset generates, regenerates and retries independently and in parallel.

Written against `E:\02-webuildtrades\Paid_Ads_Generation` (branch `wbt-web`) and
the v2 schema in `supabase/migrations/20260904*`.

---

## 1. Where it stands today

Parallelism already exists — this is not a rewrite from sequential code. What is
wrong is the **unit of work**, not the concurrency.

| module | fan-out | limit | file |
|---|---|---|---|
| blog | over blogs, after a shared metadata phase | `MAX_CONCURRENT_BLOGS = 3` | `app/agents/blog_generation/pipeline.py` |
| website | over sections, after a shared intake phase | `MAX_CONCURRENT_SECTIONS = 3` | `app/agents/website_content/pipeline.py` |
| post | posts/reviews/reels, nested pools | `ThreadPoolExecutor(2)` outer + `(2)` inner | `app/agents/post_generation/pipeline.py` |
| images | over slots | `_MAX_CONCURRENT_IMAGE_CALLS = 4` | `app/agents/post_generation/hero_image_agent.py` |

Five properties of the current design block per-asset work:

**1. The run is the unit.** `start_generation(db, request, keys)` starts a whole
request. An in-process `_running` set keyed on `request.id` refuses a second
start, so *any* per-asset regeneration is locked out while the run is going.

**2. Work is a daemon thread, not a record.** The docstring is candid about it:

> A daemon thread, deliberately: this is in-process work with no queue behind
> it, so a server restart mid-run abandons it. The rows left on "generating"
> are what makes that visible.

A restart mid-run leaves assets stuck on `generating` with nothing to resume
them. Acceptable when a human re-runs the whole job; not acceptable when twenty
assets are in flight independently.

**3. The shared phase is recomputed per regeneration.** `regenerate_section`
re-runs the entire intake:

> The alternative — replaying the stored brief — would rebuild it from
> `meeting_insights`, which is exactly what intake produces, so the saving is
> four calls out of eleven.

Four wasted calls out of eleven is a fair trade for one section. For a single
asset it is the *whole* cost, and it is paid on every retry.

**4. Persistence is single-threaded by necessity.** Workers return outcomes and
the orchestrator writes them, because SQLAlchemy Sessions are not thread-safe —
hence `snapshot(request)` before fan-out and the warning that touching the ORM
row past that point fires a lazy reload on a Session another thread is using.
Fine within one process; it does not survive moving to real workers.

**5. Prompts are functions, not data.** Each section's prompt is a Python call
inside its agent module. Nothing addresses "the prompt for `website/pages`
content", so there is no seam to swap, version or A/B one.

---

## 2. Target architecture

```
POST /runs                 the brief is frozen into cg_runs.source
     |
     v
[ PLAN ]  one job, synchronous
     |    resolves item counts, creates cg_assets rows, enqueues jobs
     |
     v
[ PREPARE ]  one job per (run, phase)   <-- the shared phase, ONCE
     |       website: intake -> meeting_insights
     |       blog:    scrape + metadata -> per-blog briefs
     |       result cached on cg_runs.source.prepared
     v
[ GENERATE ]  N jobs, one per asset          <-- the fan-out
     |        each: read prompt + instructions -> LLM -> write ONE version
     |        each: own Session, own transaction, own retry budget
     v
[ REFINE ]  0..N jobs per asset (QC loop, blog only today)
     |
     v
[ MEDIA ]  one job per asset, reads the asset's ACTIVE content version
```

Every box is a `cg_asset_jobs` row except PLAN and PREPARE, which are run-scoped
(see §4 for where those live). The queue is the database, not a thread pool.

---

## 3. The prompt registry

`cg_section_prompts` makes a prompt addressable by `(content_type, section,
kind)` with one active version each, enforced by
`cg_section_prompts_active_uq`.

```
prompt_id | content_type | section | kind    | name              | input_keys
----------+--------------+---------+---------+-------------------+---------------------------
 ...      | website      | pages   | content | page_writer_v3    | {sitemap,business_name,...}
 ...      | blog         | blogs   | content | blog_writer_v2    | {cluster_theme_1,keywords}
 ...      | social       | posts   | content | post_writer_v4    | {main_topic,fixed_rules,...}
 ...      | social       | posts   | image   | post_hero_v2      | {logo_path,industry}
```

`input_keys` is what turns "pass the sources based on required instructions"
into something mechanical rather than a per-section branch in Python:

```python
def build_instructions(run, asset, prompt) -> dict:
    """The slice of the run's source this asset's prompt actually needs."""
    source = {**run.source, **run.source.get("prepared", {})}
    payload = {k: source[k] for k in prompt.input_keys if k in source}
    payload["position"] = asset.position          # blog N of 12, page 3 of 6
    payload["section"] = asset.section
    if asset.title:
        payload["title"] = asset.title
    return payload
```

The result is stored on the job (`cg_asset_jobs.instructions`). That is the
single most valuable thing in this plan for debugging: a failed generation can
be replayed exactly, without re-running intake, because the input is on the row.

**Migration path for prompts.** Do not move all of them at once. Add a resolver
that falls back to today's hard-coded function when no active row exists:

```python
def resolve_prompt(db, content_type, section, kind):
    row = db.query(SectionPrompt).filter_by(
        content_type=content_type, section=section, kind=kind, is_active=True
    ).one_or_none()
    return row.template if row else LEGACY_PROMPTS[(content_type, section, kind)]
```

Move one section at a time, verify output parity, then delete its legacy entry.

---

## 4. Job lifecycle

```
queued ──> running ──> succeeded
              │
              ├──> failed      (attempt < max)  -> new row, attempt + 1
              └──> cancelled   (run superseded / user cancelled)
```

Claiming a job must be atomic, or two workers take the same one:

```sql
update cg_asset_jobs
   set status = 'running', started_at = now(), updated_at = now()
 where job_id = (
   select job_id from cg_asset_jobs
    where status = 'queued'
    order by created_at
    for update skip locked
    limit 1
 )
returning *;
```

`FOR UPDATE SKIP LOCKED` is the whole scheduler. It needs no Redis, no Celery,
and it is backed by `cg_asset_jobs_queue_idx`, which is partial on
`status in ('queued','running')` so the index stays small as history grows.

**On success**, one transaction does all of:

```sql
insert into cg_asset_versions (asset_id, kind, version, body, data, source_run_id, created_by)
values ($asset, $kind, cg_next_version($asset, $kind), $body, $data, $source_run, $prompt_name);

update cg_assets
   set active_content_version = $new_version,   -- or active_image_version
       status = 'review',
       error_message = null
 where asset_id = $asset;

update cg_asset_jobs
   set status = 'succeeded', result_version = $new_version, finished_at = now()
 where job_id = $job;
```

The composite PK `(asset_id, kind, version)` is the concurrency guard: if two
workers race on `cg_next_version`, the second insert violates the PK and that
attempt retries. Do not add advisory locks for this — the constraint is enough.

**On failure**, set `cg_assets.status = 'failed'` and `error_message`. The
`cg_assets_roll_up_run` trigger recomputes the run's status from its assets, so
nothing needs to track "how many are left" in application code.

**Restart safety** — the thing daemon threads cannot give you. On boot:

```sql
update cg_asset_jobs
   set status = 'queued', attempt = attempt + 1, error_message = 'reclaimed after restart'
 where status = 'running' and started_at < now() - interval '15 minutes';
```

---

## 5. Concurrency and rate limits

Concurrency now has to be bounded **per provider**, not per pipeline, because
jobs from different runs are in flight together. Today's three separate
constants (3 blogs, 3 sections, 4 images) can each be respected while the
process as a whole exceeds Anthropic's limit.

- One worker pool, size from env (`GENERATION_WORKERS`, start at 4).
- A shared semaphore per provider around the LLM call, not around the job.
- Exponential backoff with jitter on 429/5xx; `attempt` on the job row is the
  retry counter, so a restart does not reset someone's budget.
- Cap `attempt` at 3, then leave the job `failed` for a human.

Start with the pool **in-process** (a thread that polls the claim query). It is
a small change from today's threads and needs no new infrastructure. The queue
being in Postgres means moving to a separate worker process later is a
deployment change, not a code change.

---

## 6. Regeneration paths

The two rules from the schema, as code paths:

**Content** — reads the ACTIVE run's source, never the asset's own run:

```python
def regenerate_content(db, asset):
    run = active_run(db, asset.client_id, content_type_of(asset))   # cg_active_run_source
    prompt = resolve_prompt(db, run.content_type, asset.section, "content")
    enqueue(db, asset, kind="content", source_run=run, instructions=build_instructions(run, asset, prompt))
```

This is why `cg_asset_versions.source_run_id` exists: after a newer run,
versions 1–3 of an asset may come from run v4 and version 4 from run v5.
Without the column that is unanswerable.

**Image** — reads the asset's ACTIVE content, never a stored copy:

```python
def regenerate_image(db, asset):
    content = db.execute(select(func.cg_active_content(asset.asset_id))).one()
    prompt = resolve_prompt(db, ..., kind="image")
    enqueue(db, asset, kind="image", instructions={
        "title": content.data.get("title") or asset.title,
        "body": content.body,
        "hashtags": content.data.get("hashtags", []),
        **brand_assets(run),
    })
```

The original already had this right, and the reason is worth preserving:

> Deliberately holds no generation inputs. Everything the image is built from
> already exists in other rows … Storing them again would be a second copy that
> can drift from the first.

Approving a chat proposal is the same insert path — `cg_asset_chats.proposal`
becomes a new version — so there is one way content enters the system, not
three.

---

## 7. Delivery order

Each step ships and is useful alone. None requires the next.

| # | Step | Unblocks | Risk |
|---|---|---|---|
| 1 | Apply the v2 migration; backfill `kind`, `source_run_id` | everything | med — see §8 |
| 2 | Dual-write versions through one `create_version()` helper | one insert path | low |
| 3 | Add `cg_asset_jobs` + the claim loop; keep pipelines as-is, but have them enqueue instead of thread | restart safety, visible queue | low |
| 4 | Split PREPARE out of each pipeline; cache to `source.prepared` | per-asset regen without replaying intake | **high value** |
| 5 | Per-asset GENERATE jobs; delete the per-run `_running` lock | true parallel + independent retry | med |
| 6 | Prompt registry with legacy fallback; migrate one section at a time | prompt iteration without deploys | low |
| 7 | Provider-level semaphore; retire the three per-pipeline constants | rate-limit correctness | low |
| 8 | Move the pool to its own process | horizontal scale | low |

Step 4 is the one that pays for the rest. Until the shared phase is cached,
"regenerate one asset" still costs a full intake, and every other improvement is
hidden behind that.

---

## 8. Risks

**The v2 backfill cannot re-link orphaned media.** v1 stored images as separate
`cg_assets` rows with no parent, so the migration preserves them and raises a
`NOTICE` with the count rather than guessing. Re-link on
`(run_id, section, position)` and verify by eye before dropping `cg_assets.type`
— the migration deliberately leaves that DROP commented out.

**Alembic is stamped at a missing revision.** The live DB claims
`e938358a61e8`, which is not in `alembic/versions/`. Resolve that before any new
Alembic revision; apply these two files as SQL in the meantime.

**A cached PREPARE can go stale.** If the brief is edited after intake ran,
`source.prepared` is wrong. Key the cache on a hash of the brief's input fields
and recompute when it changes.

**Ordering assumptions.** `hero_image_agent` uses indexed results rather than
`as_completed` specifically to keep return order equal to slot order. Per-asset
jobs complete out of order by design — anything that depended on completion
order needs `cg_assets.position` instead.

**Partial runs become normal, not exceptional.** With independent retries, a run
sits at `partial` routinely rather than as an error state. The UI already reads
per-asset status, and `cg_assets_roll_up_run` keeps the run in step, but any
code branching on `status == 'complete'` needs revisiting.
