"""Generator Agent — produces the 3 initial logo images for a request.

Two entry points, matching the module's two request types:
- generate_logo_concepts: "from scratch" — no existing logo, so 3 independent
  client.images.generate() calls (text-to-image) against OpenAI, each nudged
  toward a different concept direction (see prompts/generation_prompt.py) so
  the 3 results read as distinct ideas rather than near-duplicates.
- generate_logo_edits: "from previous logo" — an existing logo is uploaded
  and edited via OpenAI's images.edit() (gpt-image-2) into 3 variations (see
  prompts/edit_prompt.py).
"""

from pathlib import Path
from typing import List

from app.agents.logo.client import IMAGE_MODEL, get_client
from app.agents.logo.prompts.edit_prompt import build_edit_prompt
from app.agents.logo.prompts.generation_prompt import build_generation_prompt

_DEFAULT_SIZE = "1024x1024"
_CONCEPT_COUNT = 3


def generate_logo_concepts(
    company_name: str,
    industry: str,
    style_keywords: str,
    suggestion: str,
    meeting_brief: str = "",
) -> List[str]:
    """Returns a list of 3 base64-encoded PNGs (b64_json), one per concept
    direction, generated from scratch with no input image.

    meeting_brief: concrete must-apply requirements distilled from a Fathom
    meeting transcript (see build_generation_prompt() docstring) — treated
    as mandatory, unlike style_keywords/suggestion which are inspiration.
    """
    client = get_client()
    results = []
    for i in range(_CONCEPT_COUNT):
        prompt = build_generation_prompt(
            company_name,
            industry,
            style_keywords,
            suggestion,
            concept_index=i,
            meeting_brief=meeting_brief,
        )
        result = client.images.generate(model=IMAGE_MODEL, prompt=prompt, size=_DEFAULT_SIZE)
        results.append(result.data[0].b64_json)
    return results


def generate_logo_edits(
    source_logo_path: Path, company_name: str, suggestion: str, meeting_brief: str = ""
) -> List[str]:
    """Returns a list of 3 base64-encoded images, one per variation
    direction, each an edit of the uploaded source logo via OpenAI's
    images.edit() (see module docstring).

    meeting_brief: condensed branding guidance extracted from a Fathom
    meeting transcript, when a fathom_url was given for this request.
    """
    client = get_client()
    results = []
    for i in range(_CONCEPT_COUNT):
        prompt = build_edit_prompt(
            company_name, suggestion, variation_index=i, meeting_brief=meeting_brief
        )
        with open(source_logo_path, "rb") as source_file:
            result = client.images.edit(
                model=IMAGE_MODEL,
                image=[source_file],
                prompt=prompt,
                size=_DEFAULT_SIZE,
            )
        results.append(result.data[0].b64_json)
    return results
