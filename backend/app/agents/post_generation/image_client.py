"""Shared OpenAI image client for this module's hero-image generation.

Separate from client.py (which is the Anthropic text-model client for the
copy agents) - same split as app.agents.logo.client /
app.agents.meta_ads.image_generation.client, each module keeping its own
small OpenAI accessor rather than sharing one across module boundaries.
"""

from typing import Optional

from openai import OpenAI

from app.config import OPENAI_API_KEY

IMAGE_MODEL = "gpt-image-2"

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client
