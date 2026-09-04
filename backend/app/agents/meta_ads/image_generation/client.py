"""Shared OpenAI client accessor for the image generation team's agents."""

import base64
from pathlib import Path
from typing import Optional

from openai import OpenAI

from app.config import OPENAI_API_KEY

IMAGE_MODEL = "gpt-image-2"
# gpt-4o-mini was inconsistent about left/right placement of elements (would
# sometimes contradict itself within the same response); gpt-4o's stronger
# spatial reasoning is worth the extra cost/latency for this analysis step.
VISION_MODEL = "gpt-4o"

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def image_to_data_url(path: Path) -> str:
    """Base64 data-URL for a local image file, for vision-model inputs."""
    ext = path.suffix.lstrip(".").lower() or "png"
    mime = "jpeg" if ext == "jpg" else ext
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"
