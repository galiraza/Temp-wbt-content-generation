"""The website-content "job": the brief, its six sections, and running them.

One submit runs everything, matching the n8n workflow: the form fed straight
into the agents there, and there is no cheap phase worth committing to first the
way the blog module has one.

  POST /                    save the brief and six empty section rows
  POST /{id}/generate       run it: intake + six sections   (202, background)
  GET  /{id}/sections       poll
  POST /{id}/sections/{sid}/regenerate    re-run one section

Generation is ~40 model calls and several minutes, so it is never held open on a
request. The one exception to "one submit runs everything" is `generate` being
its own call rather than firing from `POST /` -- which lets a brief be saved,
read back and corrected before any money is spent on it.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import (
    get_website_content_request_or_404,
    get_website_section_or_404,
)
from app.services.website_content_service import (
    create_request,
    export_payload,
    is_running,
    regenerate_section,
    request_to_detail,
    request_to_out,
    section_to_detail,
    section_to_out,
    start_generation,
)

router = APIRouter(prefix="/api/website-content", tags=["website-content"])


def _sections_of(db: Session, request_id: int) -> List[schemas.SectionOut]:
    rows = (
        db.query(models.WebsiteSection)
        .filter(models.WebsiteSection.request_id == request_id)
        .order_by(models.WebsiteSection.position)
        .all()
    )
    return [section_to_out(r) for r in rows]


def _reject_if_running(item_id: int, action: str) -> None:
    if is_running(item_id):
        raise HTTPException(
            status_code=409,
            detail=f"This job is generating. Wait for it to finish before {action}.",
        )


@router.get("/industries", response_model=List[str])
def list_industries():
    """The industry options the form offers.

    Served from the backend rather than hardcoded in the frontend for the same
    reason /api/industries is: the list is prompt input, and one copy of it
    avoids the two drifting.
    """
    return schemas.INDUSTRY_OPTIONS


@router.post("", response_model=schemas.WebsiteContentRequestOut, status_code=201)
def create_website_content_request(
    payload: schemas.WebsiteContentRequestCreate,
    db: Session = Depends(get_db),
):
    """Saves the brief and its six empty sections. Generation is a separate call."""
    return request_to_out(create_request(db, payload))


@router.get("", response_model=List[schemas.WebsiteContentRequestOut])
def list_website_content_requests(db: Session = Depends(get_db)):
    rows = (
        db.query(models.WebsiteContentRequest)
        .order_by(models.WebsiteContentRequest.id.desc())
        .all()
    )
    return [request_to_out(r) for r in rows]


@router.get("/{item_id}", response_model=schemas.WebsiteContentRequestDetailOut)
def get_website_content_request(item_id: int, db: Session = Depends(get_db)):
    """The brief plus the meeting analysis and parsed sitemap behind it."""
    return request_to_detail(get_website_content_request_or_404(db, item_id))


@router.put("/{item_id}", response_model=schemas.WebsiteContentRequestOut)
def update_website_content_request(
    item_id: int,
    payload: schemas.WebsiteContentRequestUpdate,
    db: Session = Depends(get_db),
):
    """Edits the brief. The sections are left alone.

    Deliberately non-destructive: fixing a typo in a phone number must not bin a
    finished run. Anything already written stays until it is regenerated, which
    is an explicit action.
    """
    row = get_website_content_request_or_404(db, item_id)
    _reject_if_running(item_id, "editing it")

    import json

    row.business_name = payload.business_name
    row.phone_number = payload.phone_number
    row.email = payload.email
    row.address = payload.address
    row.country = payload.country
    row.state_province_region = payload.state_province_region
    row.zip_postal_code = payload.zip_postal_code
    row.usps = payload.usps
    row.sitemap_text = payload.sitemap_text
    row.industries = json.dumps(payload.industries or [])
    row.other_industries = payload.other_industries
    row.fathom_meeting_1_url = payload.fathom_meeting_1_url
    row.fathom_meeting_2_url = payload.fathom_meeting_2_url
    row.fathom_meeting_3_url = payload.fathom_meeting_3_url
    row.loom_1_summary = payload.loom_1_summary
    row.loom_1_transcript = payload.loom_1_transcript
    row.loom_2_summary = payload.loom_2_summary
    row.loom_2_transcript = payload.loom_2_transcript
    row.loom_3_summary = payload.loom_3_summary
    row.loom_3_transcript = payload.loom_3_transcript

    db.commit()
    db.refresh(row)
    return request_to_out(row)


@router.post("/{item_id}/generate", response_model=schemas.WebsiteContentResult, status_code=202)
def generate_website_content(item_id: int, db: Session = Depends(get_db)):
    """Runs the whole workflow. Returns 202 immediately, runs on a thread.

    Around 40 model calls -- four for intake, then six sections at up to seven
    each -- which no HTTP request should be held open for. Poll GET /{id} and
    GET /{id}/sections for progress.
    """
    row = get_website_content_request_or_404(db, item_id)

    if not start_generation(db, row):
        raise HTTPException(status_code=409, detail="This job is already generating.")

    db.refresh(row)
    return schemas.WebsiteContentResult(
        request=request_to_out(row),
        sections=_sections_of(db, row.id),
        started=True,
    )


@router.get("/{item_id}/sections", response_model=List[schemas.SectionOut])
def list_sections(item_id: int, db: Session = Depends(get_db)):
    get_website_content_request_or_404(db, item_id)
    return _sections_of(db, item_id)


def _section_of_request(db: Session, item_id: int, section_id: int) -> models.WebsiteSection:
    get_website_content_request_or_404(db, item_id)
    section = get_website_section_or_404(db, section_id)
    if section.request_id != item_id:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.get("/{item_id}/sections/{section_id}", response_model=schemas.SectionDetailOut)
def get_section(item_id: int, section_id: int, db: Session = Depends(get_db)):
    """One section with its pre-refinement draft and full critic history. The
    list endpoint omits both -- six sections of those is a very large payload."""
    return section_to_detail(_section_of_request(db, item_id, section_id))


@router.put("/{item_id}/sections/{section_id}", response_model=schemas.SectionOut)
def update_section(
    item_id: int,
    section_id: int,
    payload: schemas.SectionUpdate,
    db: Session = Depends(get_db),
):
    """Manual edit. Leaves the evaluator's verdict alone -- it describes what the
    model wrote, and repointing it at hand-edited text would misreport it."""
    section = _section_of_request(db, item_id, section_id)
    _reject_if_running(item_id, "editing it")
    section.content = payload.content
    db.commit()
    db.refresh(section)
    return section_to_out(section)


@router.post(
    "/{item_id}/sections/{section_id}/regenerate",
    response_model=schemas.WebsiteContentResult,
    status_code=202,
)
def regenerate_one_section(item_id: int, section_id: int, db: Session = Depends(get_db)):
    """Re-runs one section, in the background.

    202 rather than a finished section: one page-writing call plus its
    refinement loop is up to seven model calls, and a Service Area section
    routinely writes several thousand words.
    """
    row = get_website_content_request_or_404(db, item_id)
    section = _section_of_request(db, item_id, section_id)

    if not regenerate_section(db, row, section):
        raise HTTPException(status_code=409, detail="This job is already generating.")

    db.refresh(row)
    return schemas.WebsiteContentResult(
        request=request_to_out(row),
        sections=_sections_of(db, row.id),
        started=True,
    )


@router.get("/{item_id}/export")
def export_website_content(item_id: int, db: Session = Depends(get_db)):
    """Everything the run produced, as JSON.

    Same `sections[]` shape the n8n workflow delivered to its callback, so
    anything already parsing that payload parses this one -- but pulled by the
    caller and scoped to one request, rather than pushed to a fixed webhook.
    """
    return export_payload(get_website_content_request_or_404(db, item_id))


@router.delete("/{item_id}", status_code=204)
def delete_website_content_request(item_id: int, db: Session = Depends(get_db)):
    row = get_website_content_request_or_404(db, item_id)
    _reject_if_running(item_id, "deleting it")
    # Sections and their refinement rounds cascade out with the row. Nothing here
    # has Storage bytes to clean up -- website content has no image assets.
    db.delete(row)
    db.commit()
    return None
