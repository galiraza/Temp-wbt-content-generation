"""A single generated review post's lifecycle and its copy chat board.

Mirrors app.routers.posts, with one extra field on the table (`name`) and one
extra guarantee: `review` holds the customer's own words. The chat agent refuses
to rewrite it, and a manual edit is the only way it changes at all — which is
what you want for fixing a mis-transcribed name, and nothing else.
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_post_generation_request_or_404, get_review_or_404
from app.services.post_generation_service import (
    message_to_out,
    regenerate_one_review,
    review_to_out,
)
from app.agents.post_generation.feedback_agent import request_revision

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

_EDITABLE = ("title", "name", "review", "caption", "hashtags")


@router.get("/{review_id}", response_model=schemas.ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    return review_to_out(get_review_or_404(db, review_id))


@router.put("/{review_id}", response_model=schemas.ReviewOut)
def update_review(
    review_id: int, payload: schemas.ReviewUpdate, db: Session = Depends(get_db)
):
    """Direct user-typed edit. No LLM, no approval step."""
    review = get_review_or_404(db, review_id)
    review.title = payload.title
    review.name = payload.name
    review.review = payload.review
    review.caption = payload.caption
    review.hashtags = json.dumps(payload.hashtags)
    db.commit()
    db.refresh(review)
    return review_to_out(review)


@router.post("/{review_id}/approve", response_model=schemas.ReviewOut)
def approve_review(review_id: int, db: Session = Depends(get_db)):
    review = get_review_or_404(db, review_id)
    review.status = "approved"
    db.commit()
    db.refresh(review)
    return review_to_out(review)


@router.post("/{review_id}/unapprove", response_model=schemas.ReviewOut)
def unapprove_review(review_id: int, db: Session = Depends(get_db)):
    review = get_review_or_404(db, review_id)
    review.status = "pending"
    db.commit()
    db.refresh(review)
    return review_to_out(review)


@router.post("/{review_id}/regenerate", response_model=schemas.ReviewOut)
def regenerate_review_route(review_id: int, db: Session = Depends(get_db)):
    """Rewrites this review post's headline and caption. The customer's quote and
    attribution are passed back in unchanged, and the hashtags are left as they
    are."""
    review = get_review_or_404(db, review_id)
    request = get_post_generation_request_or_404(db, review.request_id)

    generated = regenerate_one_review(request, review)
    review.title = generated["title"]
    review.caption = generated["caption"]
    # Hashtags are deliberately NOT touched: regenerate rewrites the copy only.
    review.status = "pending"
    db.commit()
    db.refresh(review)
    return review_to_out(review)


def _history(db: Session, review_id: int) -> List[models.PostChatMessage]:
    return (
        db.query(models.PostChatMessage)
        .filter(models.PostChatMessage.review_id == review_id)
        .order_by(models.PostChatMessage.created_at)
        .all()
    )


@router.get("/{review_id}/messages", response_model=List[schemas.ContentChatMessageOut])
def list_review_messages(review_id: int, db: Session = Depends(get_db)):
    get_review_or_404(db, review_id)
    return [message_to_out(m) for m in _history(db, review_id)]


@router.post("/{review_id}/messages", response_model=schemas.ReviewFeedbackResponse)
def send_review_feedback(
    review_id: int,
    payload: schemas.PostChatMessageCreate,
    db: Session = Depends(get_db),
):
    review = get_review_or_404(db, review_id)
    request = get_post_generation_request_or_404(db, review.request_id)

    user_msg = models.PostChatMessage(
        review_id=review.id, role="user", content=payload.content
    )
    db.add(user_msg)
    db.commit()

    chat_history = []
    for m in _history(db, review_id)[:-1]:
        content = m.content
        if m.role == "assistant":
            try:
                parsed = json.loads(m.content)
                content = parsed.get("reply") or m.content
            except (json.JSONDecodeError, TypeError):
                pass
        chat_history.append({"role": m.role, "content": content})

    result = request_revision(request, review, "review", chat_history, payload.content)

    assistant_msg = models.PostChatMessage(
        review_id=review.id,
        role="assistant",
        content=json.dumps({"reply": result["reply"], "changes": result["changes"]}),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(review)
    db.refresh(assistant_msg)
    return schemas.ReviewFeedbackResponse(
        review=review_to_out(review), message=message_to_out(assistant_msg)
    )


@router.post("/{review_id}/messages/{message_id}/approve", response_model=schemas.ReviewOut)
def approve_review_message(review_id: int, message_id: int, db: Session = Depends(get_db)):
    """Applies only the fields present in that message."""
    review = get_review_or_404(db, review_id)
    message = (
        db.query(models.PostChatMessage)
        .filter(
            models.PostChatMessage.id == message_id,
            models.PostChatMessage.review_id == review_id,
        )
        .first()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be approved")

    try:
        changes = (json.loads(message.content) or {}).get("changes") or {}
    except (json.JSONDecodeError, TypeError):
        changes = {}
    if not changes:
        raise HTTPException(status_code=400, detail="This message has no revision to apply")

    for field in _EDITABLE:
        if field not in changes:
            continue
        if field == "hashtags":
            review.hashtags = json.dumps(changes["hashtags"])
        else:
            setattr(review, field, changes[field])

    db.commit()
    db.refresh(review)
    return review_to_out(review)
