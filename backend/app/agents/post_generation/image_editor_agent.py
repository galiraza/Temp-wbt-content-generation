"""Editor Agent for post/reel branded images (revision from chat feedback).

Mirrors app.agents.logo.editor_agent's off-topic-guardrail semantics, with
one deliberate difference: the revision-prompt-writing step uses THIS
module's Claude client (client.py) via a rendered-history-string template
(same convention as feedback_agent.py), not OpenAI - matching how every
other text/reasoning step in post_generation works. Only the final pixel
generation goes through OpenAI (image_client.py), same split as
headline_mood_agent/logo_color_agent/final_image_agent.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.agents.post_generation.client import structured_llm
from app.agents.post_generation.image_client import IMAGE_MODEL, get_client
from app.agents.post_generation.prompts.image_editor_prompts import (
    REVISION_PROMPT_SYSTEM_PROMPT,
    REVISION_PROMPT_USER_PROMPT,
)

_REVISION_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVISION_PROMPT_SYSTEM_PROMPT), ("user", REVISION_PROMPT_USER_PROMPT)]
)


class _RevisionPromptOut(BaseModel):
    is_relevant: bool = Field(
        description="True if the user's latest message is feedback about editing THIS "
        "specific image (its headline/subheadline text, logo, hero photo, CTA, colors, "
        "layout, background, etc.). False for anything else: small talk, questions "
        "unrelated to this image, or requests outside the scope of editing it."
    )
    reply_message: str = Field(
        description="Only used when is_relevant is False: a short, friendly one-sentence "
        "chatbot reply explaining you're only here to help edit this image, so the user "
        "knows to ask again with real feedback. Leave this empty when is_relevant is True."
    )
    prompt: str = Field(
        description="Only used when is_relevant is True: the image-edit instruction prompt "
        "for the image model. Leave this empty when is_relevant is False."
    )


def _history_block(chat_history: List[dict]) -> str:
    """Every turn before the latest one, rendered as plain prose - the
    latest message is passed separately (see build_revision_prompt)."""
    earlier = chat_history[:-1]
    if not earlier:
        return "(nothing yet, this is the first message)"
    lines = []
    for entry in earlier:
        who = "User" if entry.get("role") == "user" else "You"
        lines.append(f"{who}: {entry.get('content', '')}")
    return "\n\n".join(lines)


def build_revision_prompt(
    chat_history: List[dict],
    has_attachment: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """chat_history: list of {"role": "user"|"assistant", "content": str},
    oldest first, ending with the latest user feedback.

    Returns a (prompt, off_topic_reply) tuple. off_topic_reply is None when
    the feedback was actually about editing this image and a revision prompt
    was produced; otherwise prompt is None and off_topic_reply holds a short
    chatbot reply to show instead.
    """
    latest_message = chat_history[-1]["content"] if chat_history else ""
    if has_attachment:
        latest_message += (
            "\n\n[The user attached an image to this message - the SECOND input image the "
            "image model will receive, after the current image. Their feedback text above "
            "explains what to do with it - write the revision prompt so it references this "
            "attached image explicitly and tells the image model exactly how to use it, per "
            "that description.]"
        )

    prompt_value = _REVISION_PROMPT.invoke(
        {"chat_history": _history_block(chat_history), "latest_message": latest_message}
    )
    result = structured_llm(_RevisionPromptOut, label="post-image-revision").invoke(prompt_value)
    if not result.is_relevant:
        return None, result.reply_message
    return result.prompt, None


def revise_post_or_reel_image(
    current_image_path: Path,
    chat_history: List[dict],
    attachment_path: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Revises an existing generated post/reel image based on chat feedback.
    chat_history must end with the latest user feedback turn.

    Returns a (b64_json, off_topic_reply) tuple, mirroring
    revise_logo_image() in app.agents.logo.editor_agent. off_topic_reply is
    None when the feedback was actually about editing this image and it was
    revised (b64_json holds the new PNG data); otherwise b64_json is None
    and off_topic_reply holds a short chatbot reply to show instead.
    """
    prompt, off_topic_reply = build_revision_prompt(
        chat_history, has_attachment=attachment_path is not None
    )
    if prompt is None:
        return None, off_topic_reply

    client = get_client()
    with open(current_image_path, "rb") as current_file:
        files = [current_file]
        attachment_file = open(attachment_path, "rb") if attachment_path else None
        if attachment_file is not None:
            files.append(attachment_file)
        try:
            result = client.images.edit(
                model=IMAGE_MODEL,
                image=files,
                prompt=prompt,
                size="1024x1024",
            )
        finally:
            if attachment_file is not None:
                attachment_file.close()

    return result.data[0].b64_json, None
