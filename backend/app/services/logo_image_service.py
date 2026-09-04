"""Business logic for logo image generation: generating the 3 initial
concepts/variations for a request, revising one from chat feedback, and
converting DB rows to API schemas. Mirrors angle_image_service.py.
"""

import json
from contextlib import ExitStack
from typing import List, Optional, Tuple

from fastapi import HTTPException

from app import models, schemas
from app.agents import (
    extract_logo_brief,
    extract_usp_style_keywords,
    generate_ai_creative_direction,
    generate_logo_concepts,
    generate_logo_edits,
    revise_logo_image,
)
from app.config import has_openai_key
from app.errors import UpstreamServiceError
from app.services.fathom_service import fetch_transcript
from app.storage import download_to_temp_file


def to_out(row: models.LogoImage) -> schemas.LogoImageOut:
    return schemas.LogoImageOut.model_validate(row)


def message_to_out(row: models.LogoImageChatMessage) -> schemas.LogoImageChatMessageOut:
    candidate_image_path = None
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
            candidate_image_path = parsed.get("file_path")
        except (json.JSONDecodeError, AttributeError):
            pass
    return schemas.LogoImageChatMessageOut(
        id=row.id,
        logo_image_id=row.logo_image_id,
        role=row.role,
        content=row.content,
        candidate_image_path=candidate_image_path,
        attachment_path=row.attachment_path,
        created_at=row.created_at,
    )


def get_meeting_brief(fathom_url: Optional[str]) -> Tuple[Optional[str], str]:
    """Resolves a Fathom meeting URL into a short logo/branding brief, for use
    as generation context. Returns (raw_transcript, brief) — raw_transcript is
    stored on the request row, brief is what actually goes into the
    generation prompt. Both are empty/None if no URL was given or the lookup
    fails — generation proceeds without meeting context rather than failing
    the whole request over an unrelated integration being unavailable.
    """
    if not fathom_url:
        return None, ""
    transcript = fetch_transcript(fathom_url)
    if not transcript:
        return None, ""
    try:
        brief = extract_logo_brief(transcript)
    except Exception:
        brief = ""
    return transcript, brief


def generate_concepts_from_scratch(
    company_name: str, industry: str, usps: str, suggestion: str, meeting_brief: str = ""
) -> List[str]:
    """Returns 3 base64 PNGs (b64_json), one per concept direction.

    Synthesis recipe:
      - company_name + industry are the foundation.
      - usps (if given) are distilled into 3-4 style/personality keywords by
        extract_usp_style_keywords() rather than injected as raw business
        copy — inspiration only.
      - suggestion, if the user typed one, is used verbatim as a creative
        driver — inspiration only. Otherwise generate_ai_creative_direction()
        invents one from company_name/industry/style_keywords.
      - meeting_brief (from get_meeting_brief(), if a fathom_url was given):
        concrete must-apply requirements from the client meeting — treated as
        MANDATORY, not inspiration, and applied regardless of whether a
        suggestion was also typed (the two are compatible, not competing —
        a typed suggestion is usually just the same meeting decision
        restated).
    """
    if not has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="Logo generation requires OPENAI_API_KEY to be configured.",
        )
    try:
        style_keywords = extract_usp_style_keywords(usps) if usps and usps.strip() else ""
        direction = (
            suggestion.strip()
            if suggestion and suggestion.strip()
            else generate_ai_creative_direction(company_name, industry, style_keywords)
        )
        return generate_logo_concepts(
            company_name, industry, style_keywords, direction, meeting_brief=meeting_brief
        )
    except Exception as exc:
        raise UpstreamServiceError(
            "Logo generation",
            "Couldn't generate the logo. Please try again.",
            internal=str(exc),
        ) from exc


def generate_edits_from_previous(
    source_logo_path: str, company_name: str, suggestion: str, meeting_brief: str = ""
) -> List[str]:
    """Returns 3 base64 images, one per variation direction, each an edit of
    the uploaded source logo (downloaded from Storage for the duration of
    the call) — via OpenAI's images.edit() (see generator_agent.py).
    """
    if not has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="Logo generation requires OPENAI_API_KEY to be configured.",
        )
    try:
        with download_to_temp_file(source_logo_path) as local_path:
            return generate_logo_edits(
                local_path, company_name, suggestion or "", meeting_brief=meeting_brief
            )
    except Exception as exc:
        raise UpstreamServiceError(
            "Logo generation",
            "Couldn't generate the logo. Please try again.",
            internal=str(exc),
        ) from exc


def revise_image(
    current_image: models.LogoImage,
    chat_history: List[dict],
    attachment_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Returns a (b64_json, off_topic_reply) tuple for a revision request
    based on chat feedback — see revise_logo_image() in editor_agent.py for
    the off-topic-guardrail semantics.

    For "from previous logo" requests, the originally uploaded reference
    logo is always resolved and passed along too (not just a freshly
    attached image) — so feedback that refers back to it (e.g. "like the
    wire in the uploaded logo") has an actual image for the model to look
    at, instead of only the text description of it.
    """
    if not has_openai_key():
        raise HTTPException(
            status_code=503,
            detail="Logo generation requires OPENAI_API_KEY to be configured.",
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
            original_reference_path = (
                stack.enter_context(
                    download_to_temp_file(current_image.previous_request.logo_path)
                )
                if current_image.previous_request_id
                else None
            )
            return revise_logo_image(
                current_image_path=current_image_path,
                chat_history=chat_history,
                attachment_path=attachment_local_path,
                original_reference_path=original_reference_path,
            )
    except Exception as exc:
        raise UpstreamServiceError(
            "Logo generation",
            "Couldn't revise the logo. Please try again.",
            internal=str(exc),
        ) from exc
