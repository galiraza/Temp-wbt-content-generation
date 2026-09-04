"""THE PIPELINE - the blog loop, and how it runs.

This is the file to read to understand the whole flow. Everything below is pure:
it takes the request row and the blog rows, calls the agents, and returns what
they produced. No database writes happen here — app.services.
blog_generation_service owns those, which is what lets blogs run on separate
threads without sharing a SQLAlchemy Session (Sessions are not thread-safe).


    PHASE 1   POST /api/blog-generation/{id}/extract-metadata
                          |
                 +--------+--------+                 <-- ThreadPoolExecutor(2)
                 |                 |                     scrape and parse TOGETHER
                 v                 v
          Firecrawl scrape   metadata chain
                 |           prompt | llm | BlogMetadataList
                 v                 |
          website content          |
          prompt | llm | text      |
                 |                 |
                 +--------+--------+
                          |
                          v
                  MetadataOutcome
              (raw markdown, structured
               markdown, blog briefs)
                          |
                  the service writes one
                  Blog row per brief


    PHASE 2   POST /api/blog-generation/{id}/generate      (background)
                          |
                          v
              run_blogs(request, blogs)
                          |
        +--------+--------+--------+--------+          <-- ThreadPoolExecutor(N)
        |        |        |        |        |              blogs run TOGETHER
        v        v        v        v        v
      blog 1   blog 2   blog 3   ...      blog 12
        |
        |   each one, independently:
        |
        |     write_blog  -----------------+
        |          |                       |
        |          v                       |
        |     audit_blog  (round 1)        |
        |          |                       |
        |     score >= 7 ? --yes--> passed |
        |          | no                    |
        |     round == MAX ? --yes--> failed_qc (content kept)
        |          | no                    |
        |     revise_blog ------> audit_blog (round 2) ...
        |
        v
    BlogOutcome per blog -> the service writes it the moment it lands


Why phase 2 fans out over blogs rather than running them in sequence:
  n8n's splitInBatches processed one blog at a time, so twelve blogs cost twelve
  full write-QC-revise cycles end to end. Nothing in a blog depends on another
  blog, so they overlap. The cap is what keeps twelve concurrent Sonnet calls
  from hitting a rate limit.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from app.agents.blog_generation.blog_writer import revise_blog, write_blog
from app.agents.blog_generation.metadata_agent import extract_metadata, structure_website
from app.agents.blog_generation.parsers import BlogMetadata, QcAudit, split_blog_output
from app.agents.blog_generation.qc_agent import audit_blog
from app.errors import UpstreamServiceError
from app.models.blog_generation.blog import MAX_QC_ROUNDS

logger = logging.getLogger("app")

#: How many blogs are written at once. Each one is a chain of up to
#: MAX_QC_ROUNDS * 2 Sonnet calls, so this is the knob that trades wall-clock
#: against rate limits.
MAX_CONCURRENT_BLOGS = 3

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.5


@dataclass
class MetadataOutcome:
    """What phase 1 produced, or why it didn't."""

    scraped_markdown: Optional[str] = None
    website_content: Optional[str] = None
    blogs: List[BlogMetadata] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.blogs)


@dataclass
class BlogOutcome:
    """One blog's final state after its write-QC-revise loop.

    `status` is "failed_qc" rather than "failed" when the loop ran out of rounds:
    the content exists and is worth editing by hand, which is a different thing
    from the model having blown up. n8n conflated the two — it moved on with the
    row left holding whatever the last upsert wrote.
    """

    blog_number: int
    status: str  # passed | failed_qc | failed
    content: Optional[str] = None
    gmb_post: Optional[str] = None
    gmb_faq: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    general_notes: Optional[str] = None
    audits: List[QcAudit] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def final_audit(self) -> Optional[QcAudit]:
        return self.audits[-1] if self.audits else None

    @property
    def rounds(self) -> int:
        return len(self.audits)


def _with_retry(func, *args, **kwargs):
    """Retries a flaky model call before giving up, same as post_generation's
    pipeline: transient network blips to the model APIs have been seen in this
    environment and succeed on a retry."""
    import time

    last_exc: Exception = RuntimeError("_with_retry called with zero attempts")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return func(*args, **kwargs)
        except UpstreamServiceError as exc:
            # A missing key, a dead website or a refusal will not fix itself on a
            # retry, and retrying wastes the user's time. A structured-output
            # schema mismatch is the exception: that is one bad reply, and asking
            # again usually gets a valid one. structured_llm flags those.
            if not getattr(exc, "retryable", False):
                raise
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS)
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc


def _message_of(exc: Exception) -> str:
    """Prefer our own user-facing wording over a raw exception string."""
    return str(getattr(exc, "message", None) or exc)


# --------------------------------------------------------------------------
# Phase 1
# --------------------------------------------------------------------------


def run_metadata(request) -> MetadataOutcome:
    """Scrapes and structures the website while parsing the pasted plan.

    Neither half needs the other, so they overlap. A failed scrape is still fatal
    to the phase: every blog prompt injects the website content, and writing a
    cluster without it means inventing the client's services.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        website_future = pool.submit(_with_retry, structure_website, request.website_url)
        metadata_future = pool.submit(_with_retry, extract_metadata, request.blog_schema_raw)

        raw = structured = None
        blogs: List[BlogMetadata] = []
        errors: List[str] = []

        try:
            raw, structured = website_future.result()
        except Exception as exc:
            errors.append(_message_of(exc))
            logger.exception("blog_website_failed request_id=%s", request.id)

        try:
            blogs = metadata_future.result()
        except Exception as exc:
            errors.append(_message_of(exc))
            logger.exception("blog_metadata_failed request_id=%s", request.id)

    if not blogs or structured is None:
        return MetadataOutcome(
            scraped_markdown=raw,
            website_content=structured,
            blogs=[],
            error="\n".join(errors) or "Couldn't read the content plan.",
        )

    return MetadataOutcome(
        scraped_markdown=raw,
        website_content=structured,
        blogs=blogs,
        error="\n".join(errors) or None,
    )


# --------------------------------------------------------------------------
# Phase 2
# --------------------------------------------------------------------------


def write_one_blog(request, blog) -> BlogOutcome:
    """The write-QC-revise loop for ONE blog. Never raises.

    The loop shape is n8n's, with two corrections:

      * the round ceiling is compared with `>=`, not `== 4`. n8n's exact equality
        against a shared counter could be stepped over, and then the blog looped
        forever.
      * every audit is returned, not just the last. The service writes one
        BlogQcRound row per audit.
    """
    sections: Dict[str, Optional[str]] = {}
    audits: List[QcAudit] = []
    current: Optional[str] = None

    try:
        current = _with_retry(write_blog, request, blog)
        sections = split_blog_output(current)

        for round_number in range(1, MAX_QC_ROUNDS + 1):
            audit = _with_retry(
                audit_blog,
                request,
                blog,
                content=sections.get("content") or current,
                round_number=round_number,
                is_revision=round_number > 1,
            )
            audits.append(audit)

            if audit.passed:
                return BlogOutcome(
                    blog_number=blog.blog_number,
                    status="passed",
                    audits=audits,
                    **sections,
                )

            if round_number >= MAX_QC_ROUNDS:
                logger.warning(
                    "blog_qc_exhausted blog_number=%s rounds=%s score=%s",
                    blog.blog_number,
                    round_number,
                    audit.score,
                )
                return BlogOutcome(
                    blog_number=blog.blog_number,
                    status="failed_qc",
                    audits=audits,
                    **sections,
                )

            current = _with_retry(
                revise_blog,
                request,
                blog,
                original=sections.get("content") or current,
                audit=audit,
                round_number=round_number,
            )
            revised = split_blog_output(current)
            # A revision that dropped a section keeps the previous one rather
            # than blanking it: the prompt tells the agent to touch only what was
            # flagged, so an absent section means "unchanged", not "deleted".
            sections = {key: revised.get(key) or sections.get(key) for key in revised}

    except Exception as exc:
        logger.exception(
            "blog_write_failed request_id=%s blog_number=%s", request.id, blog.blog_number
        )
        return BlogOutcome(
            blog_number=blog.blog_number,
            status="failed",
            audits=audits,
            error=_message_of(exc),
            **{k: sections.get(k) for k in (
                "content", "gmb_post", "gmb_faq",
                "meta_title", "meta_description", "general_notes",
            )},
        )

    # Unreachable: the loop always returns. Here so a future edit that changes the
    # range cannot fall through and return None.
    return BlogOutcome(
        blog_number=blog.blog_number,
        status="failed",
        audits=audits,
        error="The revision loop ended without a verdict.",
    )


def run_blogs(request, blogs, on_result: Optional[Callable[[BlogOutcome], None]] = None) -> List[BlogOutcome]:
    """Writes every blog, up to MAX_CONCURRENT_BLOGS at a time.

    `on_result` is called with each outcome as it finishes, on THIS thread rather
    than the worker that produced it — which is what lets the service persist
    using its own Session without sharing it across threads. The service uses it
    to write a finished blog immediately, so a 12-blog run fills the UI in as it
    goes and a crash halfway through does not lose the blogs that already passed.

    Ordered by completion, not submission, so a slow blog 1 does not hold back
    persisting blog 2. Order does not matter: every outcome carries its own
    blog_number.

    One blog failing never affects another: each outcome carries its own status.
    """
    outcomes: List[BlogOutcome] = []

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BLOGS) as pool:
        futures = [pool.submit(write_one_blog, request, blog) for blog in blogs]
        for future in as_completed(futures):
            outcome = future.result()  # write_one_blog never raises
            outcomes.append(outcome)
            if on_result is not None:
                try:
                    on_result(outcome)
                except Exception:
                    # A persistence failure for one blog must not abandon the
                    # rest of the run; the row keeps its "generating" status and
                    # the log carries the reason.
                    logger.exception(
                        "blog_persist_failed request_id=%s blog_number=%s",
                        request.id,
                        outcome.blog_number,
                    )

    logger.info(
        "blog_run_done request_id=%s passed=%s failed_qc=%s failed=%s",
        request.id,
        sum(1 for o in outcomes if o.status == "passed"),
        sum(1 for o in outcomes if o.status == "failed_qc"),
        sum(1 for o in outcomes if o.status == "failed"),
    )
    return outcomes
