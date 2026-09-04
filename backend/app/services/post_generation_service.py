"""Business logic for post generation: row mapping, the stub path, and the writes.

The orchestration itself lives in app.agents.post_generation.pipeline — read that
file to see how the two managers run. This module owns every database write, which
is what lets the pipeline run them on separate threads without sharing a Session
(SQLAlchemy Sessions are not thread-safe).

The request row carries two status columns because the managers fail
independently: a dead reviews page should not throw away eight good posts, nor
force them to be regenerated.
"""

import json
import logging
from contextlib import ExitStack
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.agents.post_generation.content_matching_agent import match_hero_image
from app.agents.post_generation.final_image_agent import generate_final_image
from app.agents.post_generation.hero_image_agent import generate_hero_images
from app.agents.post_generation.image_editor_agent import revise_post_or_reel_image
from app.agents.post_generation.parsers import parse_hashtag_pool
from app.agents.post_generation.pipeline import run_managers
from app.agents.post_generation.post_manager import (
    NUM_POSTS,
    NUM_REELS,
    regenerate_post,
    regenerate_reel,
)
from app.agents.post_generation.review_manager import NUM_REVIEWS, regenerate_review
from app.config import has_anthropic_key, has_openai_key
from app.storage import delete_file, download_to_temp_file, save_base64_image
from app.errors import AlreadyInProgressError, ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")



# --- row to schema -----------------------------------------------------------


def _newest_image(row) -> Tuple[Optional[str], int]:
    """The current image is the newest version; the count drives the version
    strip in the image chat."""
    images = list(row.images or [])
    if not images:
        return None, 0
    return images[-1].file_path, len(images)


def post_to_out(row: models.Post) -> schemas.PostOut:
    image_path, image_count = _newest_image(row)
    return schemas.PostOut(
        id=row.id,
        request_id=row.request_id,
        post_number=row.post_number,
        theme=row.theme,
        title=row.title,
        caption=row.caption,
        hashtags=row.hashtag_list,
        status=row.status,
        image_path=image_path,
        image_count=image_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def reel_to_out(row: models.Reel) -> schemas.ReelOut:
    image_path, image_count = _newest_image(row)
    return schemas.ReelOut(
        id=row.id,
        request_id=row.request_id,
        reel_number=row.reel_number,
        theme=row.theme,
        reel_text=row.reel_text,
        caption=row.caption,
        hashtags=row.hashtag_list,
        status=row.status,
        image_path=image_path,
        image_count=image_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def hero_image_to_out(row: models.HeroImage) -> schemas.HeroImageOut:
    return schemas.HeroImageOut.model_validate(row)


def post_image_to_out(row: models.PostImage) -> schemas.PostImageOut:
    return schemas.PostImageOut.model_validate(row)


def reel_image_to_out(row: models.ReelImage) -> schemas.ReelImageOut:
    return schemas.ReelImageOut.model_validate(row)


def _image_message_to_out(row, schema_cls, id_field: str):
    candidate_image_path = None
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
            candidate_image_path = parsed.get("file_path")
        except (json.JSONDecodeError, AttributeError):
            pass
    return schema_cls(
        id=row.id,
        role=row.role,
        content=row.content,
        candidate_image_path=candidate_image_path,
        attachment_path=row.attachment_path,
        created_at=row.created_at,
        **{id_field: getattr(row, id_field)},
    )


def post_image_message_to_out(row: models.PostImageChatMessage) -> schemas.PostImageChatMessageOut:
    return _image_message_to_out(row, schemas.PostImageChatMessageOut, "post_image_id")


def reel_image_message_to_out(row: models.ReelImageChatMessage) -> schemas.ReelImageChatMessageOut:
    return _image_message_to_out(row, schemas.ReelImageChatMessageOut, "reel_image_id")


def review_to_out(row: models.Review) -> schemas.ReviewOut:
    image_path, image_count = _newest_image(row)
    return schemas.ReviewOut(
        id=row.id,
        request_id=row.request_id,
        review_number=row.review_number,
        title=row.title,
        name=row.name,
        review=row.review,
        caption=row.caption,
        hashtags=row.hashtag_list,
        platform=row.platform,
        status=row.status,
        image_path=image_path,
        image_count=image_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def request_to_out(row: models.PostGenerationRequest) -> schemas.PostGenerationRequestOut:
    return schemas.PostGenerationRequestOut(
        id=row.id,
        company_name=row.company_name,
        phone=row.phone,
        email=row.email,
        website_url=row.website_url,
        company_reviews_page_url=row.company_reviews_page_url,
        month=row.month,
        industry=row.industry,
        fixed_rules=row.fixed_rules,
        main_topic=row.main_topic,
        promotion=row.promotion,
        additional_resources=row.additional_resources,
        additional_notes=row.additional_notes,
        areas_covered=row.areas_covered,
        unique_selling_points=row.unique_selling_points,
        post_image_paths=json.loads(row.post_image_paths) if row.post_image_paths else [],
        logo_path=row.logo_path,
        review_template_path=row.review_template_path,
        posts_status=row.posts_status,
        reviews_status=row.reviews_status,
        images_status=row.images_status,
        error_message=row.error_message,
        post_hashtag_pool=parse_hashtag_pool(row.post_hashtag_pool or ""),
        review_hashtag_pool=parse_hashtag_pool(row.review_hashtag_pool or ""),
        has_scraped_reviews=bool(row.scraped_reviews_markdown),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def message_to_out(row: models.PostChatMessage) -> schemas.ContentChatMessageOut:
    """An assistant turn is either a JSON partial revision or plain prose.

    The JSON form carries a `reply` to render in the thread plus only the fields
    that turn changes, so the UI can show "caption only" rather than implying the
    whole item was rewritten.
    """
    fields: Dict = {}
    display = row.content
    is_revision = False
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            display = parsed.get("reply") or row.content
            changes = parsed.get("changes") or {}
            if isinstance(changes, dict):
                fields = changes
                is_revision = bool(changes)

    return schemas.ContentChatMessageOut(
        id=row.id,
        post_id=row.post_id,
        review_id=row.review_id,
        role=row.role,
        content=display,
        is_revision=is_revision,
        title=fields.get("title"),
        name=fields.get("name"),
        review=fields.get("review"),
        caption=fields.get("caption"),
        hashtags=fields.get("hashtags"),
        created_at=row.created_at,
    )


def reel_message_to_out(row: models.ReelChatMessage) -> schemas.ReelChatMessageOut:
    """Same JSON-or-prose split as message_to_out, on the reel's own chat table."""
    fields: Dict = {}
    display = row.content
    is_revision = False
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            display = parsed.get("reply") or row.content
            changes = parsed.get("changes") or {}
            if isinstance(changes, dict):
                fields = changes
                is_revision = bool(changes)

    return schemas.ReelChatMessageOut(
        id=row.id,
        reel_id=row.reel_id,
        role=row.role,
        content=display,
        is_revision=is_revision,
        reel_text=fields.get("reel_text"),
        caption=fields.get("caption"),
        hashtags=fields.get("hashtags"),
        created_at=row.created_at,
    )


# --- stubs -------------------------------------------------------------------


def _stub_posts(company_name: str) -> Tuple[List[Dict], str]:
    """No ANTHROPIC_API_KEY: return obvious placeholders instantly rather than
    failing, so the forms and the jobs grid stay usable without live API cost.
    Same convention as the ad-angle stub path."""
    posts = [
        {
            "post_number": slot,
            "theme": models.POST_SLOT_THEMES[slot],
            "title": f"{company_name} post {slot} ({models.POST_SLOT_THEMES[slot]})",
            "caption": (
                f"[Stub post {slot}] Placeholder copy for {company_name}. "
                "Set ANTHROPIC_API_KEY to enable real generation."
            ),
            "hashtags": ["#Stub", "#SetAnthropicKey"],
        }
        for slot in models.POST_SLOTS
    ]
    return posts, ""


def _stub_reels(company_name: str) -> List[Dict]:
    return [
        {
            "reel_number": slot,
            "theme": models.REEL_SLOT_THEMES[slot],
            "reel_text": f"[Stub reel {slot}] On-screen script for {company_name}.",
            "caption": (
                f"[Stub reel {slot}] Placeholder caption. "
                "Set ANTHROPIC_API_KEY to enable real generation."
            ),
            "hashtags": ["#Stub", "#SetAnthropicKey"],
        }
        for slot in models.REEL_SLOTS
    ]


def _stub_reviews(company_name: str) -> Tuple[List[Dict], str, str]:
    reviews = [
        {
            "review_number": i + 1,
            "title": f"Stub review {i + 1}",
            "name": f"Customer {i + 1}",
            "review": (
                f"[Stub review {i + 1}] Placeholder review text for {company_name}. "
                "Set ANTHROPIC_API_KEY and FIRECRAWL_API_KEY to enable real generation."
            ),
            "caption": f"[Stub caption {i + 1}] Placeholder response for {company_name}.",
            "hashtags": ["#Stub", "#SetAnthropicKey"],
            "platform": "Stub",
        }
        for i in range(NUM_REVIEWS)
    ]
    return reviews, "", ""


# --- writes ------------------------------------------------------------------


def _delete_rows(db: Session, rows: List) -> None:
    """Deletes item rows one at a time, on purpose.

    A bulk `query(...).delete()` does NOT fire the ORM cascades, and the foreign
    keys are all NO ACTION, so re-running generation on a job whose items had chat
    messages raised a ForeignKeyViolation. Deleting through the ORM lets
    cascade="all, delete-orphan" take the chat messages and images with each row.

    Image bytes live in Supabase Storage rather than the database, so they have to
    be removed explicitly or they are orphaned there forever.
    """
    for row in rows:
        for image in list(row.images or []):
            delete_file(image.file_path)
        db.delete(row)
    db.flush()


def _replace_posts(db: Session, request_id: int, posts: List[Dict]) -> None:
    _delete_rows(db, db.query(models.Post).filter(models.Post.request_id == request_id).all())
    for data in posts:
        db.add(
            models.Post(
                request_id=request_id,
                post_number=data["post_number"],
                theme=data["theme"],
                title=data["title"],
                caption=data["caption"],
                hashtags=json.dumps(data["hashtags"]),
            )
        )


def _replace_reels(db: Session, request_id: int, reels: List[Dict]) -> None:
    _delete_rows(db, db.query(models.Reel).filter(models.Reel.request_id == request_id).all())
    for data in reels:
        db.add(
            models.Reel(
                request_id=request_id,
                reel_number=data["reel_number"],
                theme=data["theme"],
                reel_text=data["reel_text"],
                caption=data["caption"],
                hashtags=json.dumps(data["hashtags"]),
            )
        )


def _replace_reviews(db: Session, request_id: int, reviews: List[Dict]) -> None:
    _delete_rows(db, db.query(models.Review).filter(models.Review.request_id == request_id).all())
    for data in reviews:
        db.add(
            models.Review(
                request_id=request_id,
                review_number=data["review_number"],
                title=data["title"],
                name=data["name"],
                review=data["review"],
                caption=data["caption"],
                hashtags=json.dumps(data["hashtags"]),
                platform=data.get("platform"),
            )
        )


def run_generation(db: Session, request: models.PostGenerationRequest) -> None:
    """Generates both sets and writes whatever succeeded.

    Returns normally even when one manager failed: the failure is recorded on that
    manager's status column and in error_message. Only a total failure raises,
    because then there is nothing to show and the caller deserves an error rather
    than an empty grid.
    """
    if not has_anthropic_key():
        posts, _ = _stub_posts(request.company_name)
        reviews, _, _ = _stub_reviews(request.company_name)
        _replace_posts(db, request.id, posts)
        _replace_reels(db, request.id, _stub_reels(request.company_name))
        _replace_reviews(db, request.id, reviews)
        request.posts_status = "complete"
        request.reviews_status = "complete"
        request.error_message = "Stub content: ANTHROPIC_API_KEY is not configured."
        db.commit()
        return

    request.posts_status = "generating"
    request.reviews_status = "generating"
    request.error_message = None
    db.commit()

    # Both managers, in parallel. See pipeline.py for the flow.
    outcome = run_managers(request)

    if outcome.posts.ok:
        _replace_posts(db, request.id, outcome.posts.items)
        # Reels came from the same call, so they live or die with the posts.
        _replace_reels(db, request.id, outcome.reels)
        request.posts_status = "complete"
        if outcome.posts.hashtag_pool:
            request.post_hashtag_pool = outcome.posts.hashtag_pool
    else:
        request.posts_status = "failed"

    if outcome.reviews.ok:
        _replace_reviews(db, request.id, outcome.reviews.items)
        request.reviews_status = "complete"
        if outcome.reviews.hashtag_pool:
            request.review_hashtag_pool = outcome.reviews.hashtag_pool
        if outcome.scraped_markdown:
            request.scraped_reviews_markdown = outcome.scraped_markdown
    else:
        request.reviews_status = "failed"

    request.error_message = outcome.error_message
    db.commit()

    if outcome.total_failure:
        raise UpstreamServiceError(
            "Post generation",
            outcome.error_message or "Generation failed. Please try again.",
            internal=f"both managers failed for request {request.id}",
        )


def _message_of(exc: Exception) -> str:
    return str(getattr(exc, "message", None) or exc)


def _delete_hero_images(db: Session, request_id: int) -> None:
    rows = (
        db.query(models.HeroImage).filter(models.HeroImage.request_id == request_id).all()
    )
    for row in rows:
        delete_file(row.file_path)
        db.delete(row)
    db.flush()


_STALE_GENERATING_MINUTES = 20  # generation normally finishes in well under this;
# past it, a "generating" row is almost certainly one the server crashed or was
# restarted mid-request, not one genuinely still running - block real overlap,
# not a deploy that happened to land badly.


def run_image_generation(db: Session, request: models.PostGenerationRequest) -> None:
    """Generates a fresh pool of 12 hero images, then matches one to every
    existing post and reel.

    Re-running replaces the old pool (and every post/reel's match) rather
    than adding to it, same convention _replace_posts/_replace_reels use for
    content - a stale photo from a previous attempt should not linger once
    a new set has been generated.

    Raises on total failure (nothing to show), same as run_generation's
    total_failure case - but the row's images_status/error_message are set
    first, so the failure is visible even though the request also raises.

    Also raises if this request is already mid-generation: two overlapping
    runs both delete-and-replace the same 12 rows, so the one that finishes
    first is immediately thrown away - purely wasted paid image generation,
    not just a harmless race. Seen in practice: a client-side timeout on a
    genuinely-still-running request reads as failure, the obvious next move
    is to retry, and that retry now races the original.
    """
    if request.images_status == "generating" and request.updated_at > datetime.utcnow() - timedelta(
        minutes=_STALE_GENERATING_MINUTES
    ):
        raise AlreadyInProgressError(
            "Hero image generation",
            internal=f"request_id={request.id} already generating since {request.updated_at}",
        )

    request.images_status = "generating"
    request.error_message = None
    db.commit()

    try:
        results = generate_hero_images(request)
    except Exception as exc:
        request.images_status = "failed"
        request.error_message = _message_of(exc)
        db.commit()
        raise

    _delete_hero_images(db, request.id)
    subdir = f"post-generation/{request.id}/hero-images"
    hero_images: List[models.HeroImage] = []
    for item in results:
        file_path = save_base64_image(item["b64"], subdir)
        row = models.HeroImage(
            request_id=request.id,
            slot=item["slot"],
            file_path=file_path,
            summary=item["summary"],
        )
        db.add(row)
        hero_images.append(row)
    db.flush()  # assigns ids, and lets the FK SET NULL from the delete above land first

    posts = (
        db.query(models.Post)
        .filter(models.Post.request_id == request.id)
        .order_by(models.Post.post_number)
        .all()
    )
    reels = (
        db.query(models.Reel)
        .filter(models.Reel.request_id == request.id)
        .order_by(models.Reel.reel_number)
        .all()
    )

    for post in posts:
        matched = match_hero_image(hero_images, post.title, post.caption)
        if matched:
            post.hero_image_id = matched.id
            matched.usage += 1

    for reel in reels:
        reel_title = (reel.reel_text or "").splitlines()[0] if reel.reel_text else reel.caption[:80]
        matched = match_hero_image(hero_images, reel_title, reel.caption)
        if matched:
            reel.hero_image_id = matched.id
            matched.usage += 1

    request.images_status = "complete"
    db.commit()


def _reel_title(reel: models.Reel) -> str:
    """Reels have no title field - the first on-screen line stands in for
    one, same proxy used for content-matching in run_image_generation."""
    return (reel.reel_text or "").splitlines()[0] if reel.reel_text else reel.caption[:80]


def generate_image_for_post(post: models.Post, variant_rows: List[models.VariantLibrary]) -> bytes:
    """Returns finished PNG bytes (1080x1350) for a newly composited branded
    image: the client's logo, this post's matched hero photo, and a
    randomly-picked layout variant from variant_rows.
    """
    request = post.request
    if not request.logo_path:
        raise HTTPException(status_code=400, detail="Upload a company logo before generating an image.")
    if post.hero_image is None:
        raise HTTPException(
            status_code=400,
            detail="Generate this month's hero images first (Generate Images), then try again.",
        )

    try:
        with ExitStack() as stack:
            logo_local = stack.enter_context(download_to_temp_file(request.logo_path))
            hero_local = stack.enter_context(download_to_temp_file(post.hero_image.file_path))
            return generate_final_image(
                logo_path=logo_local,
                hero_photo_path=hero_local,
                title=post.title,
                industry=request.industry,
                website_url=request.website_url,
                variant_rows=variant_rows,
            )
    except (UpstreamServiceError, ServiceNotConfiguredError, HTTPException):
        raise
    except Exception as exc:
        raise UpstreamServiceError(
            "Final image generation", "Couldn't generate the image. Please try again.", internal=str(exc)
        ) from exc


def generate_image_for_reel(reel: models.Reel, variant_rows: List[models.VariantLibrary]) -> bytes:
    """Same as generate_image_for_post, for a reel - uses the first
    on-screen line as the title proxy (reels have no title field)."""
    request = reel.request
    if not request.logo_path:
        raise HTTPException(status_code=400, detail="Upload a company logo before generating an image.")
    if reel.hero_image is None:
        raise HTTPException(
            status_code=400,
            detail="Generate this month's hero images first (Generate Images), then try again.",
        )

    try:
        with ExitStack() as stack:
            logo_local = stack.enter_context(download_to_temp_file(request.logo_path))
            hero_local = stack.enter_context(download_to_temp_file(reel.hero_image.file_path))
            return generate_final_image(
                logo_path=logo_local,
                hero_photo_path=hero_local,
                title=_reel_title(reel),
                industry=request.industry,
                website_url=request.website_url,
                variant_rows=variant_rows,
            )
    except (UpstreamServiceError, ServiceNotConfiguredError, HTTPException):
        raise
    except Exception as exc:
        raise UpstreamServiceError(
            "Final image generation", "Couldn't generate the image. Please try again.", internal=str(exc)
        ) from exc


def revise_post_or_reel_image_row(
    image, chat_history: List[dict], attachment_path: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Revision is identical for a PostImage or a ReelImage row - both are
    just "the current file plus a chat history" to the editor agent. Returns
    a (b64_json, off_topic_reply) tuple, same contract as revise_image() for
    ad-angle/logo images."""
    if not has_openai_key():
        raise ServiceNotConfiguredError("Image generation", internal="OPENAI_API_KEY is unset")

    try:
        with ExitStack() as stack:
            current_image_path = stack.enter_context(download_to_temp_file(image.file_path))
            attachment_local_path = (
                stack.enter_context(download_to_temp_file(attachment_path))
                if attachment_path
                else None
            )
            return revise_post_or_reel_image(
                current_image_path=current_image_path,
                chat_history=chat_history,
                attachment_path=attachment_local_path,
            )
    except Exception as exc:
        raise UpstreamServiceError(
            "Image revision", "Couldn't revise the image. Please try again.", internal=str(exc)
        ) from exc


def regenerate_one_post(request: models.PostGenerationRequest, post: models.Post) -> Dict:
    if not has_anthropic_key():
        return {
            "title": post.title,
            "caption": f"[Stub regenerated] {post.caption}",
            "hashtags": post.hashtag_list,
        }
    return regenerate_post(request, post, request.post_hashtag_pool or "")


def regenerate_one_review(request: models.PostGenerationRequest, review: models.Review) -> Dict:
    if not has_anthropic_key():
        return {
            "title": review.title,
            "name": review.name,
            "review": review.review,
            "caption": f"[Stub regenerated] {review.caption}",
            "hashtags": review.hashtag_list,
        }
    return regenerate_review(request, review, request.review_hashtag_pool or "")


def regenerate_one_reel(request: models.PostGenerationRequest, reel: models.Reel) -> Dict:
    if not has_anthropic_key():
        return {
            "reel_text": reel.reel_text,
            "caption": f"[Stub regenerated] {reel.caption}",
            "hashtags": reel.hashtag_list,
        }
    return regenerate_reel(request, reel, request.post_hashtag_pool or "")
