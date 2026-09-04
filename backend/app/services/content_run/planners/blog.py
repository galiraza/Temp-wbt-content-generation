"""Plans a blog run: one task per blog.

Blogs split cleanly. Each one covers a different topic from the pasted content
plan, and each already runs its own write / QC / revise loop, so a blog written
on its own is the same blog. There is no reconcile pass because there is nothing
for it to do: two blogs on different topics do not accidentally share a
sentence, and the QC agent is already checking each one.

`run_metadata` is the prepare phase and cannot be skipped or parallelised with
the writing. It does two things at once already: scrapes the client's website
and parses the plan. Every blog prompt injects the scraped site, so a blog
written without it invents the client's services.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Dict, List

from app.agents.blog_generation.pipeline import run_metadata, write_one_blog
from app.services.content_run.tasks import Plan, Task

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BlogRequest:
    """Every attribute the blog agents read off a request row, and no more.

    Two phases read different fields, which is why they are all here:
    `run_metadata` needs `website_url` and `blog_schema_raw`, and `write_blog`
    and `audit_blog` need `client_name`, `website_content` and the three cluster
    themes. `website_content` is produced by the first phase, so the request the
    tasks get is a second one built with it filled in.

    Frozen for the same reason RequestSnapshot is: it crosses into worker
    threads and must not look writable.
    """

    id: int
    client_name: str = ""
    website_url: str = ""
    blog_schema_raw: str = ""
    website_content: str = ""
    cluster_theme_1: str = ""
    cluster_theme_2: str = ""
    cluster_theme_3: str = ""


def plan(source: Dict[str, Any], run_id: Any, counts: Dict[str, int]) -> Plan:
    """One task per blog in the plan.

    `counts` is not used to decide how many. The blog form already carries
    `cluster_number`, and the parsed plan says which topics exist, so a settings
    number would be a third source of truth disagreeing with the two that the
    operator can actually see. This is why `blogs` is in DERIVED_SECTIONS.
    """
    def field(*names: str) -> str:
        for name in names:
            value = source.get(name)
            if value:
                return str(value)
        return ""

    intake = _BlogRequest(
        id=0,
        client_name=field("client_name", "business_name"),
        website_url=field("website_url"),
        blog_schema_raw=field("blog_schema_raw", "blog_schema"),
        cluster_theme_1=field("cluster_theme_1"),
        cluster_theme_2=field("cluster_theme_2"),
        cluster_theme_3=field("cluster_theme_3"),
    )
    if not intake.website_url:
        return Plan(
            error="This run has no website URL, and every blog is written from "
            "the client's own site."
        )

    outcome = run_metadata(intake)
    blogs = list(getattr(outcome, "blogs", None) or [])
    if not blogs:
        error = getattr(outcome, "error", None)
        return Plan(
            error=error
            or "The content plan did not parse into any blogs. Check the pasted plan."
        )

    website_content = getattr(outcome, "website_content", None) or ""
    if not website_content:
        # The v1 service refuses the same case for the same reason: every blog
        # prompt injects the scraped site, so writing without it means the model
        # inventing the client's services. Failing here costs one scrape;
        # failing to check costs a run of fabricated blogs that read fine.
        return Plan(
            error="The client's website could not be read, so there is nothing "
            "to write the blogs from. Check the URL and try again."
        )

    # The same request with the scrape filled in. Rebuilt rather than mutated
    # because it is frozen, and it is frozen because the tasks below take it
    # into worker threads.
    request = replace(intake, website_content=website_content)

    # Honour a lower cap if the form asked for fewer than the plan lists. Never
    # a higher one: asking for eight blogs from a four topic plan would mean
    # inventing four topics.
    wanted = _wanted(source, len(blogs))
    if wanted < len(blogs):
        logger.info(
            "blog_plan_trimmed run_id=%s parsed=%s wanted=%s",
            run_id,
            len(blogs),
            wanted,
        )
        blogs = blogs[:wanted]

    tasks: List[Task] = []
    for position, item in enumerate(blogs):
        tasks.append(
            Task(
                key=f"blog:{getattr(item, 'blog_number', position + 1)}",
                section="blogs",
                position=position,
                title=_title_of(item, position),
                run=_runner(request, item),
                payload={"blog_number": getattr(item, "blog_number", position + 1)},
            )
        )

    return Plan(tasks=tasks, prepared={"blogs_parsed": len(blogs)})


def _wanted(source: Dict[str, Any], parsed: int) -> int:
    raw = source.get("cluster_number") or source.get("blog_count")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return parsed
    return max(1, min(value, parsed))


def _title_of(item: Any, position: int) -> str:
    # blog_title first: that is the field BlogMetadata declares. The others
    # are only there so a shape change shows up as a worse title rather than
    # as "Blog 3" for every blog.
    for attr in ("blog_title", "title", "topic", "keyword"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return f"Blog {position + 1}"


def _runner(request: _BlogRequest, item: Any):
    def run() -> str:
        outcome = write_one_blog(request, item)
        # BlogOutcome carries the finished blog plus its QC audits. Only the
        # copy is stored: the audits belong to the v1 tables that have a row per
        # round, and repeating them on an asset version would put review
        # machinery in front of someone reading the blog.
        # status is passed | failed_qc | failed. failed_qc still has content
        # worth reviewing by hand, which is why the pipeline distinguishes it,
        # so it is kept rather than treated as a failure.
        if isinstance(outcome.content, str) and outcome.content.strip():
            return outcome.content
        raise RuntimeError(outcome.error or "The blog came back empty.")

    return run
