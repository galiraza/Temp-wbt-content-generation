"""A post's finished branded image: generate the first version, chat-driven
revision, and approving a revision as a new version. Mirrors
app.routers.angle_images exactly, adapted for one difference: the initial
generation needs no user-supplied form data at all (logo, hero photo, title,
industry, and layout variant are all already resolvable from the post and
its request), so create_post_image takes no body.
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_post_image_or_404, get_post_or_404
from app.services.post_generation_service import (
    generate_image_for_post,
    post_image_message_to_out,
    post_image_to_out,
    revise_post_or_reel_image_row,
)
from app.storage import delete_file, save_base64_image, save_upload_bytes

router = APIRouter(tags=["post-images"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


async def _save_reference(file: UploadFile, post_id: int) -> str:
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WEBP images are allowed")
    content = await file.read()
    return save_upload_bytes(content, file.filename, f"post-generation/posts/{post_id}/references")


# --- Generate a new image for a post (initial creation) ---


@router.post("/api/posts/{post_id}/images", response_model=schemas.PostImageOut, status_code=201)
def create_post_image(post_id: int, db: Session = Depends(get_db)):
    """Composites the client's logo, this post's matched hero photo, and a
    randomly-picked layout variant into one finished graphic. Every input is
    already resolvable from the post and its request - no form data needed."""
    post = get_post_or_404(db, post_id)
    variant_rows = db.query(models.VariantLibrary).filter(models.VariantLibrary.kind == "post").all()

    png_bytes = generate_image_for_post(post, variant_rows)
    file_path = save_upload_bytes(png_bytes, "final.png", f"post-generation/posts/{post_id}/generated")

    image = models.PostImage(
        post_id=post_id,
        file_path=file_path,
        background_path=post.hero_image.file_path if post.hero_image else None,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return post_image_to_out(image)


@router.get("/api/posts/{post_id}/images", response_model=List[schemas.PostImageOut])
def list_post_images(post_id: int, db: Session = Depends(get_db)):
    get_post_or_404(db, post_id)
    rows = (
        db.query(models.PostImage)
        .filter(models.PostImage.post_id == post_id)
        .order_by(models.PostImage.created_at)
        .all()
    )
    return [post_image_to_out(r) for r in rows]


@router.delete("/api/posts/{post_id}/images", status_code=204)
def delete_post_images(post_id: int, db: Session = Depends(get_db)):
    """Deletes the entire image history for this post, so its Image tab
    resets to "no image generated yet"."""
    get_post_or_404(db, post_id)
    rows = db.query(models.PostImage).filter(models.PostImage.post_id == post_id).all()
    for row in rows:
        delete_file(row.file_path)
        db.delete(row)
    db.commit()


# --- Per-image endpoints: fetch, chat, approve a revision ---


@router.get("/api/post-images/{image_id}", response_model=schemas.PostImageOut)
def get_post_image(image_id: int, db: Session = Depends(get_db)):
    return post_image_to_out(get_post_image_or_404(db, image_id))


@router.delete("/api/post-images/{image_id}", status_code=204)
def delete_post_image(image_id: int, db: Session = Depends(get_db)):
    """Removes ONE version from a post's image history. Its chat messages
    cascade-delete via the PostImage relationship."""
    image = get_post_image_or_404(db, image_id)
    delete_file(image.file_path)
    db.delete(image)
    db.commit()


@router.get(
    "/api/post-images/{image_id}/messages",
    response_model=List[schemas.PostImageChatMessageOut],
)
def list_post_image_messages(image_id: int, db: Session = Depends(get_db)):
    get_post_image_or_404(db, image_id)
    rows = (
        db.query(models.PostImageChatMessage)
        .filter(models.PostImageChatMessage.post_image_id == image_id)
        .order_by(models.PostImageChatMessage.created_at)
        .all()
    )
    return [post_image_message_to_out(m) for m in rows]


@router.post(
    "/api/post-images/{image_id}/messages",
    response_model=schemas.PostImageChatMessageOut,
)
async def send_post_image_feedback(
    image_id: int,
    content: str = Form(...),
    image_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Chat about this image: save the user's feedback (optionally with an
    attached reference image), generate a revised candidate via the image
    agent, and save it as an assistant message (not yet applied - the user
    must approve it via .../approve to create the next PostImage version,
    keeping full history).
    """
    image = get_post_image_or_404(db, image_id)

    attachment_path = None
    if image_file is not None:
        attachment_path = await _save_reference(image_file, image.post_id)

    user_msg = models.PostImageChatMessage(
        post_image_id=image.id,
        role="user",
        content=content,
        attachment_path=attachment_path,
    )
    db.add(user_msg)
    db.commit()

    history_rows = (
        db.query(models.PostImageChatMessage)
        .filter(models.PostImageChatMessage.post_image_id == image_id)
        .order_by(models.PostImageChatMessage.created_at)
        .all()
    )
    chat_history = []
    for m in history_rows:
        if m.role == "assistant":
            content_for_llm = "Applied a revised image based on the prior feedback."
        else:
            content_for_llm = m.content
        chat_history.append({"role": m.role, "content": content_for_llm})

    b64_data, off_topic_reply = revise_post_or_reel_image_row(
        image, chat_history, attachment_path=attachment_path
    )

    if off_topic_reply:
        content = off_topic_reply
    else:
        candidate_path = save_base64_image(b64_data, f"post-generation/posts/{image.post_id}/generated")
        content = json.dumps({"file_path": candidate_path})

    assistant_msg = models.PostImageChatMessage(
        post_image_id=image.id,
        role="assistant",
        content=content,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return post_image_message_to_out(assistant_msg)


@router.post(
    "/api/post-images/{image_id}/restore",
    response_model=schemas.PostImageOut,
    status_code=201,
)
def restore_post_image_version(image_id: int, db: Session = Depends(get_db)):
    """Makes an older version the current one again, by duplicating it as a
    new PostImage row - mirrors approve, so the full history stays intact."""
    image = get_post_image_or_404(db, image_id)
    new_image = models.PostImage(
        post_id=image.post_id,
        file_path=image.file_path,
        background_path=image.background_path,
        layout_variant=image.layout_variant,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return post_image_to_out(new_image)


@router.post(
    "/api/post-images/{image_id}/messages/{message_id}/approve",
    response_model=schemas.PostImageOut,
)
def approve_post_image_message(image_id: int, message_id: int, db: Session = Depends(get_db)):
    """Applies an approved chat candidate as a NEW PostImage version (keeps
    the previous version in history)."""
    image = get_post_image_or_404(db, image_id)
    message = (
        db.query(models.PostImageChatMessage)
        .filter(
            models.PostImageChatMessage.id == message_id,
            models.PostImageChatMessage.post_image_id == image_id,
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

    new_image = models.PostImage(
        post_id=image.post_id,
        file_path=file_path,
        background_path=image.background_path,
        layout_variant=image.layout_variant,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return post_image_to_out(new_image)
