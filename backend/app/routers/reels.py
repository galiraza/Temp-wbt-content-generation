"""A single generated reel's lifecycle: manual edit, approve, regenerate, and its
copy chat board.

Mirrors app.routers.posts, with two differences that come from the reel itself:
there is no title, and the chat lives in reel_chat_messages rather than the shared
post_chat_messages table. Reels are an independent module.

As with posts, the chat proposes a revision as a message and the user must
explicitly approve that message before it touches the row, and a revision is
PARTIAL: approving a turn that only changed the hashtags leaves the script and
caption exactly as they were.
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.agents.post_generation.feedback_agent import request_revision
from app.database import get_db
from app.routers.dependencies import get_post_generation_request_or_404, get_reel_or_404
from app.services.post_generation_service import (
    reel_message_to_out,
    reel_to_out,
    regenerate_one_reel,
)

router = APIRouter(prefix="/api/reels", tags=["reels"])

_EDITABLE = ("reel_text", "caption", "hashtags")


@router.get("/{reel_id}", response_model=schemas.ReelOut)
def get_reel(reel_id: int, db: Session = Depends(get_db)):
    return reel_to_out(get_reel_or_404(db, reel_id))


@router.put("/{reel_id}", response_model=schemas.ReelOut)
def update_reel(reel_id: int, payload: schemas.ReelUpdate, db: Session = Depends(get_db)):
    """Direct user-typed edit. No LLM, no approval step."""
    reel = get_reel_or_404(db, reel_id)
    reel.reel_text = payload.reel_text
    reel.caption = payload.caption
    reel.hashtags = json.dumps(payload.hashtags)
    db.commit()
    db.refresh(reel)
    return reel_to_out(reel)


@router.post("/{reel_id}/approve", response_model=schemas.ReelOut)
def approve_reel(reel_id: int, db: Session = Depends(get_db)):
    """Locks the copy. This is the gate the image step waits on."""
    reel = get_reel_or_404(db, reel_id)
    reel.status = "approved"
    db.commit()
    db.refresh(reel)
    return reel_to_out(reel)


@router.post("/{reel_id}/unapprove", response_model=schemas.ReelOut)
def unapprove_reel(reel_id: int, db: Session = Depends(get_db)):
    reel = get_reel_or_404(db, reel_id)
    reel.status = "pending"
    db.commit()
    db.refresh(reel)
    return reel_to_out(reel)


@router.post("/{reel_id}/regenerate", response_model=schemas.ReelOut)
def regenerate_reel_route(reel_id: int, db: Session = Depends(get_db)):
    """Rewrites this one reel's script and caption, keeping its slot number and
    angle so the month keeps its shape. The hashtags are left as they are."""
    reel = get_reel_or_404(db, reel_id)
    request = get_post_generation_request_or_404(db, reel.request_id)

    generated = regenerate_one_reel(request, reel)
    reel.reel_text = generated["reel_text"]
    reel.caption = generated["caption"]
    # Hashtags are deliberately NOT touched: regenerate rewrites the copy only.
    reel.status = "pending"
    db.commit()
    db.refresh(reel)
    return reel_to_out(reel)


def _history(db: Session, reel_id: int) -> List[models.ReelChatMessage]:
    return (
        db.query(models.ReelChatMessage)
        .filter(models.ReelChatMessage.reel_id == reel_id)
        .order_by(models.ReelChatMessage.created_at)
        .all()
    )


@router.get("/{reel_id}/messages", response_model=List[schemas.ReelChatMessageOut])
def list_reel_messages(reel_id: int, db: Session = Depends(get_db)):
    get_reel_or_404(db, reel_id)
    return [reel_message_to_out(m) for m in _history(db, reel_id)]


@router.post("/{reel_id}/messages", response_model=schemas.ReelFeedbackResponse)
def send_reel_feedback(
    reel_id: int,
    payload: schemas.PostChatMessageCreate,
    db: Session = Depends(get_db),
):
    """Saves the user's message, asks the model for a revision with the full
    thread as context, and saves the reply. Does NOT change the reel."""
    reel = get_reel_or_404(db, reel_id)
    request = get_post_generation_request_or_404(db, reel.request_id)

    user_msg = models.ReelChatMessage(reel_id=reel.id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    # Render prior assistant turns back to prose so the model reads its own
    # history naturally rather than as raw JSON.
    chat_history = []
    for m in _history(db, reel_id)[:-1]:
        content = m.content
        if m.role == "assistant":
            try:
                parsed = json.loads(m.content)
                content = parsed.get("reply") or m.content
            except (json.JSONDecodeError, TypeError):
                pass
        chat_history.append({"role": m.role, "content": content})

    result = request_revision(request, reel, "reel", chat_history, payload.content)

    assistant_msg = models.ReelChatMessage(
        reel_id=reel.id,
        role="assistant",
        content=json.dumps({"reply": result["reply"], "changes": result["changes"]}),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(reel)
    db.refresh(assistant_msg)
    return schemas.ReelFeedbackResponse(
        reel=reel_to_out(reel), message=reel_message_to_out(assistant_msg)
    )


@router.post("/{reel_id}/messages/{message_id}/approve", response_model=schemas.ReelOut)
def approve_reel_message(reel_id: int, message_id: int, db: Session = Depends(get_db)):
    """Applies one assistant message's revision.

    Only the fields present in that message are written — the rest of the reel is
    left alone. Does not lock the reel; that's the separate approve endpoint.
    """
    reel = get_reel_or_404(db, reel_id)
    message = (
        db.query(models.ReelChatMessage)
        .filter(
            models.ReelChatMessage.id == message_id,
            models.ReelChatMessage.reel_id == reel_id,
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
            reel.hashtags = json.dumps(changes["hashtags"])
        else:
            setattr(reel, field, changes[field])

    db.commit()
    db.refresh(reel)
    return reel_to_out(reel)
