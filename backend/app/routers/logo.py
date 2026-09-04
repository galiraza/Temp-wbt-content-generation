import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import (
    get_logo_from_previous_request_or_404,
    get_logo_from_scratch_request_or_404,
    get_logo_image_or_404,
)
from app.services.logo_image_service import (
    generate_concepts_from_scratch,
    generate_edits_from_previous,
    get_meeting_brief,
    message_to_out,
    revise_image,
    to_out,
)
from app.storage import delete_file, save_base64_image, save_upload_bytes

router = APIRouter(prefix="/api/logos", tags=["logos"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


async def _read_validated_image(file: UploadFile) -> bytes:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WEBP images are allowed")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 10MB")
    return content


async def _save_reference(file: UploadFile, subdir: str) -> str:
    content = await _read_validated_image(file)
    return save_upload_bytes(content, file.filename or "image.png", subdir)


def _save_logo_images(b64_list: List[str], subdir: str, **fk) -> List[models.LogoImage]:
    images = []
    for slot, b64_data in enumerate(b64_list, start=1):
        file_path = save_base64_image(b64_data, subdir)
        images.append(models.LogoImage(slot=slot, file_path=file_path, **fk))
    return images


def _replace_images(
    db: Session, old_images: List[models.LogoImage], new_images: List[models.LogoImage]
) -> None:
    """Swap a request's logos for a freshly generated set.

    Ordering matters. The new images are already uploaded by the time this runs
    and the old rows are only dropped right before the commit, so a failure
    during generation or upload leaves the existing logos untouched — the job
    is never left with no logos at all.

    Storage files are deleted only after the commit succeeds: a deleted row can
    be rolled back, a deleted file cannot.
    """
    stale_paths = [image.file_path for image in old_images]
    # Chat attachments live in storage too, and the rows cascade away with the
    # image, so their files would otherwise be orphaned.
    stale_paths += [
        message.attachment_path
        for image in old_images
        for message in image.chat_messages
        if message.attachment_path
    ]

    for image in old_images:
        db.delete(image)
    db.flush()

    db.add_all(new_images)
    db.commit()

    for path in stale_paths:
        delete_file(path)


# --- From scratch ---


@router.post("/from-scratch", response_model=schemas.LogoFromScratchOut, status_code=201)
def create_logo_from_scratch(payload: schemas.LogoFromScratchCreate, db: Session = Depends(get_db)):
    row = models.LogoFromScratchRequest(
        company_name=payload.company_name,
        industry=payload.industry,
        usps=payload.usps,
        fathom_url=payload.fathom_url,
        suggestion=payload.suggestion,
        use_ai_suggestion=payload.use_ai_suggestion,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    transcript, meeting_brief = get_meeting_brief(row.fathom_url)
    if transcript:
        row.fathom_transcript = transcript
        db.commit()

    b64_list = generate_concepts_from_scratch(
        row.company_name,
        row.industry,
        row.usps or "",
        row.suggestion or "",
        meeting_brief=meeting_brief,
    )
    images = _save_logo_images(
        b64_list, f"logo-generation/scratch/{row.id}", scratch_request_id=row.id
    )
    db.add_all(images)
    db.commit()
    db.refresh(row)
    return row


@router.get("/from-scratch", response_model=List[schemas.LogoFromScratchOut])
def list_logo_from_scratch(db: Session = Depends(get_db)):
    return (
        db.query(models.LogoFromScratchRequest)
        .order_by(models.LogoFromScratchRequest.id.desc())
        .all()
    )


@router.get("/from-scratch/{request_id}/images", response_model=List[schemas.LogoImageOut])
def list_logo_from_scratch_images(request_id: int, db: Session = Depends(get_db)):
    get_logo_from_scratch_request_or_404(db, request_id)
    rows = (
        db.query(models.LogoImage)
        .filter(models.LogoImage.scratch_request_id == request_id)
        .order_by(models.LogoImage.slot, models.LogoImage.created_at)
        .all()
    )
    return [to_out(r) for r in rows]


@router.post("/from-scratch/{request_id}/regenerate", response_model=List[schemas.LogoImageOut])
def regenerate_logo_from_scratch(
    request_id: int,
    payload: Optional[schemas.LogoFromScratchUpdate] = None,
    db: Session = Depends(get_db),
):
    """Regenerate all logo concepts for a request, replacing the current set.

    Optionally accepts an edited brief so the "Run again" flow can change the
    details and regenerate in one call, mirroring the ad angles equivalent.

    The slow generation runs before anything is deleted — see _replace_images.
    """
    row = get_logo_from_scratch_request_or_404(db, request_id)

    if payload is not None:
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        db.commit()

    transcript, meeting_brief = get_meeting_brief(row.fathom_url)
    if transcript:
        row.fathom_transcript = transcript
        db.commit()

    b64_list = generate_concepts_from_scratch(
        row.company_name,
        row.industry,
        row.usps or "",
        row.suggestion or "",
        meeting_brief=meeting_brief,
    )
    new_images = _save_logo_images(
        b64_list, f"logo-generation/scratch/{row.id}", scratch_request_id=row.id
    )
    _replace_images(db, list(row.images), new_images)
    return [to_out(image) for image in new_images]


@router.delete("/from-scratch/{request_id}", status_code=204)
def delete_logo_from_scratch(request_id: int, db: Session = Depends(get_db)):
    row = get_logo_from_scratch_request_or_404(db, request_id)
    for image in row.images:
        delete_file(image.file_path)
    db.delete(row)
    db.commit()


# --- From previous logo ---


@router.post("/from-previous", response_model=schemas.LogoFromPreviousOut, status_code=201)
async def create_logo_from_previous(
    logo: UploadFile,
    company_name: str = Form(...),
    suggestion: Optional[str] = Form(None),
    use_ai_suggestion: bool = Form(False),
    fathom_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    logo_path = await _save_reference(logo, "logo-generation/previous")

    row = models.LogoFromPreviousRequest(
        company_name=company_name,
        logo_path=logo_path,
        suggestion=suggestion,
        use_ai_suggestion=use_ai_suggestion,
        fathom_url=fathom_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    transcript, meeting_brief = get_meeting_brief(row.fathom_url)
    if transcript:
        row.fathom_transcript = transcript
        db.commit()

    b64_list = generate_edits_from_previous(
        row.logo_path, row.company_name or "", row.suggestion or "", meeting_brief=meeting_brief
    )
    images = _save_logo_images(
        b64_list, f"logo-generation/previous/{row.id}/generated", previous_request_id=row.id
    )
    db.add_all(images)
    db.commit()
    db.refresh(row)
    return row


@router.get("/from-previous", response_model=List[schemas.LogoFromPreviousOut])
def list_logo_from_previous(db: Session = Depends(get_db)):
    return (
        db.query(models.LogoFromPreviousRequest)
        .order_by(models.LogoFromPreviousRequest.id.desc())
        .all()
    )


@router.get("/from-previous/{request_id}/images", response_model=List[schemas.LogoImageOut])
def list_logo_from_previous_images(request_id: int, db: Session = Depends(get_db)):
    get_logo_from_previous_request_or_404(db, request_id)
    rows = (
        db.query(models.LogoImage)
        .filter(models.LogoImage.previous_request_id == request_id)
        .order_by(models.LogoImage.slot, models.LogoImage.created_at)
        .all()
    )
    return [to_out(r) for r in rows]


@router.post("/from-previous/{request_id}/regenerate", response_model=List[schemas.LogoImageOut])
async def regenerate_logo_from_previous(
    request_id: int,
    logo: Optional[UploadFile] = File(None),
    suggestion: Optional[str] = Form(None),
    use_ai_suggestion: Optional[bool] = Form(None),
    fathom_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Regenerate all revamped logos for a request, replacing the current set.

    Multipart rather than JSON because the brief includes the source logo, which
    the caller may swap for a different file. Omitting `logo` keeps the existing
    one — the common case of "same logo, different direction".
    """
    row = get_logo_from_previous_request_or_404(db, request_id)

    replaced_logo_path = None
    if logo is not None:
        replaced_logo_path = row.logo_path
        row.logo_path = await _save_reference(logo, "logo-generation/previous")
    if suggestion is not None:
        row.suggestion = suggestion
    if use_ai_suggestion is not None:
        row.use_ai_suggestion = use_ai_suggestion
    if fathom_url is not None:
        row.fathom_url = fathom_url
    db.commit()

    transcript, meeting_brief = get_meeting_brief(row.fathom_url)
    if transcript:
        row.fathom_transcript = transcript
        db.commit()

    b64_list = generate_edits_from_previous(
        row.logo_path, row.company_name or "", row.suggestion or "", meeting_brief=meeting_brief
    )
    new_images = _save_logo_images(
        b64_list, f"logo-generation/previous/{row.id}/generated", previous_request_id=row.id
    )
    _replace_images(db, list(row.images), new_images)

    # Only once the new source logo is committed and generation has succeeded —
    # deleting it earlier would strand the request with a dead logo_path if
    # generation failed.
    if replaced_logo_path:
        delete_file(replaced_logo_path)
    return [to_out(image) for image in new_images]


@router.delete("/from-previous/{request_id}", status_code=204)
def delete_logo_from_previous(request_id: int, db: Session = Depends(get_db)):
    row = get_logo_from_previous_request_or_404(db, request_id)
    delete_file(row.logo_path)
    for image in row.images:
        delete_file(image.file_path)
    db.delete(row)
    db.commit()


# --- Per-logo-image endpoints: fetch, chat, approve a revision, restore ---


@router.get("/images/{image_id}", response_model=schemas.LogoImageOut)
def get_logo_image(image_id: int, db: Session = Depends(get_db)):
    return to_out(get_logo_image_or_404(db, image_id))


@router.delete("/images/{image_id}", status_code=204)
def delete_logo_image(image_id: int, db: Session = Depends(get_db)):
    """Removes ONE version from a slot's history. Its chat messages
    cascade-delete via the LogoImage relationship."""
    image = get_logo_image_or_404(db, image_id)
    delete_file(image.file_path)
    db.delete(image)
    db.commit()


@router.get("/images/{image_id}/messages", response_model=List[schemas.LogoImageChatMessageOut])
def list_logo_image_messages(image_id: int, db: Session = Depends(get_db)):
    get_logo_image_or_404(db, image_id)
    rows = (
        db.query(models.LogoImageChatMessage)
        .filter(models.LogoImageChatMessage.logo_image_id == image_id)
        .order_by(models.LogoImageChatMessage.created_at)
        .all()
    )
    return [message_to_out(m) for m in rows]


@router.post("/images/{image_id}/messages", response_model=schemas.LogoImageChatMessageOut)
async def send_logo_image_feedback(
    image_id: int,
    content: str = Form(...),
    image_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Chat about this logo version: save the user's feedback (optionally
    with an attached reference image), generate a revised candidate via the
    image agent, and save it as an assistant message (not yet applied — the
    user must approve it via .../approve to create the next LogoImage
    version, keeping full history for this slot).
    """
    image = get_logo_image_or_404(db, image_id)

    attachment_path = None
    if image_file is not None:
        attachment_path = await _save_reference(image_file, f"logo-generation/references/{image.id}")

    user_msg = models.LogoImageChatMessage(
        logo_image_id=image.id,
        role="user",
        content=content,
        attachment_path=attachment_path,
    )
    db.add(user_msg)
    db.commit()

    history_rows = (
        db.query(models.LogoImageChatMessage)
        .filter(models.LogoImageChatMessage.logo_image_id == image_id)
        .order_by(models.LogoImageChatMessage.created_at)
        .all()
    )
    chat_history = []
    for m in history_rows:
        if m.role == "assistant":
            content_for_llm = "Applied a revised logo based on the prior feedback."
        else:
            content_for_llm = m.content
        chat_history.append({"role": m.role, "content": content_for_llm})

    b64_data, off_topic_reply = revise_image(image, chat_history, attachment_path=attachment_path)

    if off_topic_reply:
        content = off_topic_reply
    else:
        subdir = (
            f"logo-generation/scratch/{image.scratch_request_id}"
            if image.scratch_request_id
            else f"logo-generation/previous/{image.previous_request_id}/generated"
        )
        candidate_path = save_base64_image(b64_data, subdir)
        content = json.dumps({"file_path": candidate_path})

    assistant_msg = models.LogoImageChatMessage(
        logo_image_id=image.id,
        role="assistant",
        content=content,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return message_to_out(assistant_msg)


@router.post("/images/{image_id}/restore", response_model=schemas.LogoImageOut, status_code=201)
def restore_logo_image_version(image_id: int, db: Session = Depends(get_db)):
    """Makes an older version the current one again for this slot, by
    duplicating it as a new LogoImage row — nothing is mutated/deleted, so
    the full history stays intact."""
    image = get_logo_image_or_404(db, image_id)
    new_image = models.LogoImage(
        scratch_request_id=image.scratch_request_id,
        previous_request_id=image.previous_request_id,
        slot=image.slot,
        file_path=image.file_path,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return to_out(new_image)


@router.post(
    "/images/{image_id}/messages/{message_id}/approve", response_model=schemas.LogoImageOut
)
def approve_logo_image_message(image_id: int, message_id: int, db: Session = Depends(get_db)):
    """Applies an approved chat candidate as a NEW LogoImage version for this
    slot (keeps the previous version in history)."""
    image = get_logo_image_or_404(db, image_id)
    message = (
        db.query(models.LogoImageChatMessage)
        .filter(
            models.LogoImageChatMessage.id == message_id,
            models.LogoImageChatMessage.logo_image_id == image_id,
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

    new_image = models.LogoImage(
        scratch_request_id=image.scratch_request_id,
        previous_request_id=image.previous_request_id,
        slot=image.slot,
        file_path=file_path,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return to_out(new_image)
