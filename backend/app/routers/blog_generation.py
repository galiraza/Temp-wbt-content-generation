"""The blog-generation "job": the cluster brief, its blogs, and running them.

Two phases, two endpoints, on purpose:

  POST /{id}/extract-metadata   scrape + structure + parse the plan  (~3 calls)
  POST /{id}/generate           write, QC and revise every blog      (~84 calls)

The cheap one is committed to first so a mis-pasted Blog Schema is caught before
paying for the expensive one. The n8n workflow ran straight through, so one bad
paste wasted the whole run.
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import (
    get_blog_generation_request_or_404,
    get_blog_or_404,
)
from app.services.blog_generation_service import (
    blog_to_detail,
    blog_to_out,
    is_running,
    regenerate_one,
    request_to_out,
    run_metadata_extraction,
    start_generation,
)

router = APIRouter(prefix="/api/blog-generation", tags=["blog-generation"])


def _blogs_of(db: Session, request_id: int) -> List[schemas.BlogOut]:
    rows = (
        db.query(models.Blog)
        .filter(models.Blog.request_id == request_id)
        .order_by(models.Blog.blog_number)
        .all()
    )
    return [blog_to_out(r) for r in rows]


@router.post("", response_model=schemas.BlogGenerationRequestOut, status_code=201)
def create_blog_generation_request(
    payload: schemas.BlogGenerationRequestCreate,
    db: Session = Depends(get_db),
):
    """Saves the brief only. Both generation phases are separate calls, so
    submitting the form returns immediately."""
    row = models.BlogGenerationRequest(
        client_name=payload.client_name,
        website_url=payload.website_url,
        cluster_theme_1=payload.cluster_theme_1,
        cluster_theme_2=payload.cluster_theme_2,
        cluster_theme_3=payload.cluster_theme_3,
        cluster_number=payload.cluster_number,
        blog_schema_raw=payload.blog_schema_raw,
        metadata_status="pending",
        content_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return request_to_out(row)


@router.get("", response_model=List[schemas.BlogGenerationRequestOut])
def list_blog_generation_requests(db: Session = Depends(get_db)):
    rows = (
        db.query(models.BlogGenerationRequest)
        .order_by(models.BlogGenerationRequest.id.desc())
        .all()
    )
    return [request_to_out(r) for r in rows]


@router.get("/{item_id}", response_model=schemas.BlogGenerationRequestOut)
def get_blog_generation_request(item_id: int, db: Session = Depends(get_db)):
    return request_to_out(get_blog_generation_request_or_404(db, item_id))


@router.put("/{item_id}", response_model=schemas.BlogGenerationRequestOut)
def update_blog_generation_request(
    item_id: int,
    payload: schemas.BlogGenerationRequestUpdate,
    db: Session = Depends(get_db),
):
    row = get_blog_generation_request_or_404(db, item_id)
    if is_running(item_id):
        raise HTTPException(
            status_code=409,
            detail="This job is generating. Wait for it to finish before editing it.",
        )

    plan_changed = row.blog_schema_raw != payload.blog_schema_raw
    site_changed = row.website_url != payload.website_url

    row.client_name = payload.client_name
    row.website_url = payload.website_url
    row.cluster_theme_1 = payload.cluster_theme_1
    row.cluster_theme_2 = payload.cluster_theme_2
    row.cluster_theme_3 = payload.cluster_theme_3
    row.cluster_number = payload.cluster_number
    row.blog_schema_raw = payload.blog_schema_raw

    # The blogs were derived from the plan and the site. Editing either makes the
    # existing briefs stale, so the extraction has to be re-run — but the rows are
    # left alone rather than deleted, so a typo fix does not silently bin a
    # finished cluster.
    if plan_changed or site_changed:
        row.metadata_status = "pending"
        row.error_message = (
            "The plan or website changed. Re-extract the content plan to refresh the blogs."
        )

    db.commit()
    db.refresh(row)
    return request_to_out(row)


@router.post("/{item_id}/extract-metadata", response_model=schemas.MetadataResult)
def extract_blog_metadata(item_id: int, db: Session = Depends(get_db)):
    """Phase 1. Blocking, but short: one scrape and two model calls.

    Replaces any existing blogs for this job, so the briefs always match the plan
    that is currently saved.
    """
    row = get_blog_generation_request_or_404(db, item_id)
    if is_running(item_id):
        raise HTTPException(
            status_code=409,
            detail="This job is generating. Wait for it to finish before re-extracting.",
        )
    run_metadata_extraction(db, row)
    db.refresh(row)
    return schemas.MetadataResult(
        request=request_to_out(row),
        blogs=_blogs_of(db, row.id),
    )


@router.post("/{item_id}/generate", response_model=schemas.BlogGenerationResult, status_code=202)
def generate_blog_content(item_id: int, db: Session = Depends(get_db)):
    """Phase 2. Returns 202 immediately and runs on a background thread.

    Up to ~84 model calls for a 12-blog cluster, which no HTTP request should be
    held open for. Poll GET /{id} and GET /{id}/blogs for progress.
    """
    row = get_blog_generation_request_or_404(db, item_id)

    if not row.blogs:
        raise HTTPException(
            status_code=400,
            detail="No blogs to write yet. Extract the content plan first.",
        )
    if row.metadata_status != "complete":
        raise HTTPException(
            status_code=400,
            detail="Extract the content plan first.",
        )

    started = start_generation(db, row)
    if not started:
        raise HTTPException(
            status_code=409, detail="This job is already generating."
        )

    db.refresh(row)
    return schemas.BlogGenerationResult(
        request=request_to_out(row),
        blogs=_blogs_of(db, row.id),
        started=True,
    )


@router.get("/{item_id}/blogs", response_model=List[schemas.BlogOut])
def list_blogs(item_id: int, db: Session = Depends(get_db)):
    get_blog_generation_request_or_404(db, item_id)
    return _blogs_of(db, item_id)


@router.get("/{item_id}/blogs/{blog_id}", response_model=schemas.BlogDetailOut)
def get_blog(item_id: int, blog_id: int, db: Session = Depends(get_db)):
    """One blog with its full QC history. The list endpoint omits the rounds."""
    get_blog_generation_request_or_404(db, item_id)
    blog = get_blog_or_404(db, blog_id)
    if blog.request_id != item_id:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog_to_detail(blog)


@router.put("/{item_id}/blogs/{blog_id}", response_model=schemas.BlogOut)
def update_blog(
    item_id: int,
    blog_id: int,
    payload: schemas.BlogUpdate,
    db: Session = Depends(get_db),
):
    """Manual edit. Leaves the QC verdict alone — it describes what the model
    wrote, and repointing it at hand-edited text would misreport the audit."""
    get_blog_generation_request_or_404(db, item_id)
    blog = get_blog_or_404(db, blog_id)
    if blog.request_id != item_id:
        raise HTTPException(status_code=404, detail="Blog not found")

    blog.content = payload.content
    blog.gmb_post = payload.gmb_post
    blog.gmb_faq = payload.gmb_faq
    blog.meta_title = payload.meta_title
    blog.meta_description = payload.meta_description
    db.commit()
    db.refresh(blog)
    return blog_to_out(blog)


@router.post("/{item_id}/blogs/{blog_id}/regenerate", response_model=schemas.BlogOut)
def regenerate_blog(item_id: int, blog_id: int, db: Session = Depends(get_db)):
    """Re-runs one blog's whole write-QC-revise loop. Slow, but inline: one blog
    is up to eight calls, which fits in a request."""
    row = get_blog_generation_request_or_404(db, item_id)
    if is_running(item_id):
        raise HTTPException(
            status_code=409,
            detail="This job is generating. Wait for it to finish first.",
        )
    blog = get_blog_or_404(db, blog_id)
    if blog.request_id != item_id:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog_to_out(regenerate_one(db, row, blog))


@router.get("/{item_id}/export")
def export_blogs(item_id: int, db: Session = Depends(get_db)):
    """Everything the cluster produced, as JSON.

    This replaces the n8n "Call Zapier" node, which POSTed 12 numbered
    blog_N_content fields to a webhook after reading the WHOLE data table with no
    client filter — so an export could ship another client's blogs. Scoped to one
    request here, and pulled by the caller rather than pushed.
    """
    row = get_blog_generation_request_or_404(db, item_id)
    rows = (
        db.query(models.Blog)
        .filter(models.Blog.request_id == item_id)
        .order_by(models.Blog.blog_number)
        .all()
    )
    return {
        "client_name": row.client_name,
        "website_url": row.website_url,
        "cluster_themes": [
            t for t in (row.cluster_theme_1, row.cluster_theme_2, row.cluster_theme_3) if t
        ],
        "blog_count": len(rows),
        "blogs": [
            {
                "blog_number": b.blog_number,
                "title": b.title,
                "funnel_stage": b.funnel_stage,
                "service_areas": b.service_area_list,
                "keywords": b.keyword_list,
                "meta_title": b.meta_title,
                "meta_description": b.meta_description,
                "content": b.content,
                "gmb_post": b.gmb_post,
                "gmb_faq": b.gmb_faq,
                "qc_score": b.qc_score,
                "qc_result": b.qc_result,
                "status": b.status,
            }
            for b in rows
        ],
    }


@router.delete("/{item_id}", status_code=204)
def delete_blog_generation_request(item_id: int, db: Session = Depends(get_db)):
    row = get_blog_generation_request_or_404(db, item_id)
    if is_running(item_id):
        raise HTTPException(
            status_code=409,
            detail="This job is generating. Wait for it to finish before deleting it.",
        )
    # Blogs and their QC rounds cascade out with the row. Nothing here has
    # Storage bytes to clean up — a blog cluster has no image assets.
    db.delete(row)
    db.commit()
    return None
