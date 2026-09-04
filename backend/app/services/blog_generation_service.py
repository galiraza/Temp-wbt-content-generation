"""Database writes and row-to-schema mapping for blog generation.

app.agents.blog_generation.pipeline is pure and owns no Session; this module owns
every write. The split is what lets the pipeline fan blogs out across threads.

Phase 2 runs in a background thread because it is far too slow for a request:
twelve blogs at up to MAX_QC_ROUNDS audits each is up to ~84 Sonnet calls. The
endpoint returns 202 and the UI polls, rather than holding a connection open for
the length of the run.
"""

import json
import logging
import threading
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.agents.blog_generation.parsers import word_count
from app.agents.blog_generation.pipeline import (
    BlogOutcome,
    run_blogs,
    run_metadata,
)
from app.config import has_anthropic_key
from app.database import SessionLocal
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

#: Request ids with a generation thread currently running. Guards against a
#: double-click starting two runs over the same rows, which would have two
#: threads writing the same blog.
_running: set = set()
_running_lock = threading.Lock()


# --------------------------------------------------------------------------
# Row -> schema
# --------------------------------------------------------------------------


def blog_to_out(row: models.Blog) -> schemas.BlogOut:
    return schemas.BlogOut(
        id=row.id,
        request_id=row.request_id,
        blog_number=row.blog_number,
        title=row.title,
        funnel_stage=row.funnel_stage,
        service_areas=row.service_area_list,
        keywords=row.keyword_list,
        content=row.content,
        gmb_post=row.gmb_post,
        gmb_faq=row.gmb_faq,
        meta_title=row.meta_title,
        meta_description=row.meta_description,
        general_notes=row.general_notes,
        qc_score=row.qc_score,
        qc_result=row.qc_result,
        qc_word_count=row.qc_word_count,
        qc_fixes=row.fix_list,
        qc_breakdown=row.breakdown,
        revision_attempts=row.revision_attempts,
        word_count=word_count(row.content),
        status=row.status,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def qc_round_to_out(row: models.BlogQcRound) -> schemas.BlogQcRoundOut:
    return schemas.BlogQcRoundOut(
        id=row.id,
        round_number=row.round_number,
        score=row.score,
        result=row.result,
        word_count=row.word_count,
        fixes=row.fix_list,
        breakdown=row.breakdown_dict,
        created_at=row.created_at,
    )


def blog_to_detail(row: models.Blog) -> schemas.BlogDetailOut:
    base = blog_to_out(row)
    return schemas.BlogDetailOut(
        **base.model_dump(),
        qc_rounds=[qc_round_to_out(r) for r in row.qc_rounds],
    )


def request_to_out(row: models.BlogGenerationRequest) -> schemas.BlogGenerationRequestOut:
    blogs = row.blogs or []
    return schemas.BlogGenerationRequestOut(
        id=row.id,
        client_name=row.client_name,
        website_url=row.website_url,
        cluster_theme_1=row.cluster_theme_1,
        cluster_theme_2=row.cluster_theme_2,
        cluster_theme_3=row.cluster_theme_3,
        cluster_number=row.cluster_number,
        blog_schema_raw=row.blog_schema_raw,
        metadata_status=row.metadata_status,
        content_status=row.content_status,
        error_message=row.error_message,
        has_scraped_website=bool(row.scraped_markdown),
        has_website_content=bool(row.website_content),
        blog_count=len(blogs),
        passed_count=sum(1 for b in blogs if b.status == "passed"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --------------------------------------------------------------------------
# Phase 1 — metadata
# --------------------------------------------------------------------------


def run_metadata_extraction(db: Session, request: models.BlogGenerationRequest) -> None:
    """Scrapes the site, structures it, parses the plan, and writes one Blog row
    per brief.

    Replaces every existing blog for this request: re-extracting means the plan
    changed, and keeping orphaned blogs from a previous parse would leave the
    cluster holding two different plans at once.
    """
    if not has_anthropic_key():
        request.metadata_status = "failed"
        request.error_message = "ANTHROPIC_API_KEY is not configured on the server."
        db.commit()
        raise ServiceNotConfiguredError(
            "Blog generation", internal="ANTHROPIC_API_KEY is unset"
        )

    request.metadata_status = "extracting"
    request.error_message = None
    db.commit()

    outcome = run_metadata(request)

    if not outcome.ok:
        request.metadata_status = "failed"
        request.error_message = outcome.error
        db.commit()
        raise UpstreamServiceError(
            "Blog generation",
            outcome.error or "Couldn't read the content plan. Please try again.",
            internal=f"metadata extraction failed for request {request.id}",
        )

    request.scraped_markdown = outcome.scraped_markdown
    request.website_content = outcome.website_content

    # Wipe and rewrite, so blog_number stays dense and matches the new plan.
    for existing in list(request.blogs):
        db.delete(existing)
    db.flush()

    for meta in outcome.blogs:
        db.add(
            models.Blog(
                request_id=request.id,
                blog_number=meta.blog_number,
                title=meta.blog_title,
                funnel_stage=meta.funnel_stage,
                service_areas=json.dumps(meta.service_areas or []),
                keywords=json.dumps(meta.keywords or []),
                status="pending",
            )
        )

    request.metadata_status = "complete"
    # Content has to be re-run against the new briefs.
    request.content_status = "pending"

    # A count that disagrees with the form is worth surfacing rather than
    # silently accepting: n8n hardcoded 12 and ignored the form's own number.
    found = len(outcome.blogs)
    expected = request.cluster_number
    if expected and expected != found:
        request.error_message = (
            f"The plan produced {found} blogs but the form said {expected}. "
            "Check the pasted Blog Schema before generating."
        )
    else:
        request.error_message = outcome.error

    db.commit()
    logger.info(
        "blog_metadata_saved request_id=%s blogs=%s expected=%s",
        request.id,
        found,
        expected,
    )


# --------------------------------------------------------------------------
# Phase 2 — content
# --------------------------------------------------------------------------


def _apply_outcome(db: Session, blog: models.Blog, outcome: BlogOutcome) -> None:
    """Writes one finished blog and its audit rounds."""
    blog.content = outcome.content
    blog.gmb_post = outcome.gmb_post
    blog.gmb_faq = outcome.gmb_faq
    blog.meta_title = outcome.meta_title
    blog.meta_description = outcome.meta_description
    blog.general_notes = outcome.general_notes
    blog.status = outcome.status
    blog.error_message = outcome.error
    blog.revision_attempts = outcome.rounds

    final = outcome.final_audit
    if final is not None:
        blog.qc_score = final.score
        blog.qc_result = final.result
        blog.qc_word_count = final.word_count
        blog.qc_fixes = json.dumps(final.fixes_required or [])
        blog.qc_breakdown = json.dumps(final.breakdown.model_dump())

    # Rewrite the audit trail rather than appending: a regeneration is a fresh
    # loop, and interleaving its rounds with the previous run's would make
    # round_number meaningless.
    for existing in list(blog.qc_rounds):
        db.delete(existing)
    db.flush()

    for index, audit in enumerate(outcome.audits, start=1):
        db.add(
            models.BlogQcRound(
                blog_id=blog.id,
                round_number=index,
                score=audit.score,
                result=audit.result,
                word_count=audit.word_count,
                fixes=json.dumps(audit.fixes_required or []),
                breakdown=json.dumps(audit.breakdown.model_dump()),
            )
        )


def _finalise_request(db: Session, request: models.BlogGenerationRequest) -> None:
    """Sets content_status from what the blogs actually ended up as."""
    blogs = request.blogs or []
    passed = sum(1 for b in blogs if b.status == "passed")
    failed = sum(1 for b in blogs if b.status == "failed")

    if not blogs:
        request.content_status = "failed"
    elif passed == len(blogs):
        request.content_status = "complete"
    elif passed == 0 and failed == len(blogs):
        request.content_status = "failed"
    else:
        # Some blogs never reached the threshold, or one model call died. Their
        # content is still there to edit, so this is not a failure of the run.
        request.content_status = "partial"

    messages = [
        f"Blog {b.blog_number}: {b.error_message}"
        for b in blogs
        if b.status == "failed" and b.error_message
    ]
    below = [b.blog_number for b in blogs if b.status == "failed_qc"]
    if below:
        messages.append(
            "Below the QC threshold after "
            f"{models.MAX_QC_ROUNDS} rounds: blog "
            + ", ".join(str(n) for n in sorted(below))
        )
    request.error_message = "\n".join(messages) or None
    db.commit()


def _generate_in_background(request_id: int) -> None:
    """The worker. Opens its own Session: this runs on a thread, and Sessions are
    not thread-safe, so it cannot borrow the request's."""
    db = SessionLocal()
    try:
        request = (
            db.query(models.BlogGenerationRequest)
            .filter(models.BlogGenerationRequest.id == request_id)
            .first()
        )
        if request is None:
            logger.warning("blog_generate_missing request_id=%s", request_id)
            return

        blogs = list(request.blogs)
        if not blogs:
            request.content_status = "failed"
            request.error_message = "No blogs to write. Extract the content plan first."
            db.commit()
            return

        by_number: Dict[int, models.Blog] = {b.blog_number: b for b in blogs}

        for blog in blogs:
            blog.status = "generating"
            blog.error_message = None
        request.content_status = "generating"
        request.error_message = None
        db.commit()

        def persist(outcome: BlogOutcome) -> None:
            # Called on this thread by run_blogs, so using `db` here is safe.
            blog = by_number.get(outcome.blog_number)
            if blog is None:
                logger.warning(
                    "blog_outcome_unmatched request_id=%s blog_number=%s",
                    request_id,
                    outcome.blog_number,
                )
                return
            _apply_outcome(db, blog, outcome)
            db.commit()

        run_blogs(request, blogs, on_result=persist)

        db.refresh(request)
        _finalise_request(db, request)
    except Exception as exc:
        logger.exception("blog_generate_crashed request_id=%s", request_id)
        try:
            db.rollback()
            request = (
                db.query(models.BlogGenerationRequest)
                .filter(models.BlogGenerationRequest.id == request_id)
                .first()
            )
            if request is not None:
                request.content_status = "failed"
                request.error_message = str(getattr(exc, "message", None) or exc)
                # Blogs left mid-flight would otherwise poll as "generating"
                # forever, with no thread left to finish them.
                for blog in request.blogs:
                    if blog.status == "generating":
                        blog.status = "failed"
                        blog.error_message = "The generation run stopped unexpectedly."
                db.commit()
        except Exception:
            logger.exception("blog_generate_cleanup_failed request_id=%s", request_id)
    finally:
        db.close()
        with _running_lock:
            _running.discard(request_id)


def is_running(request_id: int) -> bool:
    with _running_lock:
        return request_id in _running


def start_generation(db: Session, request: models.BlogGenerationRequest) -> bool:
    """Starts phase 2 on a background thread. Returns False if already running.

    A daemon thread, deliberately: this is in-process work with no queue behind
    it, so a server restart mid-run abandons it. The rows left on "generating"
    are what makes that visible, and re-running is always safe.
    """
    if not has_anthropic_key():
        raise ServiceNotConfiguredError(
            "Blog generation", internal="ANTHROPIC_API_KEY is unset"
        )

    with _running_lock:
        if request.id in _running:
            return False
        _running.add(request.id)

    request.content_status = "generating"
    request.error_message = None
    for blog in request.blogs:
        blog.status = "generating"
    db.commit()

    thread = threading.Thread(
        target=_generate_in_background,
        args=(request.id,),
        name=f"blog-generate-{request.id}",
        daemon=True,
    )
    thread.start()
    logger.info("blog_generate_started request_id=%s blogs=%s", request.id, len(request.blogs))
    return True


def regenerate_one(db: Session, request: models.BlogGenerationRequest, blog: models.Blog) -> models.Blog:
    """Re-runs the whole write-QC-revise loop for ONE blog, inline.

    Inline rather than backgrounded: one blog is up to eight calls, which fits in
    a request the way twelve blogs do not. The frontend gives it the longer
    generation timeout.
    """
    if not has_anthropic_key():
        raise ServiceNotConfiguredError(
            "Blog generation", internal="ANTHROPIC_API_KEY is unset"
        )
    if not request.website_content:
        raise UpstreamServiceError(
            "Blog generation",
            "This job has no website content yet. Re-extract the content plan first.",
            internal=f"request {request.id} has no website_content",
        )

    from app.agents.blog_generation.pipeline import write_one_blog

    blog.status = "generating"
    blog.error_message = None
    db.commit()

    outcome = write_one_blog(request, blog)
    _apply_outcome(db, blog, outcome)
    db.commit()

    db.refresh(request)
    _finalise_request(db, request)
    db.refresh(blog)
    return blog
