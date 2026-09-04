"""Logo color-extraction agent: analyzes the client's uploaded logo and
derives the 4-color brand palette used to build the final branded post
image (see prompts/logo_color_prompt.py and final_image_prompt.py).

Vision-based, so it uses OpenAI directly (langchain_openai), not this
module's usual Claude text client (see client.py) - the same pattern
already used for vision-based structured extraction in
app.agents.logo.editor_agent (build_revision_prompt's image content
blocks), just applied to a fresh single-turn call instead of a chat history.
"""

import base64
from pathlib import Path
from typing import Dict

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agents.post_generation.prompts.logo_color_prompt import LOGO_COLOR_USER_PROMPT
from app.config import has_openai_key
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

_MIME_TYPES_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class _LogoColorsOut(BaseModel):
    primary_hex: str
    accent_hex: str
    bg_hex: str
    neutral_hex: str


def _image_content_block(path: Path) -> dict:
    mime = _MIME_TYPES_BY_SUFFIX.get(path.suffix.lower(), "image/png")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def extract_logo_colors(logo_path: Path) -> Dict[str, str]:
    """Returns {"primary_hex", "accent_hex", "bg_hex", "neutral_hex"}, all
    6-digit hex strings."""
    if not has_openai_key():
        raise ServiceNotConfiguredError(
            "Logo color extraction", internal="OPENAI_API_KEY is unset"
        )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    structured = llm.with_structured_output(_LogoColorsOut)
    content = [
        {"type": "text", "text": LOGO_COLOR_USER_PROMPT},
        _image_content_block(logo_path),
    ]
    try:
        result = structured.invoke([("user", content)])
    except Exception as exc:
        raise UpstreamServiceError(
            "Logo color extraction",
            "Couldn't read the logo's colors. Please try again.",
            internal=f"{type(exc).__name__}: {exc}",
        ) from exc

    return {
        "primary_hex": result.primary_hex,
        "accent_hex": result.accent_hex,
        "bg_hex": result.bg_hex,
        "neutral_hex": result.neutral_hex,
    }
