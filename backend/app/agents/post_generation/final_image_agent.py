"""Final branded post-image agent: composites the client's logo and a
matched hero photo into one finished graphic, using a randomly-picked
layout variant from the shared variant library (app.models.VariantLibrary).

Ties together logo_color_agent (brand palette), headline_mood_agent
(headline/subheadline/mood split), final_image_prompt.py (the template),
and image_canvas.fit_to_canvas (exact 1080x1350 output, no stretching -
see that module for why requesting "1088x1360" from images.edit() makes
this a trivial uniform downscale rather than an outpaint).

Does NOT run the classical-CV stretch QA (image_qa_agent) yet - that's a
deliberate, separate follow-up, not wired into this first pass.
"""

import base64
import random
from pathlib import Path
from typing import List

from app import models
from app.agents.post_generation.headline_mood_agent import extract_headline_mood
from app.agents.post_generation.image_client import IMAGE_MODEL, get_client
from app.agents.post_generation.logo_color_agent import extract_logo_colors
from app.agents.post_generation.prompts.final_image_prompt import (
    build_final_image_prompt,
    substitute_variant_colors,
)
from app.errors import ServiceNotConfiguredError, UpstreamServiceError
from app.services.image_canvas import EDIT_REQUEST_SIZE, fit_to_canvas

VARIANT_KIND = "post"


def generate_final_image(
    *,
    logo_path: Path,
    hero_photo_path: Path,
    title: str,
    industry: str,
    website_url: str,
    variant_rows: List[models.VariantLibrary],
) -> bytes:
    """Returns finished PNG bytes at exactly 1080x1350.

    title: a post's title, or (for a reel) its first on-screen line used the
    same way - see final_image_service usage.
    """
    if not variant_rows:
        raise ServiceNotConfiguredError(
            "Final image generation",
            internal=f"no VariantLibrary rows with kind={VARIANT_KIND!r}",
        )

    colors = extract_logo_colors(logo_path)
    headline_mood = extract_headline_mood(title, industry)
    variant = random.choice(variant_rows)
    layout_block = substitute_variant_colors(variant.layout_block, colors)

    prompt = build_final_image_prompt(
        primary_hex=colors["primary_hex"],
        accent_hex=colors["accent_hex"],
        bg_hex=colors["bg_hex"],
        neutral_hex=colors["neutral_hex"],
        headline=headline_mood["headline"],
        subheadline=headline_mood["subheadline"],
        mood=headline_mood["mood"],
        variant=variant.letter,
        layout_block=layout_block,
        industry=industry or "Not provided",
        cta_text=website_url or "",
    )

    client = get_client()
    with open(logo_path, "rb") as logo_file, open(hero_photo_path, "rb") as photo_file:
        try:
            result = client.images.edit(
                model=IMAGE_MODEL,
                image=[logo_file, photo_file],
                prompt=prompt,
                size=EDIT_REQUEST_SIZE,
            )
        except Exception as exc:
            raise UpstreamServiceError(
                "Final image generation",
                "Couldn't generate the final image. Please try again.",
                internal=f"{type(exc).__name__}: {exc}",
            ) from exc

    raw_bytes = base64.b64decode(result.data[0].b64_json)
    return fit_to_canvas(raw_bytes)
