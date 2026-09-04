"""Editor Agent (revision from chat feedback).

Mirrors the ad-angle feedback loop — turns chat history + latest feedback
into a revision prompt, then calls gpt-image-2 to edit the current image.
"""

from pathlib import Path
from typing import List, Optional, Tuple

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.meta_ads.image_generation.client import IMAGE_MODEL, get_client
from app.agents.meta_ads.image_generation.prompts.editor_prompts import (
    REVISION_PROMPT_SYSTEM_PROMPT,
    REVISION_PROMPT_USER_PROMPT,
)


class _RevisionPromptOut(BaseModel):
    is_relevant: bool = Field(
        description="True if the user's latest message is feedback about editing THIS "
        "specific ad image (its photo, logo, text, colors, layout, badges, CTA, etc.). False "
        "for anything else: small talk, questions unrelated to this image, or requests "
        "outside the scope of editing this image."
    )
    reply_message: str = Field(
        description="Only used when is_relevant is False: a short, friendly one-sentence "
        "chatbot reply explaining you're only here to help edit this ad image, so the user "
        "knows to ask again with real feedback. Leave this empty when is_relevant is True."
    )
    prompt: str = Field(
        description="Only used when is_relevant is True: the image-edit instruction prompt "
        "for the image model. Leave this empty when is_relevant is False."
    )


def build_revision_prompt(
    header_text: str,
    additional_info: str,
    chat_history: List[dict],
    has_attachment: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """chat_history: list of {"role": "user"|"assistant", "content": str},
    oldest first, ending with the latest user feedback. Mirrors
    regenerate_angle_with_feedback() in ad_angle_agent.py.

    Returns a (prompt, off_topic_reply) tuple. off_topic_reply is None when
    the feedback was actually about editing this image and a revision prompt
    was produced; otherwise prompt is None and off_topic_reply holds a short
    chatbot reply to show instead.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(_RevisionPromptOut)

    user_prompt = REVISION_PROMPT_USER_PROMPT.format(
        header_text=header_text, additional_info=additional_info or "None"
    )
    if has_attachment:
        user_prompt += (
            "\n\nThe user's latest feedback message has an image attached to it (the SECOND "
            "input image the image model will receive, after the current ad image). Their "
            "feedback text explains what to do with it (e.g. use it as the new logo, use it as "
            "the new photo, or match its color/style for some element) - write the revision "
            "prompt so it references this attached image explicitly and tells the image model "
            "exactly how to use it, per that description."
        )

    messages = [
        ("system", REVISION_PROMPT_SYSTEM_PROMPT),
        ("user", user_prompt),
    ]
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append((role, msg["content"]))

    result = structured_llm.invoke(messages)
    if not result.is_relevant:
        return None, result.reply_message
    return result.prompt, None


def revise_ad_image(
    current_image_path: Path,
    header_text: str,
    additional_info: str,
    chat_history: List[dict],
    attachment_path: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Revises an existing generated image based on chat feedback.
    chat_history must end with the latest user feedback turn.

    attachment_path: an image the user attached to their latest feedback
    message (e.g. "use this as the new logo") - sent as a second input image
    alongside the current image when present.

    Returns a (b64_json, off_topic_reply) tuple, mirroring
    regenerate_angle_with_feedback() in ad_angle_agent.py. off_topic_reply is
    None when the feedback was actually about editing this image and it was
    revised (b64_json holds the new PNG data); otherwise b64_json is None
    and off_topic_reply holds a short chatbot reply to show instead.
    """
    prompt, off_topic_reply = build_revision_prompt(
        header_text, additional_info, chat_history, has_attachment=attachment_path is not None
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
