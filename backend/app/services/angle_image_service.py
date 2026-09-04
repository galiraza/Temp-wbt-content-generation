"""Business logic for angle image generation: calling the image agent with
the reference image + company logo/photo paths the router resolved, and
converting DB rows to API schemas.
"""

import json
from contextlib import ExitStack
from typing import List, Optional, Tuple

from fastapi import HTTPException

from app import models, schemas
from app.agents import generate_ad_image, revise_ad_image
from app.config import has_openai_key
from app.errors import UpstreamServiceError
from app.storage import download_to_temp_file


def to_out(row: models.AngleImage) -> schemas.AngleImageOut:
    return schemas.AngleImageOut(
        id=row.id,
        angle_id=row.angle_id,
        file_path=row.file_path,
        header_text=row.header_text,
        additional_info=row.additional_info,
        reference_image_path=row.reference_image_path,
        logo_path=row.logo_path,
        company_image_paths=json.loads(row.company_image_paths) if row.company_image_paths else [],
        created_at=row.created_at,
    )


def message_to_out(row: models.AngleImageChatMessage) -> schemas.AngleImageChatMessageOut:
    candidate_image_path = None
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
            candidate_image_path = parsed.get("file_path")
        except (json.JSONDecodeError, AttributeError):
            pass
    return schemas.AngleImageChatMessageOut(
        id=row.id,
        angle_image_id=row.angle_image_id,
        role=row.role,
        content=row.content,
        candidate_image_path=candidate_image_path,
        attachment_path=row.attachment_path,
        created_at=row.created_at,
    )


def generate_image_for_angle(
    header_text: str,
    additional_info: str,
    reference_image_path: str,
    logo_path: str,
    company_image_paths: List[str],
) -> str:
    """Returns base64 PNG data for a newly generated image.

    reference_image_path is the reference ad — the Generator agent
    replicates it exactly, swapping in the company logo, the company
    photo(s), header_text, and (when given) additional_info into the
    reference's own body-copy/description block; everything else (CTA,
    checklist/benefit list, badges, backgrounds) stays untouched. A
    reference image, a company logo, and at least one company photo are all
    required — there is nothing to replicate onto and no from-scratch
    fallback in this pipeline otherwise. ALL given company photos are used
    (not just the first) — some reference templates have multiple photo
    slots (e.g. one large primary photo plus several smaller supporting
    photos in a grid), and it takes exactly as many real photos as slots to
    avoid the Generator inventing content for the rest.

    logo_path/company_image_paths/reference_image_path are each either a
    freshly uploaded file's Supabase Storage URL or a URL reused from a
    prior AngleImage on this same angle (the router resolves which). Every
    one of them is downloaded to a temp file (via download_to_temp_file) for
    the duration of this call, since the image generation agent needs real
    local paths to open() and send to OpenAI's API. Temp files are cleaned
    up automatically once the `with` block exits, success or failure.
    """
    if not has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="Image generation requires OPENAI_API_KEY to be configured.",
        )

    try:
        with ExitStack() as stack:
            logo_local_path = stack.enter_context(download_to_temp_file(logo_path))
            photo_local_paths = [
                stack.enter_context(download_to_temp_file(p)) for p in company_image_paths
            ]
            reference_path = stack.enter_context(download_to_temp_file(reference_image_path))
            return generate_ad_image(
                header_text=header_text,
                additional_info=additional_info,
                logo_path=logo_local_path,
                photo_paths=photo_local_paths,
                reference_path=reference_path,
            )
    except Exception as exc:
        raise UpstreamServiceError(
            "Image generation",
            "Couldn't generate the image. Please try again.",
            internal=str(exc),
        ) from exc


def revise_image(
    current_image: models.AngleImage,
    chat_history: List[dict],
    attachment_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Returns a (b64_json, off_topic_reply) tuple for a revision request
    based on chat feedback — see revise_ad_image() in editor_agent.py for
    the off-topic-guardrail semantics.

    chat_history: full conversation for this image (both roles, oldest
    first, ending with the latest user feedback) — built by the router the
    same way angles.py builds it for the ad-angle feedback flow.

    attachment_path: Supabase Storage path for an image the user attached to
    their latest feedback message (e.g. "make the logo look like this"), if
    any — passed to the editor agent as a second reference image alongside
    the current image.
    """
    if not has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="Image generation requires OPENAI_API_KEY to be configured.",
        )

    try:
        with ExitStack() as stack:
            current_image_path = stack.enter_context(
                download_to_temp_file(current_image.file_path)
            )
            attachment_local_path = (
                stack.enter_context(download_to_temp_file(attachment_path))
                if attachment_path
                else None
            )
            return revise_ad_image(
                current_image_path=current_image_path,
                header_text=current_image.header_text,
                additional_info=current_image.additional_info or "",
                chat_history=chat_history,
                attachment_path=attachment_local_path,
            )
    except Exception as exc:
        raise UpstreamServiceError(
            "Image generation",
            "Couldn't revise the image. Please try again.",
            internal=str(exc),
        ) from exc
