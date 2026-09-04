"""Prompt text for the Generator Agent — from-scratch logo generation.

No reference image exists for this path (unlike ad-angle image generation,
which always replicates a reference ad) — three independent
client.images.generate() calls are made, each nudged toward a different
visual direction via CONCEPT_DIRECTIVES, so the 3 results read as distinct
concepts rather than near-duplicates of the same idea.
"""

BASE_LOGO_PROMPT = """You are an expert brand-identity designer creating a logo for a business.

Business name: "{company_name}"
Industry: {industry}
{style_keywords_line}{suggestion_line}{must_apply_line}
Design a clean, professional, modern logo for this business. The logo must:
- Clearly work as a standalone brand mark — no mockups, no background scene.
- The ONLY text allowed anywhere in the image is the business name itself, rendered once as \
part of the logo. Never add taglines, slogans, mottos, service lists, or any other words — \
express the brand personality and creative direction given below through color, icon, and \
typography choices only, never as literal on-image text.
- Use a plain white or transparent background so it can be placed anywhere.
- Be legible at small sizes (favicon/app-icon scale) as well as large.
- Reflect the industry and any brand personality/creative direction given above through color, \
iconography, or typography choices — but stay tasteful and avoid cliché stock-icon combinations.
- Avoid photorealistic imagery — this is a vector-style brand mark, not a photo or illustration \
scene.
- If a "Confirmed client requirements" list is given above, treat every line as a non-negotiable \
constraint, not a suggestion — apply each one exactly (still without rendering any of it as \
literal on-image text, per the rule above). This is IN ADDITION to any "Creative direction \
requested" also given above, not instead of it — when both are present, apply both together; a \
concrete confirmed requirement (an exact color, icon, or name) must actually be visible in the \
result, not just referenced in spirit. If the two ever conflict on a specific concrete detail, \
the confirmed client requirements win, since the client explicitly approved those in a meeting.

{concept_directive}"""

CONCEPT_DIRECTIVES = [
    "Design direction for THIS concept: a pure text-only wordmark — the business name rendered "
    "in expressive, well-crafted custom typography IS the entire logo. Do not include any icon, "
    "symbol, emblem, or graphic mark of any kind; typography and color are the only design tools "
    "here.",
    "Design direction for THIS concept: an icon+text design — a distinctive symbolic mark "
    "representing the business, placed beside or above the business name, which is always "
    "rendered in a clean supporting typeface. Both the icon and the business name must be "
    "clearly present.",
    "Design direction for THIS concept: a badge or combination mark — the business name and an "
    "icon combined into a single cohesive unit (e.g. enclosed in a shape, monogram-style, or "
    "tightly integrated lockup), giving a more established/traditional brand feel. Both the icon "
    "and the business name must be clearly present.",
]


def build_generation_prompt(
    company_name: str,
    industry: str,
    style_keywords: str,
    suggestion: str,
    concept_index: int,
    meeting_brief: str = "",
) -> str:
    """concept_index: 0, 1, or 2 — selects which of the 3 CONCEPT_DIRECTIVES
    steers this particular generation, so the 3 results are visually distinct
    concepts rather than near-duplicates of the same idea: concept 0 is
    always a text-only wordmark, concepts 1 and 2 always pair an icon with
    the business name.

    style_keywords: 3-4 short brand-personality keywords already distilled
    from raw USPs by usp_style_agent.extract_usp_style_keywords() — never
    raw USP business copy. Framed as inspiration only, like suggestion.

    meeting_brief: concrete must-apply requirements already distilled from a
    Fathom meeting transcript by transcript_extraction_agent.py (a bullet
    list of specific colors/icons/style the client asked for or ruled out).
    Unlike style_keywords/suggestion, this is framed as MANDATORY — the
    client already confirmed these in a meeting, so they aren't optional
    inspiration. The Suggestion field and meeting requirements are treated
    as compatible, not competing (a typed suggestion is usually just the
    same meeting decision restated), so both are always included when
    present rather than picking one over the other.
    """
    style_keywords_line = (
        f"Brand personality/style (for inspiration only, do not display this text): "
        f"{style_keywords}\n"
        if style_keywords
        else ""
    )
    suggestion_line = (
        f"Creative direction requested (for inspiration only, do not display this text): "
        f"{suggestion}\n"
        if suggestion
        else ""
    )
    must_apply_line = (
        f"Confirmed client requirements from a meeting (MANDATORY — apply every line exactly, "
        f"these are not optional inspiration):\n{meeting_brief}\n"
        if meeting_brief
        else ""
    )
    return BASE_LOGO_PROMPT.format(
        company_name=company_name,
        industry=industry,
        style_keywords_line=style_keywords_line,
        suggestion_line=suggestion_line,
        must_apply_line=must_apply_line,
        concept_directive=CONCEPT_DIRECTIVES[concept_index % len(CONCEPT_DIRECTIVES)],
    )
