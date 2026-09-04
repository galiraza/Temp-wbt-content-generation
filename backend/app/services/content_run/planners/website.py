"""Plans a website run: one task per page group, as the prompts are written.

One task per key in PAGE_ORDER, each calling `write_page` exactly as the
existing pipeline does. `service`, `service_area` and `other` each write every
page of their kind in one reply, which is what their prompts ask for and what
the client signed off on, so a run produces five page groups and stores each
whole.

WHY NOT ONE TASK PER PAGE. It was built, measured and rejected, and the reasons
are worth keeping because the idea is an obvious one to have again.

  it needs the prompts changed  The bundled prompts say to write a page for each
        service in the sitemap. Narrowing one to a single page means appending a
        directive that overrides that, and narrowing the prompt variable holding
        the list. The prompt text is untouched, but what a run produces is not,
        and the current output is signed off.

  it loses cross-page uniqueness  The prompts keep their own promise by having
        the siblings in front of them: no sentence on two pages, while the trust
        bar, Why Choose Us, Areas We Cover and the CTA stay identical sitewide.
        A page written alone cannot do that. Replacing it took two mechanisms,
        sibling openings during the run and a dedupe pass after it, and both are
        approximations of something the bundled reply gets for free.

  it is SLOWER  This is the one that settles it. Refinement is per task: the
        bundled path runs five critic/refiner/evaluator loops, one per page
        group, and the split runs one per page. For a client with six services,
        five areas and eight other pages that is 21 loops instead of 5, so
        roughly 84 model calls instead of 20 against the same three workers. A
        measured run reached 10 of 21 pages in eleven minutes; the bundled path
        finishes in about three.

The single-page machinery is still in the tree, unused: `write_single_page`,
`prompts/single_page.py`, and `dedupe.reconcile_pages`. It becomes worth
revisiting only if refinement moves out of the per-item path, which is what
makes the arithmetic above turn around.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agents.website_content.page_agents import (
    PAGE_ORDER,
    PAGE_SPECS,
    write_page,
)
from app.agents.website_content.pipeline import (
    RequestSnapshot,
    build_content_brief,
    run_intake,
)
from app.agents.website_content.parsers import SitemapData
from app.agents.website_content.refine import refine_section
from app.services.content_run.tasks import Plan, Task

logger = logging.getLogger(__name__)

#: The `source` keys that map straight onto RequestSnapshot fields.
#:
#: Listed rather than derived from the dataclass, because `source` is written by
#: two things (the sync, from the v1 request tables, and the form) and a silent
#: rename on either side should show up as a missing field here rather than as a
#: page written without a phone number.
_SNAPSHOT_KEYS = (
    "business_name",
    "phone_number",
    "email",
    "address",
    "country",
    "state_province_region",
    "zip_postal_code",
    "usps",
    "sitemap_text",
    "other_industries",
    "fathom_meeting_1_url",
    "fathom_meeting_2_url",
    "fathom_meeting_3_url",
    "loom_1_summary",
    "loom_1_transcript",
    "loom_2_summary",
    "loom_2_transcript",
    "loom_3_summary",
    "loom_3_transcript",
)

#: Which page agents write several pages in one reply, and the key their list
#: lives under in meeting_insights["sitemap_structure"].
#:
#: Nothing in this module reads it any more: the plan above runs each agent
#: whole. It stays as the record of which agents bundle, which is what the
#: single-page machinery would need if the arithmetic in the docstring ever
#: turns around, and what the tests assert the directives cover.
#:
#: sitemap_structure, not sitemap_data. Both carry a services list and they are
#: not the same list: sitemap_data is what the extractor read off the client
#: sheet, sitemap_structure is what the analyst decided the site should have,
#: and it is sitemap_structure that the brief renders into {sitemap} and the
#: prompts iterate. Reading the other one would produce pages for services the
#: prompt was never told about.
_BUNDLED = {
    "service": "services",
    "service_area": "service_areas",
    "other": "other_pages",
}



def _snapshot(source: Dict[str, Any], run_id: Any) -> RequestSnapshot:
    """Builds the thread-safe brief from the run's frozen `source`.

    `snapshot(row)` in the website pipeline does this from a v1 request row.
    This does it from jsonb, for the same reason and with the same contract: it
    is built once here, on the thread that owns the Session, and the workers
    only ever see the frozen result.

    `id` is an int on RequestSnapshot and a run_id is a uuid, so the id is only
    used for log correlation. Passing 0 keeps the type honest; the run id goes
    into the log line the orchestrator writes instead.
    """
    industries = source.get("industries") or []
    if isinstance(industries, str):
        industries = [industries]
    return RequestSnapshot(
        id=0,
        industries=tuple(industries),
        **{key: (source.get(key) or "") for key in _SNAPSHOT_KEYS},
    )


def prepare(source: Dict[str, Any], run_id: Any) -> Dict[str, Any]:
    """Runs intake once, and returns the brief every page task then reads.

    Intake is the sitemap parse, the industry match and the meeting transcript
    pass. It cannot be parallelised with the pages because the pages are written
    from its output, and it must not be run per page because it would then run
    seventeen times for one identical result.

    A run whose `source` already carries `sitemap_data` and `meeting_insights`
    skips the model calls: those are the intake products, and a run synced from
    the v1 tables already has them. Re-deriving them would change the brief
    underneath a re-run, which is the opposite of what freezing `source` is for.
    """
    request = _snapshot(source, run_id)

    cached_sitemap = source.get("sitemap_data")
    cached_insights = source.get("meeting_insights")
    if cached_sitemap and cached_insights is not None:
        # meetings=None is safe: build_content_brief takes the parameter but its
        # body never reads it, because everything the transcripts contributed
        # arrives already folded into `insights` by the analyst. Checked, not
        # assumed. If that ever changes this call is where it will surface.
        brief = build_content_brief(
            request,
            None,
            SitemapData(**cached_sitemap),
            cached_insights,
            _as_list(source.get("resolved_industries")),
        )
        return {
            "brief": brief,
            "sitemap_data": cached_sitemap,
            "meeting_insights": cached_insights,
            "request": request,
            "reused_intake": True,
        }

    outcome = run_intake(request)
    if not outcome.ok:
        return {"error": outcome.error or "Intake did not produce a brief."}

    return {
        "brief": outcome.brief,
        "sitemap_data": _sitemap_dict(outcome.sitemap),
        "meeting_insights": outcome.meeting_insights,
        "matched_industries": outcome.matched_industries,
        "note": outcome.note,
        "request": request,
        "reused_intake": False,
    }


def _as_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _sitemap_dict(sitemap: Any) -> Dict[str, Any]:
    """SitemapData as plain jsonb, so it survives a round trip through `source`."""
    if sitemap is None:
        return {}
    if isinstance(sitemap, dict):
        return sitemap
    for attr in ("model_dump", "dict", "_asdict"):
        fn = getattr(sitemap, attr, None)
        if callable(fn):
            return fn()
    return dict(getattr(sitemap, "__dict__", {}) or {})


def plan(source: Dict[str, Any], run_id: Any, counts: Dict[str, int]) -> Plan:
    """One task per page group. `counts` is unused: a website run follows the sitemap.

    `counts` is in the signature because every planner has the same one, and
    `pages` is in DERIVED_SECTIONS precisely because this is the planner that
    ignores it. Asking for six pages when the sitemap lists nine would have to
    either drop three or invent three.

    Five tasks over three workers, which is the concurrency the existing
    pipeline already uses. No reconcile: the bundled prompts keep their own
    cross-page uniqueness rule, so there is nothing left for a dedupe pass to
    do that would not be second-guessing them.
    """
    prepared = prepare(source, run_id)
    if prepared.get("error"):
        return Plan(error=prepared["error"])

    brief: Dict[str, Any] = prepared["brief"]

    tasks: List[Task] = [
        Task(
            key=key,
            section="pages",
            position=position,
            title=PAGE_SPECS[key].section_title,
            run=_page_runner(key, brief),
            payload={"page": key},
        )
        for position, key in enumerate(PAGE_ORDER)
    ]

    logger.info("website_plan run_id=%s page_groups=%s", run_id, len(tasks))
    return Plan(
        tasks=tasks,
        prepared={
            key: prepared[key]
            for key in ("sitemap_data", "meeting_insights", "note", "reused_intake")
            if prepared.get(key) is not None
        },
    )


def _page_runner(key: str, brief: Dict[str, Any]):
    """Closure for an unbundled page. Refines, as the existing pipeline does."""

    def run() -> str:
        draft = write_page(key, brief)
        return _refined(draft, label=key)

    return run


def _refined(draft: str, label: str) -> str:
    """Critic/Refiner/Evaluator, exactly as write_section runs it.

    Falls back to the draft when refinement errors: an unrefined page is worth
    keeping and reviewing, and the existing pipeline makes the same call by
    giving that case the status `unrefined` rather than `failed`.
    """
    result = refine_section(draft, label=label)
    if result.error is not None:
        logger.warning("website_refine_failed label=%s %s", label, result.error)
        return draft
    return result.content or draft
