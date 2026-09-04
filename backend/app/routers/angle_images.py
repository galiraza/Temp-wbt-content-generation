import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_angle_image_or_404, get_angle_or_404
from app.services.angle_image_service import (
    generate_image_for_angle,
    message_to_out,
    revise_image,
    to_out,
)
from app.storage import delete_file, save_base64_image, save_upload_bytes

router = APIRouter(tags=["angle-images"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


async def _save_reference(file: UploadFile, angle_id: int, subdir: str = "references") -> str:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WEBP images are allowed")
    content = await file.read()
    return save_upload_bytes(content, file.filename, f"angles/{angle_id}/{subdir}")


# --- Generate a new image for an angle (initial creation) ---


@router.post(
    "/api/angles/{angle_id}/images", response_model=schemas.AngleImageOut, status_code=201
)
async def create_angle_image(
    angle_id: int,
    header_text: Optional[str] = Form(None),
    additional_info: Optional[str] = Form(None),
    reference_image: Optional[UploadFile] = File(None),
    existing_reference_image_path: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    existing_logo_path: Optional[str] = Form(None),
    company_images: List[UploadFile] = File([]),
    existing_company_image_paths: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Every asset (reference image, logo, company photos) is either a fresh
    upload for this call or a URL reused from a prior AngleImage on this same
    angle (e.g. the "Regenerate" form prefilled from the angle's last
    generation, unchanged) — exactly one of each upload/existing-path pair
    must be given. existing_company_image_paths is a JSON-encoded array of
    URLs, mirroring how company_image_paths is stored on the model.

    Each angle's logo/company photos/reference image are now captured
    per-generation on the AngleImage row itself, rather than shared across
    every angle in the request via a separate company_assets table.
    """
    get_angle_or_404(db, angle_id)

    if reference_image is not None:
        reference_image_path = await _save_reference(reference_image, angle_id, "references")
    elif existing_reference_image_path:
        reference_image_path = existing_reference_image_path
    else:
        raise HTTPException(status_code=400, detail="A reference image is required.")

    if logo is not None:
        logo_path = await _save_reference(logo, angle_id, "logo")
    elif existing_logo_path:
        logo_path = existing_logo_path
    else:
        raise HTTPException(status_code=400, detail="Upload a company logo before generating an image.")

    company_image_paths: List[str] = []
    if existing_company_image_paths:
        try:
            company_image_paths.extend(json.loads(existing_company_image_paths))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="existing_company_image_paths must be a JSON array")
    for file in company_images:
        company_image_paths.append(await _save_reference(file, angle_id, "photos"))
    if not company_image_paths:
        raise HTTPException(status_code=400, detail="Upload a company photo before generating an image.")

    b64_data = generate_image_for_angle(
        header_text=header_text or "",
        additional_info=additional_info or "",
        reference_image_path=reference_image_path,
        logo_path=logo_path,
        company_image_paths=company_image_paths,
    )
    file_path = save_base64_image(b64_data, f"angles/{angle_id}/generated")

    image = models.AngleImage(
        angle_id=angle_id,
        file_path=file_path,
        header_text=header_text or "",
        additional_info=additional_info,
        reference_image_path=reference_image_path,
        logo_path=logo_path,
        company_image_paths=json.dumps(company_image_paths),
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return to_out(image)


@router.get("/api/angles/{angle_id}/images", response_model=List[schemas.AngleImageOut])
def list_angle_images(angle_id: int, db: Session = Depends(get_db)):
    get_angle_or_404(db, angle_id)
    rows = (
        db.query(models.AngleImage)
        .filter(models.AngleImage.angle_id == angle_id)
        .order_by(models.AngleImage.created_at)
        .all()
    )
    return [to_out(r) for r in rows]


@router.delete("/api/angles/{angle_id}/images", status_code=204)
def delete_angle_images(angle_id: int, db: Session = Depends(get_db)):
    """Deletes the entire image history for this angle (all versions), so the
    angle's Image tab resets to "no image generated yet"."""
    get_angle_or_404(db, angle_id)
    rows = db.query(models.AngleImage).filter(models.AngleImage.angle_id == angle_id).all()
    for row in rows:
        delete_file(row.file_path)
        db.delete(row)
    db.commit()


# --- Per-image endpoints: fetch, chat, approve a revision ---


@router.get("/api/angle-images/{image_id}", response_model=schemas.AngleImageOut)
def get_angle_image(image_id: int, db: Session = Depends(get_db)):
    return to_out(get_angle_image_or_404(db, image_id))


@router.delete("/api/angle-images/{image_id}", status_code=204)
def delete_angle_image(image_id: int, db: Session = Depends(get_db)):
    """Removes ONE version from an angle's image history (not the whole
    history — see delete_angle_images for that). Its chat messages cascade-
    delete via the AngleImage relationship."""
    image = get_angle_image_or_404(db, image_id)
    delete_file(image.file_path)
    db.delete(image)
    db.commit()


@router.get(
    "/api/angle-images/{image_id}/messages",
    response_model=List[schemas.AngleImageChatMessageOut],
)
def list_angle_image_messages(image_id: int, db: Session = Depends(get_db)):
    get_angle_image_or_404(db, image_id)
    rows = (
        db.query(models.AngleImageChatMessage)
        .filter(models.AngleImageChatMessage.angle_image_id == image_id)
        .order_by(models.AngleImageChatMessage.created_at)
        .all()
    )
    return [message_to_out(m) for m in rows]


@router.post(
    "/api/angle-images/{image_id}/messages",
    response_model=schemas.AngleImageChatMessageOut,
)
async def send_angle_image_feedback(
    image_id: int,
    content: str = Form(...),
    image_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Chat about this image: save the user's feedback (optionally with an
    attached reference image, e.g. "use this as the new logo"), generate a
    revised candidate image via the image agent, and save it as an assistant
    message (not yet applied — the user must approve it via .../approve to
    create the next AngleImage version, keeping full history).
    """
    image = get_angle_image_or_404(db, image_id)

    attachment_path = None
    if image_file is not None:
        attachment_path = await _save_reference(image_file, image.angle_id)

    user_msg = models.AngleImageChatMessage(
        angle_image_id=image.id,
        role="user",
        content=content,
        attachment_path=attachment_path,
    )
    db.add(user_msg)
    db.commit()

    history_rows = (
        db.query(models.AngleImageChatMessage)
        .filter(models.AngleImageChatMessage.angle_image_id == image_id)
        .order_by(models.AngleImageChatMessage.created_at)
        .all()
    )
    # For chat history passed to the LLM, represent assistant turns as plain text
    # rather than raw JSON, so the model reads them naturally.
    chat_history = []
    for m in history_rows:
        if m.role == "assistant":
            content_for_llm = "Applied a revised image based on the prior feedback."
        else:
            content_for_llm = m.content
        chat_history.append({"role": m.role, "content": content_for_llm})

    b64_data, off_topic_reply = revise_image(image, chat_history, attachment_path=attachment_path)

    # An off-topic reply is stored as plain chatbot text (no candidate image to
    # approve); a real revision is stored as JSON so the frontend can show it as
    # an editable preview — mirrors send_angle_feedback() in angles.py.
    if off_topic_reply:
        content = off_topic_reply
    else:
        candidate_path = save_base64_image(b64_data, f"angles/{image.angle_id}/generated")
        content = json.dumps({"file_path": candidate_path})

    assistant_msg = models.AngleImageChatMessage(
        angle_image_id=image.id,
        role="assistant",
        content=content,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return message_to_out(assistant_msg)


@router.post(
    "/api/angle-images/{image_id}/restore",
    response_model=schemas.AngleImageOut,
    status_code=201,
)
def restore_angle_image_version(image_id: int, db: Session = Depends(get_db)):
    """Makes an older version history entry the current one again, by
    duplicating it as a new AngleImage row — mirrors how approving a chat
    candidate creates a new version rather than mutating/deleting anything,
    so the full history stays intact."""
    image = get_angle_image_or_404(db, image_id)
    new_image = models.AngleImage(
        angle_id=image.angle_id,
        file_path=image.file_path,
        header_text=image.header_text,
        additional_info=image.additional_info,
        reference_image_path=image.reference_image_path,
        logo_path=image.logo_path,
        company_image_paths=image.company_image_paths,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return to_out(new_image)


@router.post(
    "/api/angle-images/{image_id}/messages/{message_id}/approve",
    response_model=schemas.AngleImageOut,
)
def approve_angle_image_message(
    image_id: int, message_id: int, db: Session = Depends(get_db)
):
    """Applies an approved chat candidate as a NEW AngleImage version (keeps
    the previous version in history)."""
    image = get_angle_image_or_404(db, image_id)
    message = (
        db.query(models.AngleImageChatMessage)
        .filter(
            models.AngleImageChatMessage.id == message_id,
            models.AngleImageChatMessage.angle_image_id == image_id,
        )
        .first()
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Only assistant messages can be approved")

    try:
        parsed = json.loads(message.content)
        file_path = parsed["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="This message has no candidate image")

    new_image = models.AngleImage(
        angle_id=image.angle_id,
        file_path=file_path,
        header_text=image.header_text,
        additional_info=image.additional_info,
        reference_image_path=image.reference_image_path,
        logo_path=image.logo_path,
        company_image_paths=image.company_image_paths,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return to_out(new_image)
