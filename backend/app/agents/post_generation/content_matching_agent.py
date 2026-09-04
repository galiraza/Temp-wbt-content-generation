"""Content-matching agent: picks which of a request's hero images best fits
one post/reel's title+caption, without exceeding the pool's usage limit.
See content_matching_prompt.py for the exact selection rules ported from n8n
(the usage-limit math, eligibility, and scoring steps all happen inside the
model call - this module only builds the candidate list and resolves the
model's answer back to a real HeroImage row).

In n8n this read/wrote a Data Table for usage; here the caller passes in the
request's own HeroImage rows (already carrying their current usage) and is
responsible for incrementing the winner's usage and committing afterward -
this function never mutates anything itself.
"""

import json
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app import models
from app.agents.post_generation.client import structured_llm
from app.agents.post_generation.prompts.content_matching_prompt import (
    CONTENT_MATCHING_USER_PROMPT,
)
from app.config import has_anthropic_key

_CONTENT_MATCHING_PROMPT = ChatPromptTemplate.from_messages([("user", CONTENT_MATCHING_USER_PROMPT)])


class _ContentMatchOut(BaseModel):
    image_name: str
    usage: int


def _image_name(hero_image: models.HeroImage) -> str:
    return f"Hero Image {hero_image.slot}"


def match_hero_image(
    hero_images: List[models.HeroImage], title: str, caption: str
) -> Optional[models.HeroImage]:
    """Returns the picked HeroImage row, or None if the pool is empty.

    Falls back to the least-used image (never a fixed slot) if the model's
    answer doesn't resolve to a real candidate - the prompt is strict about
    the output format, but a hallucinated name should degrade to "still a
    sensible pick", not a crash.
    """
    if not hero_images:
        return None

    if not has_anthropic_key():
        # No ANTHROPIC_API_KEY: fall back to the least-used image rather than
        # failing - a simple but sensible pick, same "degrade, don't crash"
        # convention as post_generation_service's stub content path.
        return min(hero_images, key=lambda h: h.usage)

    candidates = [
        {"image_name": _image_name(h), "summary": h.summary, "usage": h.usage} for h in hero_images
    ]
    prompt_value = _CONTENT_MATCHING_PROMPT.invoke(
        {
            "candidates_json": json.dumps(candidates),
            "image_video_title": title,
            "post_caption": caption,
        }
    )
    result = structured_llm(_ContentMatchOut, label="content-matching").invoke(prompt_value)

    by_name = {_image_name(h): h for h in hero_images}
    return by_name.get(result.image_name) or min(hero_images, key=lambda h: h.usage)
