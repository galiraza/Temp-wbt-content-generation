"""The post-generation "job": the brief, its assets, and running generation.

Per-item editing lives in app.routers.posts and app.routers.reviews.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_post_generation_request_or_404
from app.services.post_generation_service import (
    hero_image_to_out,
    post_to_out,
    reel_to_out,
    request_to_out,
    review_to_out,
    run_generation,
    run_image_generation,
)
from app.storage import delete_file, save_upload_bytes

router = APIRouter(prefix="/api/post-generation", tags=["post-generation"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


async def _read_validated_image(file: UploadFile) -> bytes:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WEBP images are allowed")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")
    return content


async def _save_image(file: UploadFile, subdir: str) -> str:
    content = await _read_validated_image(file)
    return save_upload_bytes(content, file.filename or "image.png", subdir)


def _posts_of(db: Session, request_id: int) -> List[schemas.PostOut]:
    rows = (
        db.query(models.Post)
        .filter(models.Post.request_id == request_id)
        .order_by(models.Post.post_number)
        .all()
    )
    return [post_to_out(r) for r in rows]


def _reels_of(db: Session, request_id: int) -> List[schemas.ReelOut]:
    rows = (
        db.query(models.Reel)
        .filter(models.Reel.request_id == request_id)
        .order_by(models.Reel.reel_number)
        .all()
    )
    return [reel_to_out(r) for r in rows]


def _reviews_of(db: Session, request_id: int) -> List[schemas.ReviewOut]:
    rows = (
        db.query(models.Review)
        .filter(models.Review.request_id == request_id)
        .order_by(models.Review.review_number)
        .all()
    )
    return [review_to_out(r) for r in rows]


def _hero_images_of(db: Session, request_id: int) -> List[schemas.HeroImageOut]:
    rows = (
        db.query(models.HeroImage)
        .filter(models.HeroImage.request_id == request_id)
        .order_by(models.HeroImage.slot)
        .all()
    )
    return [hero_image_to_out(r) for r in rows]


@router.post("", response_model=schemas.PostGenerationRequestOut, status_code=201)
async def create_post_generation_request(
    company_name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    website_url: Optional[str] = Form(None),
    company_reviews_page_url: Optional[str] = Form(None),
    month: Optional[str] = Form(None),
    industry: Optional[str] = Form(None),
    fixed_rules: Optional[str] = Form(None),
    main_topic: Optional[str] = Form(None),
    promotion: Optional[str] = Form(None),
    additional_resources: Optional[str] = Form(None),
    additional_notes: Optional[str] = Form(None),
    areas_covered: Optional[str] = Form(None),
    unique_selling_points: Optional[str] = Form(None),
    post_images: List[UploadFile] = File([]),
    logo: Optional[UploadFile] = File(None),
    review_template: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Saves the brief and its assets. Generation is a separate call, so the
    upload isn't held open for the length of two model pipelines."""
    row = models.PostGenerationRequest(
        company_name=company_name,
        phone=phone,
        email=email,
        website_url=website_url,
        company_reviews_page_url=company_reviews_page_url,
        month=month,
        industry=industry,
        fixed_rules=fixed_rules,
        main_topic=main_topic,
        promotion=promotion,
        additional_resources=additional_resources,
        additional_notes=additional_notes,
        areas_covered=areas_covered,
        unique_selling_points=unique_selling_points,
        posts_status="pending",
        reviews_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    subdir = f"post-generation/{row.id}"
    if post_images:
        paths = [await _save_image(f, f"{subdir}/post-images") for f in post_images]
        row.post_image_paths = json.dumps(paths)
    if logo is not None:
        row.logo_path = await _save_image(logo, f"{subdir}/logo")
    if review_template is not None:
        row.review_template_path = await _save_image(
            review_template, f"{subdir}/review-template"
        )

    db.commit()
    db.refresh(row)
    return request_to_out(row)


@router.get("", response_model=List[schemas.PostGenerationRequestOut])
def list_post_generation_requests(db: Session = Depends(get_db)):
    rows = (
        db.query(models.PostGenerationRequest)
        .order_by(models.PostGenerationRequest.id.desc())
        .all()
    )
    return [request_to_out(r) for r in rows]


@router.get("/{item_id}", response_model=schemas.PostGenerationRequestOut)
def get_post_generation_request(item_id: int, db: Session = Depends(get_db)):
    return request_to_out(get_post_generation_request_or_404(db, item_id))


@router.put("/{item_id}", response_model=schemas.PostGenerationRequestOut)
async def update_post_generation_request(
    item_id: int,
    company_name: str = Form(...),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    website_url: Optional[str] = Form(None),
    company_reviews_page_url: Optional[str] = Form(None),
    month: Optional[str] = Form(None),
    industry: Optional[str] = Form(None),
    fixed_rules: Optional[str] = Form(None),
    main_topic: Optional[str] = Form(None),
    promotion: Optional[str] = Form(None),
    additional_resources: Optional[str] = Form(None),
    additional_notes: Optional[str] = Form(None),
    areas_covered: Optional[str] = Form(None),
    unique_selling_points: Optional[str] = Form(None),
    post_images: List[UploadFile] = File([]),
    existing_post_image_paths: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    existing_logo_path: Optional[str] = Form(None),
    review_template: Optional[UploadFile] = File(None),
    existing_review_template_path: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    row = get_post_generation_request_or_404(db, item_id)

    row.company_name = company_name
    row.phone = phone
    row.email = email
    row.website_url = website_url
    row.company_reviews_page_url = company_reviews_page_url
    row.month = month
    row.industry = industry
    row.fixed_rules = fixed_rules
    row.main_topic = main_topic
    row.promotion = promotion
    row.additional_resources = additional_resources
    row.additional_notes = additional_notes
    row.areas_covered = areas_covered
    row.unique_selling_points = unique_selling_points

    subdir = f"post-generation/{row.id}"

    if post_images:
        new_paths = [await _save_image(f, f"{subdir}/post-images") for f in post_images]
        kept_paths = json.loads(existing_post_image_paths) if existing_post_image_paths else []
        row.post_image_paths = json.dumps(kept_paths + new_paths)
    elif existing_post_image_paths is not None:
        row.post_image_paths = json.dumps(json.loads(existing_post_image_paths))

    if logo is not None:
        if row.logo_path:
            delete_file(row.logo_path)
        row.logo_path = await _save_image(logo, f"{subdir}/logo")
    elif existing_logo_path is not None:
        row.logo_path = existing_logo_path or None

    if review_template is not None:
        if row.review_template_path:
            delete_file(row.review_template_path)
        row.review_template_path = await _save_image(
            review_template, f"{subdir}/review-template"
        )
    elif existing_review_template_path is not None:
        row.review_template_path = existing_review_template_path or None

    db.commit()
    db.refresh(row)
    return request_to_out(row)


@router.post("/{item_id}/generate", response_model=schemas.GenerationResult)
def generate_post_generation_content(item_id: int, db: Session = Depends(get_db)):
    """Runs both managers in parallel and returns everything that succeeded.

    A manager that fails does not fail the request: its status column says
    "failed" and error_message says why, so eight good posts are not thrown away
    because a reviews page was unreachable. Re-running replaces both sets.
    """
    row = get_post_generation_request_or_404(db, item_id)
    run_generation(db, row)
    db.refresh(row)
    return schemas.GenerationResult(
        request=request_to_out(row),
        posts=_posts_of(db, row.id),
        reels=_reels_of(db, row.id),
        reviews=_reviews_of(db, row.id),
    )


@router.post("/{item_id}/generate-images", response_model=schemas.ImageGenerationResult)
def generate_post_generation_images(item_id: int, db: Session = Depends(get_db)):
    """Generates a fresh pool of 12 hero images and matches one to every
    existing post and reel. Best run after /generate, since the hero-image
    prompts use the generated post titles as creative anchors - but does not
    require it: with no posts yet, hero images still generate, they simply
    have nothing to be matched to until content exists.

    Re-running replaces the whole pool and every match, same convention as
    /generate replacing posts/reels.
    """
    row = get_post_generation_request_or_404(db, item_id)
    run_image_generation(db, row)
    db.refresh(row)
    return schemas.ImageGenerationResult(
        request=request_to_out(row),
        hero_images=_hero_images_of(db, row.id),
        posts=_posts_of(db, row.id),
        reels=_reels_of(db, row.id),
    )


@router.get("/{item_id}/hero-images", response_model=List[schemas.HeroImageOut])
def list_hero_images(item_id: int, db: Session = Depends(get_db)):
    get_post_generation_request_or_404(db, item_id)
    return _hero_images_of(db, item_id)


@router.get("/{item_id}/posts", response_model=List[schemas.PostOut])
def list_posts(item_id: int, db: Session = Depends(get_db)):
    get_post_generation_request_or_404(db, item_id)
    return _posts_of(db, item_id)


@router.get("/{item_id}/reels", response_model=List[schemas.ReelOut])
def list_reels(item_id: int, db: Session = Depends(get_db)):
    get_post_generation_request_or_404(db, item_id)
    return _reels_of(db, item_id)


@router.get("/{item_id}/reviews", response_model=List[schemas.ReviewOut])
def list_reviews(item_id: int, db: Session = Depends(get_db)):
    get_post_generation_request_or_404(db, item_id)
    return _reviews_of(db, item_id)


@router.delete("/{item_id}", status_code=204)
def delete_post_generation_request(item_id: int, db: Session = Depends(get_db)):
    row = get_post_generation_request_or_404(db, item_id)

    # Generated images cascade out of the database with the rows, but their bytes
    # live in Storage and have to be removed explicitly.
    for image in (
        db.query(models.PostImage)
        .outerjoin(models.Post, models.PostImage.post_id == models.Post.id)
        .outerjoin(models.Review, models.PostImage.review_id == models.Review.id)
        .filter(
            (models.Post.request_id == item_id) | (models.Review.request_id == item_id)
        )
        .all()
    ):
        delete_file(image.file_path)

    for image in (
        db.query(models.ReelImage)
        .join(models.Reel, models.ReelImage.reel_id == models.Reel.id)
        .filter(models.Reel.request_id == item_id)
        .all()
    ):
        delete_file(image.file_path)

    for hero_image in row.hero_images:
        delete_file(hero_image.file_path)

    for path in json.loads(row.post_image_paths) if row.post_image_paths else []:
        delete_file(path)
    if row.logo_path:
        delete_file(row.logo_path)
    if row.review_template_path:
        delete_file(row.review_template_path)

    db.delete(row)
    db.commit()
    return None
