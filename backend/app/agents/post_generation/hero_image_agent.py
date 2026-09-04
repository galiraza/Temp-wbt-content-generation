"""Hero-image generation: writes 12 image-generation prompts via
hero_image_prompt.py, then generates a real image for each.

Runs after content generation, not before: it uses the request's own
generated post titles as creative anchors (hero_image_prompt.py's "POST
TITLES" section), so post_manager.generate_posts() must have already
produced the request's Post rows. Uses OpenAI (gpt-image-2, text-to-image,
no reference image) rather than this module's usual Claude, since these are
meant to be independent real-world photos - the same provider every other
image-generation agent in this codebase already uses.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.agents.post_generation.client import structured_llm
from app.agents.post_generation.image_client import IMAGE_MODEL, get_client
from app.agents.post_generation.prompts.hero_image_prompt import HERO_IMAGE_PROMPT_USER_PROMPT
from app.config import has_anthropic_key, has_openai_key
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

HERO_IMAGE_COUNT = 12
_IMAGE_SIZE = "1024x1024"
# Each slot is an independent call (own prompt, no shared state), but firing all 12
# at once against an unconfirmed per-account rate limit is asking for 429s - 4 at a
# time still turns the dominant cost of this request (12 sequential ~20-70s calls,
# 8+ minutes observed in practice) into roughly a quarter of that.
_MAX_CONCURRENT_IMAGE_CALLS = 4

_HERO_IMAGE_PROMPT = ChatPromptTemplate.from_messages([("user", HERO_IMAGE_PROMPT_USER_PROMPT)])


class _HeroImagePromptsOut(BaseModel):
    prompts: List[str] = Field(..., min_length=HERO_IMAGE_COUNT, max_length=HERO_IMAGE_COUNT)


def _value(value, fallback: str = "Not provided") -> str:
    return (value or "").strip() or fallback


def _titles_block(request) -> str:
    titles = [p.title for p in sorted(request.posts, key=lambda p: p.post_number) if p.title]
    return "\n".join(f"- {t}" for t in titles) if titles else "Not provided"


def _stub_prompts(request) -> List[str]:
    """No ANTHROPIC_API_KEY: return obvious placeholder prompts instantly
    rather than failing, so the OpenAI image call (which has its own,
    independent key) can still be exercised. Same convention as
    post_generation_service._stub_posts."""
    industry = _value(request.industry, "the business's trade")
    return [
        f"[Stub prompt {i}] A hyper-realistic photograph representing {industry} for "
        f"{request.company_name}. Set ANTHROPIC_API_KEY to enable real prompt writing."
        for i in range(1, HERO_IMAGE_COUNT + 1)
    ]


def write_hero_image_prompts(request) -> List[str]:
    """Runs the prompt-builder step only: returns the 12 image-generation
    prompts without generating anything yet."""
    if not has_anthropic_key():
        return _stub_prompts(request)

    fields = {
        "company_name": request.company_name,
        "industry": _value(request.industry),
        "areas_covered": _value(request.areas_covered),
        "fixed_rules": _value(request.fixed_rules, "None"),
        "main_topic": _value(request.main_topic),
        "unique_selling_points": _value(request.unique_selling_points),
        "additional_notes": _value(request.additional_notes),
        "image_video_titles": _titles_block(request),
    }
    prompt_value = _HERO_IMAGE_PROMPT.invoke(fields)
    result = structured_llm(_HeroImagePromptsOut, label="hero-image-prompts").invoke(prompt_value)
    return result.prompts


def _generate_one(client, slot: int, prompt: str) -> Dict:
    try:
        response = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=_IMAGE_SIZE)
    except Exception as exc:
        raise UpstreamServiceError(
            "Hero image generation",
            "Couldn't generate the hero images. Please try again.",
            internal=f"slot {slot}: {type(exc).__name__}: {exc}",
        ) from exc
    return {"slot": slot, "summary": prompt, "b64": response.data[0].b64_json}


def generate_hero_images(request) -> List[Dict]:
    """Writes the 12 prompts, then generates a real image for each, up to
    _MAX_CONCURRENT_IMAGE_CALLS at a time.

    Returns a list of {"slot": int, "summary": str, "b64": str} dicts, one
    per hero image, ready for the caller to upload and store as HeroImage
    rows. `summary` is the prompt that produced the image - doubles as what
    the content-matching agent later reads to judge fit.
    """
    if not has_openai_key():
        raise ServiceNotConfiguredError(
            "Hero image generation", internal="OPENAI_API_KEY is unset"
        )

    prompts = write_hero_image_prompts(request)
    client = get_client()
    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_IMAGE_CALLS) as pool:
        futures = [
            pool.submit(_generate_one, client, slot, prompt)
            for slot, prompt in enumerate(prompts, start=1)
        ]
        # Indexed, not as_completed: keeps the return order = slot order, and a
        # failure surfaces via the first future that raises rather than whichever
        # happened to finish first.
        results = [f.result() for f in futures]
    return results
