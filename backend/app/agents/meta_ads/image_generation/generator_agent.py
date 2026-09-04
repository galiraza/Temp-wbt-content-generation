"""Agent — Generator Agent.

Role: Expert Brand-Graphics Editor.

A single gpt-image-2 images.edit() call, given the reference ad, the new
logo, and one or more new photos, plus header/subtitle text, instructed
(via replication_prompt.py) to replicate the reference EXACTLY and swap in
only those elements. No dynamic prompt-building step, no pixel compositing
— this mirrors the approach already proven out in the social-media project
before its own DNA-extraction rewrite.

Some reference templates have multiple distinct photo slots (e.g. one
large primary photo plus several smaller supporting photos in a grid) —
passing only one real photo left the AI to invent content for the rest
(observed directly), so ALL of the company's uploaded photos are sent, and
the prompt is told exactly how many there are so it knows to use every one
rather than inventing anything.

Two pixel-exact compositing architectures for the logo were tried and
rejected (see replication_prompt.py's module docstring for why): the logo
is fully AI-drawn here, same as the photo and header — not pixel-perfect,
but without the seam/reflow failure modes those attempts ran into.

Reference image, logo, and at least one photo are all required — the
caller (angle_image_service.py) validates this before calling
generate_ad_image, since there is nothing to replicate onto without a
reference, and no approach in this pipeline generates a design from
scratch.
"""

from pathlib import Path
from typing import List

from app.agents.meta_ads.image_generation.client import IMAGE_MODEL, get_client
from app.agents.meta_ads.image_generation.prompts.replication_prompt import (
    REPLICATION_PROMPT_TEMPLATE,
)

_DEFAULT_SIZE = "1024x1024"

_BOTH_INSTRUCTION = (
    'This reference has a bold headline line plus a smaller subtitle line beneath it. Replace '
    'the headline line with EXACTLY this text, word for word:\n"""\n{header_text}\n"""\n'
    'Replace the subtitle line with EXACTLY this text, word for word:\n"""\n{additional_info}\n"""\n'
    "Both lines are present - no reflow needed. Keep the same size relationship between them as "
    "the reference has (headline bigger/bolder, subtitle smaller)."
)
_HEADER_ONLY_INSTRUCTION = (
    'Replace the bold headline line with EXACTLY this text, word for word:\n"""\n{header_text}\n"""\n'
    "No new subtitle text was given. Completely remove the reference's own subtitle line (every "
    "word of it) and close up the gap it leaves - shift whatever sits below this area upward to "
    "sit directly under the headline, using a normal single-line gap rather than the original "
    "two-line gap. Do not invent a substitute subtitle and do not reuse the reference's own "
    "subtitle wording."
)
_SUBTITLE_ONLY_INSTRUCTION = (
    "No new headline text was given. Completely remove the reference's own bold headline line "
    '(every word of it). Replace the subtitle line with EXACTLY this text, word for word:\n"""\n'
    "{additional_info}\n\"\"\"\nMove that subtitle text up to occupy the headline's old position "
    "(it becomes the top and only line of this area now), closing up the gap the removed "
    "headline left."
)
_NEITHER_INSTRUCTION = (
    "No new headline or subtitle text was given. Completely remove the ENTIRE original header "
    "area - both the bold headline line AND the smaller subtitle line beneath it, every word of "
    "both, under any circumstance. Then close up the empty gap this leaves: shift everything "
    "that sat below this area upward to start where the area itself used to start, using the "
    "same gap/spacing the reference shows between its OTHER adjacent elements. Do not leave a "
    "large empty blank space - the area's height should effectively disappear from the layout."
)

_PHOTO_SINGLE_INSTRUCTION = (
    "You were given exactly ONE new photo (the last input image). Identify the single "
    "photographic area in the reference (NOT the logo or background textures) and completely "
    "remove the original photo there; replace it with this new photo. The old photo must not be "
    "visible anywhere."
)
_PHOTO_MULTI_INSTRUCTION = (
    "You were given {photo_count} new photos, as the last {photo_count} input images, in that "
    "exact order. The reference has MULTIPLE distinct photo slots (e.g. one large primary photo "
    "plus several smaller supporting photos in a grid/collage) - do not treat it as having only "
    "one photo area. Match each new photo to a distinct slot, in the same order: the FIRST new "
    "photo goes in the largest/primary slot, and the REMAINING new photos go into the smaller "
    "supporting slots in the reference's own natural reading order (left-to-right, then "
    "top-to-bottom). Every one of the {photo_count} new photos must be used somewhere - do NOT "
    "invent, duplicate stock imagery, or hallucinate any photo content of your own for any slot. "
    "If the reference has MORE photo slots than {photo_count}, reuse/repeat the given photos "
    "(cycling through them in order) to fill the remaining slots rather than inventing new photo "
    "content. If the reference has FEWER photo slots than {photo_count}, use only as many of the "
    "given photos as there are slots and ignore the rest. None of the reference's own original "
    "photos may remain visible in any slot."
)


def _build_photo_instruction(photo_count: int) -> str:
    """Branching in Python for the same reason as the header instruction:
    an explicit, unambiguous count ("you were given 4 photos, here's how to
    use all 4") removes the guesswork that let the model invent photo
    content for slots it wasn't given real images for (observed directly).
    """
    if photo_count <= 1:
        return _PHOTO_SINGLE_INSTRUCTION
    return _PHOTO_MULTI_INSTRUCTION.format(photo_count=photo_count)


def _build_header_instruction(header_text: str, additional_info: str) -> str:
    """Branching this in Python rather than leaving the model to infer intent
    from empty quoted strings is far more reliable (observed directly: the
    model kept the reference's own header/subtitle alive even when given
    explicit "leave it blank" wording next to an empty string) — an
    unambiguous, distinct instruction for each of the four combinations
    removes that guesswork. header_text drives the bold headline line;
    additional_info drives the smaller subtitle/description line beneath
    it — these are two independent lines, not one merged block (observed
    directly: treating them as one block silently dropped additional_info
    whenever it was supplied alongside a header).
    """
    has_header = bool(header_text and header_text.strip())
    has_subtitle = bool(additional_info and additional_info.strip())

    if has_header and has_subtitle:
        return _BOTH_INSTRUCTION.format(header_text=header_text, additional_info=additional_info)
    if has_header:
        return _HEADER_ONLY_INSTRUCTION.format(header_text=header_text)
    if has_subtitle:
        return _SUBTITLE_ONLY_INSTRUCTION.format(additional_info=additional_info)
    return _NEITHER_INSTRUCTION


def generate_ad_image(
    header_text: str,
    additional_info: str,
    logo_path: Path,
    photo_paths: List[Path],
    reference_path: Path,
) -> str:
    """Returns base64-encoded PNG data (b64_json) for one ad image: reference
    + logo + photo(s) (in that exact order, matching the order named in the
    prompt) + header/subtitle text -> gpt-image-2 replicates the reference,
    swapping logo/photo(s)/header/subtitle.
    """
    prompt = REPLICATION_PROMPT_TEMPLATE.format(
        header_instruction=_build_header_instruction(header_text, additional_info),
        photo_instruction=_build_photo_instruction(len(photo_paths)),
    )

    client = get_client()
    files = [open(reference_path, "rb"), open(logo_path, "rb")] + [
        open(p, "rb") for p in photo_paths
    ]
    try:
        result = client.images.edit(
            model=IMAGE_MODEL, image=files, prompt=prompt, size=_DEFAULT_SIZE
        )
    finally:
        for f in files:
            f.close()

    return result.data[0].b64_json
