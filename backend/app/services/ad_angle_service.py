"""Business logic shared across the ad-angle routers: converting DB rows to
API schemas, and calling the ad-angle agent (with a stub fallback when no
OPENAI_API_KEY is configured, so the app is usable without an LLM key).
"""

import json
import time
from typing import List, Optional, Tuple

from app import models, schemas
from app.agents import (
    generate_ad_angles,
    regenerate_angle_with_feedback,
    regenerate_single_angle,
)
from app.config import has_openai_key
from app.errors import UpstreamServiceError

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.5


def _with_retry(func, *args, **kwargs):
    """Retries a flaky LLM call before giving up — transient network/DNS blips
    reaching the OpenAI API have been observed directly in this environment,
    and succeed immediately on a retry (the call itself is not at fault).
    Only the last attempt's exception propagates, after _MAX_ATTEMPTS tries.
    """
    last_exc: Exception = RuntimeError("_with_retry called with zero attempts")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc


def to_out(row: models.AdAngleRequest) -> schemas.AdAngleRequestOut:
    return schemas.AdAngleRequestOut(
        id=row.id,
        company_name=row.company_name,
        offers=json.loads(row.offers) if row.offers else [],
        service_name=row.service_name,
        service_content=row.service_content,
        industry=json.loads(row.industry) if row.industry else [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def message_to_out(row: models.AngleChatMessage) -> schemas.ChatMessageOut:
    headline = None
    primary_text = None
    display_content = row.content
    if row.role == "assistant":
        try:
            parsed = json.loads(row.content)
            headline = parsed.get("headline")
            primary_text = parsed.get("primary_text")
            display_content = primary_text or row.content
        except (json.JSONDecodeError, AttributeError):
            pass
    return schemas.ChatMessageOut(
        id=row.id,
        angle_id=row.angle_id,
        role=row.role,
        content=display_content,
        headline=headline,
        primary_text=primary_text,
        created_at=row.created_at,
    )


def _stub_generate(service_name: str) -> List[Tuple[str, str]]:
    return [
        (
            f"{service_name}: Special Offer",
            f"[Stub angle {i + 1}] {service_name}: placeholder ad copy. "
            f"Set OPENAI_API_KEY to enable real generation.",
        )
        for i in range(6)
    ]


def generate_angles_for_request(request: models.AdAngleRequest) -> List[Tuple[str, str]]:
    """Stub angles are returned only when no OPENAI_API_KEY is configured at all —
    a genuine failure of the real call (a transient network/API error, etc.) raises
    an UpstreamServiceError instead of silently falling back to a stub. Swallowing real
    errors here previously made working features (e.g. off-topic feedback
    detection) look broken whenever a one-off API hiccup occurred, since the stub
    has none of that logic.
    """
    if not has_openai_key():
        return _stub_generate(request.service_name)
    try:
        return _with_retry(
            generate_ad_angles,
            company_name=request.company_name,
            industry=json.loads(request.industry) if request.industry else [],
            service_name=request.service_name,
            service_content=request.service_content,
            usps="",
            offers=json.loads(request.offers) if request.offers else [],
        )
    except Exception as exc:
        raise UpstreamServiceError(
            "Ad angle generation",
            "Couldn't generate ad angles right now. Please try again.",
            internal=str(exc),
        ) from exc


def regenerate_single(
    request: models.AdAngleRequest, headline: str, primary_text: str
) -> Tuple[str, str]:
    """See generate_angles_for_request's docstring for why real errors raise
    instead of silently falling back to a stub."""
    if not has_openai_key():
        return (headline, f"[Stub regenerated] {request.service_name}: placeholder ad copy.")
    try:
        return _with_retry(
            regenerate_single_angle,
            company_name=request.company_name,
            industry=json.loads(request.industry) if request.industry else [],
            service_name=request.service_name,
            service_content=request.service_content,
            usps="",
            offers=json.loads(request.offers) if request.offers else [],
            existing_headline=headline,
            existing_primary_text=primary_text,
        )
    except Exception as exc:
        raise UpstreamServiceError(
            "Ad angle generation",
            "Couldn't regenerate that angle. Please try again.",
            internal=str(exc),
        ) from exc


def regenerate_with_feedback(
    request: models.AdAngleRequest,
    current_headline: str,
    current_primary_text: str,
    chat_history: List[dict],
) -> Tuple[str, str, Optional[str]]:
    """Returns (headline, primary_text, off_topic_reply). off_topic_reply is None when the
    angle was actually revised; otherwise it holds a chatbot reply to show instead, and
    headline/primary_text come back unchanged.

    See generate_angles_for_request's docstring for why real errors raise instead
    of silently falling back to a stub.
    """
    if not has_openai_key():
        return (current_headline, f"[Stub feedback revision] {current_primary_text}", None)
    try:
        return _with_retry(
            regenerate_angle_with_feedback,
            company_name=request.company_name,
            industry=json.loads(request.industry) if request.industry else [],
            service_name=request.service_name,
            service_content=request.service_content,
            usps="",
            offers=json.loads(request.offers) if request.offers else [],
            current_headline=current_headline,
            current_primary_text=current_primary_text,
            chat_history=chat_history,
        )
    except Exception as exc:
        raise UpstreamServiceError(
            "Ad angle generation",
            "Couldn't apply that feedback. Please try again.",
            internal=str(exc),
        ) from exc
