"""Shared OpenAI client accessor for the logo generation agents."""

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
