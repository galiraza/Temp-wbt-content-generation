"""The copy chat board agent, shared by posts and reviews.

Returns a PARTIAL revision: only the fields the user asked about. That is the
whole point — re-emitting the whole item every turn silently rewrites the caption
when someone only wanted a different hashtag.

Every field on the schemas below is Optional, and that is load-bearing: an unset
field means "leave this alone". LangChain's with_structured_output does the
validation, so nothing here parses prose and guesses.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate

from app.agents.post_generation.client import structured_llm
from app.agents.post_generation.parsers import normalise_hashtags
from app.agents.post_generation.prompts.feedback_prompts import (
    FEEDBACK_USER_PROMPT,
    POST_FEEDBACK_SYSTEM_PROMPT,
    REEL_FEEDBACK_SYSTEM_PROMPT,
    REVIEW_FEEDBACK_SYSTEM_PROMPT,
)


class PostRevision(BaseModel):
    """A proposed change to one post. Unset fields are left alone."""

    is_revision: bool = Field(
        description="True if this reply carries changes to apply, false if it is just an answer."
    )
    reply: Optional[str] = Field(
        default=None,
        description="What to say to the user. Required when is_revision is false.",
    )
    title: Optional[str] = Field(
        default=None, description="Only if the title was asked to change."
    )
    caption: Optional[str] = Field(
        default=None,
        description="Only if the caption was asked to change. Includes the CTA block.",
    )
    hashtags: Optional[List[str]] = Field(
        default=None, description="Only if the hashtags were asked to change."
    )


class ReelRevision(BaseModel):
    """A proposed change to one reel. Unset fields are left alone.

    No title field: a reel does not have one.
    """

    is_revision: bool = Field(
        description="True if this reply carries changes to apply, false if it is just an answer."
    )
    reply: Optional[str] = Field(
        default=None,
        description="What to say to the user. Required when is_revision is false.",
    )
    reel_text: Optional[str] = Field(
        default=None,
        description="Only if the on-screen script was asked to change. Keep the line breaks.",
    )
    caption: Optional[str] = Field(
        default=None,
        description="Only if the caption was asked to change. Includes the CTA block.",
    )
    hashtags: Optional[List[str]] = Field(
        default=None, description="Only if the hashtags were asked to change."
    )


class ReviewRevision(BaseModel):
    """A proposed change to one review post. Unset fields are left alone."""

    is_revision: bool = Field(
        description="True if this reply carries changes to apply, false if it is just an answer."
    )
    reply: Optional[str] = Field(
        default=None,
        description="What to say to the user. Required when is_revision is false.",
    )
    title: Optional[str] = Field(
        default=None, description="Only if the headline was asked to change."
    )
    name: Optional[str] = Field(
        default=None, description="Only to correct a mis-transcribed reviewer name."
    )
    review: Optional[str] = Field(
        default=None,
        description="Only to correct a transcription error. Never a rewrite of the customer's words.",
    )
    caption: Optional[str] = Field(
        default=None, description="Only if the caption was asked to change."
    )
    hashtags: Optional[List[str]] = Field(
        default=None, description="Only if the hashtags were asked to change."
    )


_POST_FIELDS = ("title", "caption", "hashtags")
_REEL_FIELDS = ("reel_text", "caption", "hashtags")
_REVIEW_FIELDS = ("title", "name", "review", "caption", "hashtags")

_POST_PROMPT = ChatPromptTemplate.from_messages(
    [("system", POST_FEEDBACK_SYSTEM_PROMPT), ("user", FEEDBACK_USER_PROMPT)]
)
_REEL_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REEL_FEEDBACK_SYSTEM_PROMPT), ("user", FEEDBACK_USER_PROMPT)]
)
_REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVIEW_FEEDBACK_SYSTEM_PROMPT), ("user", FEEDBACK_USER_PROMPT)]
)


def post_feedback_chain(post_id: int):
    """prompt | llm -> PostRevision. Only the changed fields come back set."""
    return _POST_PROMPT | structured_llm(PostRevision, label=f"post-feedback-{post_id}")


def reel_feedback_chain(reel_id: int):
    """prompt | llm -> ReelRevision."""
    return _REEL_PROMPT | structured_llm(ReelRevision, label=f"reel-feedback-{reel_id}")


def review_feedback_chain(review_id: int):
    """prompt | llm -> ReviewRevision."""
    return _REVIEW_PROMPT | structured_llm(
        ReviewRevision, label=f"review-feedback-{review_id}"
    )


def _history_block(chat_history: List[Dict]) -> str:
    if not chat_history:
        return "(nothing yet, this is the first message)"
    lines = []
    for entry in chat_history:
        who = "User" if entry.get("role") == "user" else "You"
        lines.append(f"{who}: {entry.get('content', '')}")
    return "\n\n".join(lines)


def _post_block(item) -> str:
    tags = " ".join(item.hashtag_list) or "(none)"
    return f"Title: {item.title}\n\nCaption:\n{item.caption}\n\nHashtags: {tags}"


def _reel_block(item) -> str:
    tags = " ".join(item.hashtag_list) or "(none)"
    return (
        f"On-screen text (one line per card):\n{item.reel_text}\n\n"
        f"Caption:\n{item.caption}\n\nHashtags: {tags}"
    )


def _review_block(item) -> str:
    tags = " ".join(item.hashtag_list) or "(none)"
    return (
        f"Headline: {item.title}\n\n"
        f"Reviewer: {item.name}\n\n"
        f"Review (the customer's own words, do not rewrite):\n{item.review}\n\n"
        f"Caption:\n{item.caption}\n\n"
        f"Hashtags: {tags}"
    )


def request_revision(request, item, kind: str, chat_history: List[Dict], message: str) -> Dict:
    """Asks for a revision of one item.

    Returns {"is_revision": bool, "reply": str, "changes": {field: value}}.
    `changes` holds only the fields the model chose to return, already normalised,
    and is empty when the reply is conversational.
    """
    if kind == "reel":
        fields, block, chain = _REEL_FIELDS, _reel_block(item), reel_feedback_chain(item.id)
    elif kind == "review":
        fields, block, chain = _REVIEW_FIELDS, _review_block(item), review_feedback_chain(item.id)
    else:
        fields, block, chain = _POST_FIELDS, _post_block(item), post_feedback_chain(item.id)

    result = chain.invoke(
        {
            "company_name": request.company_name,
            "website_url": (request.website_url or "Not provided"),
            "phone": (request.phone or "Not provided"),
            "email": (request.email or "Not provided"),
            "item_block": block,
            "history": _history_block(chat_history),
            "message": message,
        }
    )

    changes: Dict = {}
    if result is not None and result.is_revision:
        for field in fields:
            value = getattr(result, field, None)
            if value is None:
                continue
            if field == "hashtags":
                cleaned = normalise_hashtags(value if isinstance(value, list) else [])
                if cleaned:
                    changes[field] = cleaned
            elif isinstance(value, str) and value.strip():
                changes[field] = value.strip()

    reply: Optional[str] = ((result.reply if result else None) or "").strip() or None
    if changes:
        # A revision with no covering note still needs something to render in the
        # thread above the diff.
        reply = reply or "Here's a revised version, approve it to apply."
    elif not reply:
        reply = "I couldn't work out what to change there. Could you say it another way?"

    return {"is_revision": bool(changes), "reply": reply, "changes": changes}
