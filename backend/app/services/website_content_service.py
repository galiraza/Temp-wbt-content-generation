"""Database writes and row-to-schema mapping for website content generation.

app.agents.website_content.pipeline is pure and owns no Session; this module owns
every write. The split is what lets the pipeline fan the six sections out across
threads.

The run happens in a background thread because it is far too slow for a request:
intake is four model calls, then six sections at up to seven each -- upwards of
forty Sonnet calls, most of them writing thousands of words. The endpoint returns
202 and the UI polls, rather than holding a connection open for the length of the
run. n8n solved the same problem by answering the form immediately and delivering
to a webhook much later.
"""

import json
import logging
import threading
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.agents.website_content.parsers import word_count
from app.agents.website_content.pipeline import (
    SECTION_ORDER,
    IntakeOutcome,
    SectionOutcome,
    run_intake,
    run_sections,
    snapshot,
)
from app.config import has_anthropic_key
from app.database import SessionLocal
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

_SERVICE = "Website content generation"

#: Request ids with a run currently in flight. Guards against a double-click
#: starting two runs over the same rows, which would have two threads writing
#: the same section.
_running: set = set()
_running_lock = threading.Lock()


# --------------------------------------------------------------------------
# Row -> schema
# --------------------------------------------------------------------------


def section_to_out(row: models.WebsiteSection) -> schemas.SectionOut:
    return schemas.SectionOut(
        id=row.id,
        request_id=row.request_id,
        section_key=row.section_key,
        section_title=row.section_title,
        position=row.position,
        content=row.content,
        word_count=word_count(row.content),
        blog_industry=row.blog_industry,
        blog_service=row.blog_service,
        blog_titles=row.blog_titles,
        blog_keywords=row.blog_keywords,
        refinement_turns=row.refinement_turns,
        verdict=row.verdict,
        verdict_reason=row.verdict_reason,
        checks=row.check_results,
        status=row.status,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def round_to_out(row: models.WebsiteRefinementRound) -> schemas.RefinementRoundOut:
    return schemas.RefinementRoundOut(
        id=row.id,
        turn=row.turn,
        critic_report=row.critic_report,
        refined_content=row.refined_content,
        verdict=row.verdict,
        reason=row.reason,
        checks=row.check_results,
        carry_forward=[schemas.CarryForwardOut(**issue) for issue in row.carry_forward_list],
        created_at=row.created_at,
    )


def section_to_detail(row: models.WebsiteSection) -> schemas.SectionDetailOut:
    base = section_to_out(row)
    return schemas.SectionDetailOut(
        **base.model_dump(),
        draft=row.draft,
        rounds=[round_to_out(r) for r in row.rounds],
    )


def _request_fields(row: models.WebsiteContentRequest) -> dict:
    sections = row.sections or []
    return {
        "id": row.id,
        "business_name": row.business_name,
        "phone_number": row.phone_number,
        "email": row.email,
        "address": row.address,
        "country": row.country,
        "state_province_region": row.state_province_region,
        "zip_postal_code": row.zip_postal_code,
        "usps": row.usps,
        "sitemap_text": row.sitemap_text,
        "industries": row.industries_list,
        "other_industries": row.other_industries,
        "fathom_meeting_1_url": row.fathom_meeting_1_url,
        "fathom_meeting_2_url": row.fathom_meeting_2_url,
        "fathom_meeting_3_url": row.fathom_meeting_3_url,
        "loom_1_summary": row.loom_1_summary,
        "loom_1_transcript": row.loom_1_transcript,
        "loom_2_summary": row.loom_2_summary,
        "loom_2_transcript": row.loom_2_transcript,
        "loom_3_summary": row.loom_3_summary,
        "loom_3_transcript": row.loom_3_transcript,
        "resolved_industries": row.resolved_industries,
        "status": row.status,
        "error_message": row.error_message,
        "note": row.note,
        "has_meeting_insights": bool(row.meeting_insights),
        "has_sitemap_data": bool(row.sitemap_data),
        "section_count": len(sections),
        "passed_count": sum(1 for s in sections if s.status == "passed"),
        "total_words": sum(word_count(s.content) for s in sections),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def request_to_out(row: models.WebsiteContentRequest) -> schemas.WebsiteContentRequestOut:
    return schemas.WebsiteContentRequestOut(**_request_fields(row))


def request_to_detail(
    row: models.WebsiteContentRequest,
) -> schemas.WebsiteContentRequestDetailOut:
    return schemas.WebsiteContentRequestDetailOut(
        **_request_fields(row),
        meeting_insights=row.insights,
        sitemap_data=row.sitemap,
    )


# --------------------------------------------------------------------------
# Row creation
# --------------------------------------------------------------------------


def create_request(
    db: Session, payload: schemas.WebsiteContentRequestCreate
) -> models.WebsiteContentRequest:
    """Saves the brief and the six empty section rows.

    The sections are created up front rather than as each one finishes, so the
    UI has something to render the moment the run starts: six cards on
    "generating" that fill in one at a time, instead of an empty list that grows.
    """
    row = models.WebsiteContentRequest(
        business_name=payload.business_name,
        phone_number=payload.phone_number,
        email=payload.email,
        address=payload.address,
        country=payload.country,
        state_province_region=payload.state_province_region,
        zip_postal_code=payload.zip_postal_code,
        usps=payload.usps,
        sitemap_text=payload.sitemap_text,
        industries=json.dumps(payload.industries or []),
        other_industries=payload.other_industries,
        fathom_meeting_1_url=payload.fathom_meeting_1_url,
        fathom_meeting_2_url=payload.fathom_meeting_2_url,
        fathom_meeting_3_url=payload.fathom_meeting_3_url,
        loom_1_summary=payload.loom_1_summary,
        loom_1_transcript=payload.loom_1_transcript,
        loom_2_summary=payload.loom_2_summary,
        loom_2_transcript=payload.loom_2_transcript,
        loom_3_summary=payload.loom_3_summary,
        loom_3_transcript=payload.loom_3_transcript,
        status="pending",
    )
    db.add(row)
    db.flush()

    for position, key in enumerate(models.SECTION_KEYS):
        db.add(
            models.WebsiteSection(
                request_id=row.id,
                section_key=key,
                section_title=models.SECTION_TITLES[key],
                position=position,
                status="pending",
            )
        )

    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def _apply_intake(db: Session, request: models.WebsiteContentRequest, outcome: IntakeOutcome) -> None:
    """Persists what the intake phase learned, so it survives the run.

    Written whether or not the phase succeeded: a parsed sitemap with a failed
    analyst is still the most useful thing to look at when working out why.
    """
    if outcome.sitemap is not None:
        request.sitemap_data = json.dumps(outcome.sitemap.model_dump(), ensure_ascii=False)
    if outcome.meeting_insights is not None:
        request.meeting_insights = json.dumps(outcome.meeting_insights, ensure_ascii=False)
    if outcome.brief:
        request.resolved_industries = outcome.brief.get("industries") or None
    request.note = outcome.note


def _apply_section(db: Session, section: models.WebsiteSection, outcome: SectionOutcome) -> None:
    """Writes one finished section and its refinement rounds."""
    section.content = outcome.content
    section.draft = outcome.draft
    section.status = outcome.status
    section.error_message = outcome.error
    section.refinement_turns = outcome.turns

    if outcome.blog_brief is not None:
        section.blog_industry = outcome.blog_brief.industry or None
        section.blog_service = outcome.blog_brief.service or None
        section.blog_titles = outcome.blog_brief.titles or None
        section.blog_keywords = outcome.blog_brief.keywords or None
        # The lead-in calls degrade rather than raise, so their notes are the
        # only record that (say) no keyword row matched.
        if outcome.blog_brief.notes and not section.error_message:
            section.error_message = " ".join(outcome.blog_brief.notes)

    final = outcome.rounds[-1] if outcome.rounds else None
    if final is not None:
        section.verdict = final.verdict
        section.verdict_reason = final.reason
        section.checks = json.dumps(final.checks)

    # Rewrite the audit trail rather than appending: a regeneration is a fresh
    # loop, and interleaving its turns with the previous run's would make `turn`
    # meaningless.
    for existing in list(section.rounds):
        db.delete(existing)
    db.flush()

    for round_ in outcome.rounds:
        db.add(
            models.WebsiteRefinementRound(
                section_id=section.id,
                turn=round_.turn,
                critic_report=round_.critic_report,
                refined_content=round_.refined_content,
                verdict=round_.verdict,
                reason=round_.reason,
                checks=json.dumps(round_.checks),
                carry_forward=json.dumps(
                    [issue.model_dump() for issue in round_.carry_forward], ensure_ascii=False
                ),
            )
        )


def _finalise(db: Session, request: models.WebsiteContentRequest) -> None:
    """Sets the request status from what the sections actually ended up as."""
    sections = request.sections or []
    passed = sum(1 for s in sections if s.status == "passed")
    failed = sum(1 for s in sections if s.status == "failed")

    if not sections:
        request.status = "failed"
    elif passed == len(sections):
        request.status = "complete"
    elif failed == len(sections):
        request.status = "failed"
    else:
        # Some sections need review, or one agent died. Their content is still
        # there to edit, so this is not a failure of the run.
        request.status = "partial"

    messages = [
        f"{s.section_title}: {s.error_message}"
        for s in sections
        if s.status == "failed" and s.error_message
    ]
    review = [s.section_title for s in sections if s.status in ("needs_review", "unrefined")]
    if review:
        messages.append("Worth a read before sending: " + ", ".join(sorted(review)))

    # The kickoff-meeting note is separate from errors and stays on `note`.
    request.error_message = "\n".join(messages) or None
    db.commit()


def _run_in_background(request_id: int, keys: Optional[List[str]] = None) -> None:
    """The worker. Opens its own Session: this runs on a thread, and Sessions are
    not thread-safe, so it cannot borrow the request's."""
    db = SessionLocal()
    try:
        request = (
            db.query(models.WebsiteContentRequest)
            .filter(models.WebsiteContentRequest.id == request_id)
            .first()
        )
        if request is None:
            logger.warning("website_run_missing request_id=%s", request_id)
            return

        selected = keys or SECTION_ORDER
        by_key: Dict[str, models.WebsiteSection] = {s.section_key: s for s in request.sections}

        for key in selected:
            section = by_key.get(key)
            if section is not None:
                section.status = "generating"
                section.error_message = None
        request.status = "generating"
        request.error_message = None
        db.commit()

        # Snapshot BEFORE anything fans out. Past this point the pipeline
        # must not touch the ORM row: its attributes are expired by the commit
        # above, so reading one off a worker thread would fire a lazy reload on
        # this Session while another thread is already using it.
        brief_snapshot = snapshot(request)

        outcome = run_intake(brief_snapshot)
        _apply_intake(db, request, outcome)

        if not outcome.ok:
            request.status = "failed"
            request.error_message = outcome.error or "The brief could not be prepared."
            for key in selected:
                section = by_key.get(key)
                if section is not None:
                    section.status = "failed"
                    section.error_message = "The brief could not be prepared."
            db.commit()
            logger.warning("website_intake_failed request_id=%s", request_id)
            return

        db.commit()

        def persist(result: SectionOutcome) -> None:
            # Called on this thread by run_sections, so using `db` here is safe.
            section = by_key.get(result.key)
            if section is None:
                logger.warning(
                    "website_section_unmatched request_id=%s key=%s", request_id, result.key
                )
                return
            _apply_section(db, section, result)
            db.commit()

        run_sections(brief_snapshot, outcome.brief, keys=selected, on_result=persist)

        db.refresh(request)
        _finalise(db, request)
    except Exception as exc:
        logger.exception("website_run_crashed request_id=%s", request_id)
        try:
            db.rollback()
            request = (
                db.query(models.WebsiteContentRequest)
                .filter(models.WebsiteContentRequest.id == request_id)
                .first()
            )
            if request is not None:
                request.status = "failed"
                request.error_message = str(getattr(exc, "message", None) or exc)
                # Sections left mid-flight would otherwise poll as "generating"
                # forever, with no thread left to finish them.
                for section in request.sections:
                    if section.status == "generating":
                        section.status = "failed"
                        section.error_message = "The generation run stopped unexpectedly."
                db.commit()
        except Exception:
            logger.exception("website_run_cleanup_failed request_id=%s", request_id)
    finally:
        db.close()
        with _running_lock:
            _running.discard(request_id)


def recover_abandoned_runs() -> int:
    """Clears rows left mid-run by a process that is no longer here.

    A run is a daemon thread with no queue behind it, so a restart -- a deploy, a
    crash, a developer hitting Ctrl+C -- abandons whatever was in flight. The
    rows stay on "generating" and the UI polls them forever, because there is no
    worker left to finish them and nothing else ever revisits the row.

    Called once at startup, where the reasoning is airtight: this process has
    just begun, `_running` is empty by definition, so ANY row still claiming to
    be generating belongs to a process that is gone. Sections that never started
    go back to pending; ones that hold content keep it and are marked unrefined,
    since a written page is worth keeping even if its refinement never ran.

    Returns the number of requests it touched, for the startup log.
    """
    db = SessionLocal()
    try:
        stale = (
            db.query(models.WebsiteContentRequest)
            .filter(models.WebsiteContentRequest.status == "generating")
            .all()
        )
        sections = (
            db.query(models.WebsiteSection)
            .filter(models.WebsiteSection.status == "generating")
            .all()
        )
        if not stale and not sections:
            return 0

        for section in sections:
            if (section.content or "").strip():
                section.status = "unrefined"
                section.error_message = (
                    "The run was interrupted before this section finished refining. "
                    "The draft is kept; regenerate it to run the full pass."
                )
            else:
                section.status = "pending"
                section.error_message = "The run was interrupted before this section was written."

        for request in stale:
            written = [s for s in request.sections if (s.content or "").strip()]
            request.status = "partial" if written else "pending"
            request.error_message = (
                "The previous run was interrupted, most likely by the server restarting. "
                "Nothing was lost that had already finished. Run it again to fill in the rest."
            )

        db.commit()
        logger.warning(
            "website_recovered_abandoned requests=%s sections=%s", len(stale), len(sections)
        )
        return len(stale)
    except Exception:
        logger.exception("website_recover_failed")
        db.rollback()
        return 0
    finally:
        db.close()


def is_running(request_id: int) -> bool:
    with _running_lock:
        return request_id in _running


def start_generation(
    db: Session, request: models.WebsiteContentRequest, keys: Optional[List[str]] = None
) -> bool:
    """Starts the run on a background thread. Returns False if already running.

    A daemon thread, deliberately: this is in-process work with no queue behind
    it, so a server restart mid-run abandons it. The rows left on "generating"
    are what makes that visible, and re-running is always safe -- every section
    is rewritten from the brief.
    """
    if not has_anthropic_key():
        raise ServiceNotConfiguredError(_SERVICE, internal="ANTHROPIC_API_KEY is unset")

    with _running_lock:
        if request.id in _running:
            return False
        _running.add(request.id)

    selected = keys or SECTION_ORDER
    request.status = "generating"
    request.error_message = None
    for section in request.sections:
        if section.section_key in selected:
            section.status = "generating"
            section.error_message = None
    db.commit()

    thread = threading.Thread(
        target=_run_in_background,
        args=(request.id, selected),
        name=f"website-content-{request.id}",
        daemon=True,
    )
    thread.start()
    logger.info(
        "website_run_started request_id=%s sections=%s", request.id, ",".join(selected)
    )
    return True


def regenerate_section(
    db: Session, request: models.WebsiteContentRequest, section: models.WebsiteSection
) -> bool:
    """Re-runs ONE section, in the background.

    Backgrounded rather than inline, unlike the blog module's regenerate: one
    section here is a full page-writing call plus up to six refinement calls, and
    the Service Area section routinely writes several thousand words. That does
    not fit in a request the way one blog does.

    The whole intake phase runs again with it. The alternative -- replaying the
    stored brief -- would rebuild it from `meeting_insights`, which is exactly
    what intake produces, so the saving is four calls out of eleven and the cost
    is a second code path that can drift from the real one.
    """
    return start_generation(db, request, keys=[section.section_key])


def export_payload(request: models.WebsiteContentRequest) -> dict:
    """Everything the run produced, in the shape Command HQ already parses.

    This replaces the n8n "Call Zapier" node, which POSTed six fixed fields to a
    webhook. Same `sections[]` array of `{section_title, section_content}` the
    Content Generation API documents, so anything already reading that payload
    reads this one -- but pulled by the caller rather than pushed, and scoped to
    one request.
    """
    return {
        "jobId": str(request.id),
        "status": "completed" if request.status in ("complete", "partial") else request.status,
        "documentName": request.business_name,
        "sections": [
            {"section_title": s.section_title, "section_content": s.content or ""}
            for s in sorted(request.sections or [], key=lambda s: s.position)
            if s.content
        ],
        "note": request.note or "",
    }
