"""Editor Agent (revision from chat feedback).

Mirrors app.agents.meta_ads.image_generation.editor_agent — turns chat
history + latest feedback into a revision prompt, then calls gpt-image-2 to
edit the current logo image.
"""

import base64
from contextlib import ExitStack
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.logo.client import IMAGE_MODEL, get_client
from app.agents.logo.prompts.editor_prompts import (
    REVISION_PROMPT_SYSTEM_PROMPT,
    REVISION_PROMPT_USER_PROMPT,
)

_MIME_TYPES_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _image_content_block(path: Path) -> dict:
    """A vision input block for a LangChain multimodal message, so the
    prompt-writing LLM can look at the image directly instead of only
    reading a text description of it.
    """
    mime = _MIME_TYPES_BY_SUFFIX.get(path.suffix.lower(), "image/png")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


class _RevisionPromptOut(BaseModel):
    is_relevant: bool = Field(
        description="True if the user's latest message is feedback about editing THIS "
        "specific logo (its colors, typography, icon/symbol, layout, wording, style, etc.). "
        "False for anything else: small talk, questions unrelated to this logo, or requests "
        "outside the scope of editing this logo."
    )
    reply_message: str = Field(
        description="Only used when is_relevant is False: a short, friendly one-sentence "
        "chatbot reply explaining you're only here to help edit this logo, so the user knows "
        "to ask again with real feedback. Leave this empty when is_relevant is True."
    )
    prompt: str = Field(
        description="Only used when is_relevant is True: the image-edit instruction prompt "
        "for the image model. Leave this empty when is_relevant is False."
    )


def build_revision_prompt(
    chat_history: List[dict],
    has_attachment: bool,
    current_image_path: Optional[Path] = None,
    original_reference_path: Optional[Path] = None,
    attachment_path: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """chat_history: list of {"role": "user"|"assistant", "content": str},
    oldest first, ending with the latest user feedback.

    current_image_path / original_reference_path / attachment_path: when
    given, the actual images are sent to this LLM as vision input (not just
    described in text) so it can ground the revision prompt in what it
    actually sees - e.g. the precise shape of an icon in the originally
    uploaded logo the feedback is asking to match.

    Returns a (prompt, off_topic_reply) tuple. off_topic_reply is None when
    the feedback was actually about editing this logo and a revision prompt
    was produced; otherwise prompt is None and off_topic_reply holds a short
    chatbot reply to show instead.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    structured_llm = llm.with_structured_output(_RevisionPromptOut)

    user_prompt = REVISION_PROMPT_USER_PROMPT
    image_blocks = []
    if current_image_path is not None:
        user_prompt += (
            "\n\nThe CURRENT logo, exactly as it looks right now, is attached below as an "
            "image so you can see it directly."
        )
        image_blocks.append(_image_content_block(current_image_path))
    if original_reference_path is not None:
        user_prompt += (
            "\n\nThe ORIGINAL logo the client uploaded, before any AI edits, is also attached "
            "below as an image. Whenever the feedback refers back to something from that "
            "original upload (an icon's exact shape, a wire/line's path, a color, etc.), look "
            "at this image closely and describe its precise geometry - curves, angles, "
            "thickness, endpoints, how it connects to other elements - in the instruction you "
            "write. Do not approximate or invent a generic version of it."
        )
        image_blocks.append(_image_content_block(original_reference_path))
    if has_attachment and attachment_path is not None:
        user_prompt += (
            "\n\nThe user's latest feedback message has an image attached to it too, also "
            "attached below (and the LAST extra input image the image model will receive). "
            "Their feedback text explains what to do with it (e.g. match its color/style for "
            "some element) - look at it directly, write the revision prompt so it references "
            "this attached image explicitly, and describe precisely what you see rather than "
            "a generic guess."
        )
        image_blocks.append(_image_content_block(attachment_path))

    human_content = [{"type": "text", "text": user_prompt}] + image_blocks

    messages = [
        ("system", REVISION_PROMPT_SYSTEM_PROMPT),
        ("user", human_content),
    ]
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append((role, msg["content"]))

    result = structured_llm.invoke(messages)
    if not result.is_relevant:
        return None, result.reply_message
    return result.prompt, None


def revise_logo_image(
    current_image_path: Path,
    chat_history: List[dict],
    attachment_path: Optional[Path] = None,
    original_reference_path: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Revises an existing generated logo based on chat feedback. chat_history
    must end with the latest user feedback turn.

    attachment_path: an image the user attached to their latest feedback
    message - sent as an extra input image alongside the current logo when
    present.

    original_reference_path: for "from previous logo" requests, the
    originally uploaded reference logo - always passed (not just when the
    user re-attaches it in a message) so feedback referring back to it has
    an actual image to ground against, both when writing the revision
    prompt and in the image-edit call itself.

    Returns a (b64_json, off_topic_reply) tuple, mirroring revise_ad_image()
    in the ad-angle editor agent. off_topic_reply is None when the feedback
    was actually about editing this logo and it was revised (b64_json holds
    the new PNG data); otherwise b64_json is None and off_topic_reply holds a
    short chatbot reply to show instead.
    """
    prompt, off_topic_reply = build_revision_prompt(
        chat_history,
        has_attachment=attachment_path is not None,
        current_image_path=current_image_path,
        original_reference_path=original_reference_path,
        attachment_path=attachment_path,
    )
    if prompt is None:
        return None, off_topic_reply

    client = get_client()
    with ExitStack() as stack:
        files = [stack.enter_context(open(current_image_path, "rb"))]
        if original_reference_path is not None:
            files.append(stack.enter_context(open(original_reference_path, "rb")))
        if attachment_path is not None:
            files.append(stack.enter_context(open(attachment_path, "rb")))
        result = client.images.edit(
            model=IMAGE_MODEL,
            image=files,
            prompt=prompt,
            size="1024x1024",
        )

    return result.data[0].b64_json, None
