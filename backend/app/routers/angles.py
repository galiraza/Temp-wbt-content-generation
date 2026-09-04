import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_ad_angle_request_or_404, get_angle_or_404
from app.services.ad_angle_service import (
    message_to_out,
    regenerate_single,
    regenerate_with_feedback,
)

router = APIRouter(prefix="/api/angles", tags=["angles"])


@router.post("/{angle_id}/approve", response_model=schemas.AngleOut)
def approve_angle(angle_id: int, db: Session = Depends(get_db)):
    angle = get_angle_or_404(db, angle_id)
    angle.status = "approved"
    db.commit()
    db.refresh(angle)
    return angle


@router.put("/{angle_id}", response_model=schemas.AngleOut)
def update_angle(angle_id: int, payload: schemas.AngleUpdate, db: Session = Depends(get_db)):
    """Directly overwrite this angle's headline/primary_text with user-typed edits
    (bypasses the AI feedback chat entirely — no LLM call, no approval step)."""
    angle = get_angle_or_404(db, angle_id)
    angle.headline = payload.headline
    angle.primary_text = payload.primary_text
    db.commit()
    db.refresh(angle)
    return angle


@router.post("/{angle_id}/regenerate", response_model=schemas.AngleOut)
def regenerate_angle(angle_id: int, db: Session = Depends(get_db)):
    """Regenerate just this one angle's whole content (cheaper than regenerating all 6)."""
    angle = get_angle_or_404(db, angle_id)
    request = get_ad_angle_request_or_404(db, angle.request_id)

    headline, primary_text = regenerate_single(request, angle.headline, angle.primary_text)
    angle.headline = headline
    angle.primary_text = primary_text
    angle.status = "pending"
    db.commit()
    db.refresh(angle)
    return angle


@router.get("/{angle_id}/messages", response_model=List[schemas.ChatMessageOut])
def list_angle_messages(angle_id: int, db: Session = Depends(get_db)):
    get_angle_or_404(db, angle_id)
    rows = (
        db.query(models.AngleChatMessage)
        .filter(models.AngleChatMessage.angle_id == angle_id)
        .order_by(models.AngleChatMessage.created_at)
        .all()
    )
    return [message_to_out(m) for m in rows]


@router.post("/{angle_id}/messages", response_model=schemas.FeedbackResponse)
def send_angle_feedback(
    angle_id: int, payload: schemas.ChatMessageCreate, db: Session = Depends(get_db)
):
    """Chat with the LLM about this angle: save the user's chat message, ask the LLM
    (with full chat history) to propose a revised headline + primary_text, and save its
    reply as a chat message. This does NOT change the angle's stored content — the user
    must explicitly approve a reply (see .../messages/{message_id}/approve) to apply it.
    """
    angle = get_angle_or_404(db, angle_id)
    request = get_ad_angle_request_or_404(db, angle.request_id)

    user_msg = models.AngleChatMessage(angle_id=angle.id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    history_rows = (
        db.query(models.AngleChatMessage)
        .filter(models.AngleChatMessage.angle_id == angle_id)
        .order_by(models.AngleChatMessage.created_at)
        .all()
    )
    # For chat history passed to the LLM, represent assistant turns as plain text
    # (headline + primary text) rather than raw JSON, so the model reads them naturally.
    chat_history = []
    for m in history_rows:
        if m.role == "assistant":
            try:
                parsed = json.loads(m.content)
                content = f"Headline: {parsed.get('headline', '')}\nPrimary text: {parsed.get('primary_text', '')}"
            except (json.JSONDecodeError, AttributeError):
                content = m.content
        else:
            content = m.content
        chat_history.append({"role": m.role, "content": content})

    new_headline, new_primary_text, off_topic_reply = regenerate_with_feedback(
        request, angle.headline, angle.primary_text, chat_history
    )

    # An off-topic reply is stored as plain chatbot text (no angle revision to approve);
    # a real revision is stored as JSON so the frontend can show it as an editable preview.
    content = (
        off_topic_reply
        if off_topic_reply
        else json.dumps({"headline": new_headline, "primary_text": new_primary_text})
    )
    assistant_msg = models.AngleChatMessage(angle_id=angle.id, role="assistant", content=content)
    db.add(assistant_msg)
    db.commit()
    db.refresh(angle)
    db.refresh(assistant_msg)
    return schemas.FeedbackResponse(angle=angle, message=message_to_out(assistant_msg))


@router.post("/{angle_id}/messages/{message_id}/approve", response_model=schemas.AngleOut)
def approve_angle_message(angle_id: int, message_id: int, db: Session = Depends(get_db)):
    """Apply a specific assistant chat message's headline + primary_text to the angle
    as its current content — does not lock the angle (that's the separate .../approve
    endpoint); the angle stays editable/regeneratable afterwards."""
    angle = get_angle_or_404(db, angle_id)
    message = (
        db.query(models.AngleChatMessage)
        .filter(
            models.AngleChatMessage.id == message_id,
            models.AngleChatMessage.angle_id == angle_id,
        )
        .first()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be approved")

    try:
        parsed = json.loads(message.content)
        headline = parsed["headline"]
        primary_text = parsed["primary_text"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="This message has no structured revision")

    angle.headline = headline
    angle.primary_text = primary_text
    db.commit()
    db.refresh(angle)
    return angle
