"""A single generated post's lifecycle: manual edit, approve, regenerate, and its
copy chat board.

The chat proposes a revision as a message and the user must explicitly approve
that message before it touches the row — the same contract as the angle chat. The
difference here is that a revision is PARTIAL: approving a turn that only changed
the hashtags leaves the title and caption exactly as they were.
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_post_generation_request_or_404, get_post_or_404
from app.services.post_generation_service import (
    message_to_out,
    post_to_out,
    regenerate_one_post,
)
from app.agents.post_generation.feedback_agent import request_revision

router = APIRouter(prefix="/api/posts", tags=["posts"])

_EDITABLE = ("title", "caption", "hashtags")


@router.get("/{post_id}", response_model=schemas.PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    return post_to_out(get_post_or_404(db, post_id))


@router.put("/{post_id}", response_model=schemas.PostOut)
def update_post(post_id: int, payload: schemas.PostUpdate, db: Session = Depends(get_db)):
    """Direct user-typed edit. No LLM, no approval step."""
    post = get_post_or_404(db, post_id)
    post.title = payload.title
    post.caption = payload.caption
    post.hashtags = json.dumps(payload.hashtags)
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@router.post("/{post_id}/approve", response_model=schemas.PostOut)
def approve_post(post_id: int, db: Session = Depends(get_db)):
    """Locks the copy. This is the gate the image step waits on: an image is only
    generated from copy the user has signed off."""
    post = get_post_or_404(db, post_id)
    post.status = "approved"
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@router.post("/{post_id}/unapprove", response_model=schemas.PostOut)
def unapprove_post(post_id: int, db: Session = Depends(get_db)):
    post = get_post_or_404(db, post_id)
    post.status = "pending"
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@router.post("/{post_id}/regenerate", response_model=schemas.PostOut)
def regenerate_post_route(post_id: int, db: Session = Depends(get_db)):
    """Rewrites this one post's title and caption, keeping its slot number and
    theme so the month keeps its shape. The hashtags are left as they are."""
    post = get_post_or_404(db, post_id)
    request = get_post_generation_request_or_404(db, post.request_id)

    generated = regenerate_one_post(request, post)
    post.title = generated["title"]
    post.caption = generated["caption"]
    # Hashtags are deliberately NOT touched: regenerate rewrites the copy only.
    post.status = "pending"
    db.commit()
    db.refresh(post)
    return post_to_out(post)


def _history(db: Session, post_id: int) -> List[models.PostChatMessage]:
    return (
        db.query(models.PostChatMessage)
        .filter(models.PostChatMessage.post_id == post_id)
        .order_by(models.PostChatMessage.created_at)
        .all()
    )


@router.get("/{post_id}/messages", response_model=List[schemas.ContentChatMessageOut])
def list_post_messages(post_id: int, db: Session = Depends(get_db)):
    get_post_or_404(db, post_id)
    return [message_to_out(m) for m in _history(db, post_id)]


@router.post("/{post_id}/messages", response_model=schemas.PostFeedbackResponse)
def send_post_feedback(
    post_id: int,
    payload: schemas.PostChatMessageCreate,
    db: Session = Depends(get_db),
):
    """Saves the user's message, asks the model for a revision with the full
    thread as context, and saves the reply. Does NOT change the post."""
    post = get_post_or_404(db, post_id)
    request = get_post_generation_request_or_404(db, post.request_id)

    user_msg = models.PostChatMessage(post_id=post.id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    # Render prior assistant turns back to prose so the model reads its own
    # history naturally rather than as raw JSON.
    chat_history = []
    for m in _history(db, post_id)[:-1]:
        content = m.content
        if m.role == "assistant":
            try:
                parsed = json.loads(m.content)
                content = parsed.get("reply") or m.content
            except (json.JSONDecodeError, TypeError):
                pass
        chat_history.append({"role": m.role, "content": content})

    result = request_revision(request, post, "post", chat_history, payload.content)

    assistant_msg = models.PostChatMessage(
        post_id=post.id,
        role="assistant",
        content=json.dumps({"reply": result["reply"], "changes": result["changes"]}),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(post)
    db.refresh(assistant_msg)
    return schemas.PostFeedbackResponse(
        post=post_to_out(post), message=message_to_out(assistant_msg)
    )


@router.post("/{post_id}/messages/{message_id}/approve", response_model=schemas.PostOut)
def approve_post_message(post_id: int, message_id: int, db: Session = Depends(get_db)):
    """Applies one assistant message's revision.

    Only the fields present in that message are written — the rest of the post is
    left alone. Does not lock the post; that's the separate approve endpoint.
    """
    post = get_post_or_404(db, post_id)
    message = (
        db.query(models.PostChatMessage)
        .filter(
            models.PostChatMessage.id == message_id,
            models.PostChatMessage.post_id == post_id,
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
            post.hashtags = json.dumps(changes["hashtags"])
        else:
            setattr(post, field, changes[field])

    db.commit()
    db.refresh(post)
    return post_to_out(post)
