"""Prompt text for the Generator Agent — editing an existing uploaded logo
into 3 refreshed variations, each nudged toward a different composition
type via VARIATION_DIRECTIVES so the 3 results are meaningfully distinct in
the same way the from-scratch flow's 3 concepts are — not just "more/less
changed" versions of one idea. Always lands on 1 text-only wordmark + 2
icon+text compositions overall (mirrors CONCEPT_DIRECTIVES in
generation_prompt.py), but WHICH slot is which depends on the uploaded
logo's own type — detected by the model itself by looking at the reference
image, not by us:
  - Slot 0 always mirrors the original's own type (icon+text stays
    icon+text, text-only stays text-only) — a faithful rebrand/redesign of
    the same structure, driven by the creative direction/meeting_brief.
  - Slot 1 is always icon+text, regardless of the original.
  - Slot 2 is the opposite of the original's type (text-only if the
    original had an icon, icon+text/badge if the original was text-only) —
    this is what keeps the overall mix at 1 text-only + 2 icon+text either
    way: original-has-icon → icon(0)+icon(1)+text(2); original-is-text →
    text(0)+icon(1)+icon(2).

Kept at quality-instruction parity with generation_prompt.py's
BASE_LOGO_PROMPT (no leaked text, no photorealism, no cliché stock icons) —
images.edit() is an image-EDIT call, not a from-scratch design model, so
without these explicit guardrails it drifts toward literal photo-editing
habits (rendering extra captions, softer/painterly shading, generic icon
clip-art) that a from-scratch text-to-image call doesn't have to be told to
avoid as forcefully.
"""

BASE_EDIT_PROMPT = """CRITICAL OUTPUT RULE: generate exactly ONE single logo design, full stop. \
Never a sheet, grid, moodboard, or collage of multiple variations, alternate layouts, icon-only \
versions, or size comparisons side by side. One design. Nothing else in the image.

You are an expert brand-identity designer refreshing an existing logo (the input image) for \
"{company_name}".
{suggestion_line}{meeting_brief_line}
Keep this an evolution of the original brand's overall visual identity — do not invent an \
unrelated new brand from scratch. If "Confirmed client requirements" are given above, apply \
every line exactly even where that means changing the original's business name/text, colors, \
icon, or styling — those changes were explicitly requested by the client (e.g. a confirmed \
rebrand or renamed division) and take priority over preserving the original look, including \
replacing the original name/text with a new one if the requirements say so. This is IN ADDITION \
to any "Creative direction requested" also given above, not instead of it — when both are \
present, apply both together; a concrete confirmed requirement (an exact color, icon, or name) \
must actually be visible in the result, not just referenced in spirit. If the two ever conflict \
on a specific concrete detail, the confirmed client requirements win, since the client explicitly \
approved those in a meeting.

The refreshed logo must:
- Be a SINGLE clean, professional, modern, top-quality standalone logo mark on a plain white or \
transparent background, legible at small sizes (favicon/app-icon scale) as well as large. No \
mockup, no background scene, no annotations or labels.
- The ONLY text allowed anywhere in the image is the business name itself, rendered once as part \
of the logo. Never add taglines, slogans, mottos, service lists, captions, or any other words — \
express creative direction through color, icon, and typography choices only, never as literal \
on-image text.
- Avoid photorealistic, painterly, or photo-editing-style rendering (soft shading, drop shadows, \
gradients meant to look "photographic") — this is a flat, crisp, vector-style brand mark, the \
same rendering quality as a logo drawn in vector design software, not a photo or illustration \
scene.
- Use precise geometry, even spacing, and properly centered/baseline-aligned typography — the \
kind of exacting alignment a professional designer would deliver, not a rough approximation.
- Reflect the brand tastefully; avoid cliché stock-icon combinations and generic clip-art \
rendering.

{variation_directive}

Reminder: output ONE logo only — not a set, not a comparison, not multiple options in one image."""

VARIATION_DIRECTIVES = [
    "Design direction for THIS version: first, look closely at the uploaded reference logo. If "
    "it currently has an icon or symbol alongside the business name, design this version as a "
    "refreshed icon+text lockup — redesign/modernize that icon and pair it with the business "
    "name in updated typography, evolving the original's palette and feel per the creative "
    "direction above; both the icon and the business name must be clearly present. If the "
    "uploaded logo is text-only (no icon or symbol), design this version instead as a refreshed "
    "pure text-only wordmark — no icon of any kind, just modernized typography and color for the "
    "business name, evolving the original's feel per the creative direction above.",
    "Design direction for THIS version: a refreshed icon+text design, regardless of whether the "
    "original logo had an icon — introduce or modernize a fitting icon/symbol for the business, "
    "placed beside or above the business name in a clean supporting typeface. Both the icon and "
    "the business name must be clearly present.",
    "Design direction for THIS version: look at the uploaded reference logo again. If it is "
    "text-only (no icon or symbol), design this version instead as a refreshed badge or "
    "combination mark — introduce a fitting icon combined with the business name into a single "
    "cohesive unit (e.g. enclosed in a shape, monogram-style, or tightly integrated lockup), "
    "giving a more established/traditional brand feel; both the icon and the business name must "
    "be clearly present in that case.\n"
    "CRITICAL — if the uploaded reference logo currently HAS an icon or symbol, this version must "
    "instead be a pure text-only wordmark with ZERO icons, symbols, circular badges, sunbursts, "
    "rays, or any other graphic mark — none whatsoever, even a small or subtle one. This is "
    "non-negotiable for this version: completely remove/omit the icon from the reference image, "
    "do not carry it over, do not shrink it, do not turn it into a decorative letterform accent — "
    "just delete it. The business name alone, in expressive, well-crafted typography, IS the "
    "entire mark. Typography and color are the only design tools available for this version.",
]


def build_edit_prompt(
    company_name: str, suggestion: str, variation_index: int, meeting_brief: str = ""
) -> str:
    """variation_index: 0, 1, or 2 — selects which of the 3
    VARIATION_DIRECTIVES steers this particular edit: index 0 mirrors the
    uploaded logo's own type (icon+text stays icon+text, text-only stays
    text-only), index 1 is always icon+text, index 2 is the opposite of the
    original's type — see module docstring for why this always nets out to
    1 text-only + 2 icon+text overall, mirroring CONCEPT_DIRECTIVES in
    generation_prompt.py.

    company_name: stated explicitly so the model has an unambiguous source
    of truth for the business name text, instead of only inferring it from
    the reference image's pixels.

    meeting_brief: concrete must-apply requirements already distilled from a
    Fathom meeting transcript by transcript_extraction_agent.py (a bullet
    list of specific colors/icons/style the client asked for or ruled out).
    Framed as MANDATORY, like in build_generation_prompt() — the client
    already confirmed these in a meeting, so they aren't optional guidance.
    """
    suggestion_line = f"\nCreative direction requested: {suggestion}\n" if suggestion else ""
    meeting_brief_line = (
        f"\nConfirmed client requirements from a meeting (MANDATORY — apply every line exactly, "
        f"these are not optional guidance):\n{meeting_brief}\n"
        if meeting_brief
        else ""
    )
    return BASE_EDIT_PROMPT.format(
        company_name=company_name,
        suggestion_line=suggestion_line,
        meeting_brief_line=meeting_brief_line,
        variation_directive=VARIATION_DIRECTIVES[variation_index % len(VARIATION_DIRECTIVES)],
    )
