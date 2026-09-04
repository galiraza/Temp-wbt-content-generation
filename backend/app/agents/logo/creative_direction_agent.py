"""Creative Direction Agent — invents a visual brief when no suggestion was given.

Used by generate_concepts_from_scratch() (logo_image_service.py) only when
the user left the "Your Suggestion" field empty. Turns company_name,
industry, and style_keywords (already distilled from raw USPs by
usp_style_agent.extract_usp_style_keywords() — never raw USP business copy)
into a short, concrete visual brief (icon motif, color palette, typographic
mood) for build_generation_prompt()'s suggestion_line.

Mirrors the ChatOpenAI(model="gpt-4o-mini") + structured-output pattern used
by build_revision_prompt() in editor_agent.py.
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_SYSTEM_PROMPT = """You are an expert brand-identity designer. A client has asked for a logo but \
gave no explicit creative direction — you must invent a tasteful, industry-appropriate visual \
brief for the image-generation model to follow.

Given the business name, industry, and (optionally) a few brand-personality keywords, write ONE \
concise paragraph (2-4 sentences) covering:
- A concrete icon/symbol motif idea suited to the industry (or explicitly "no icon, typography \
only" if a wordmark-only feel suits the business best).
- A specific 2-3 color palette (name the colors) that fits the industry's mood and any brand \
personality keywords given.
- A typographic/overall mood (e.g. bold and confident, friendly and approachable, sleek and \
technical).

Keep it concrete and specific, not generic filler."""

_USER_PROMPT_TEMPLATE = """Business name: "{company_name}"
Industry: {industry}
{style_keywords_line}
Write the visual creative-direction brief."""


class _CreativeDirectionOut(BaseModel):
    direction: str = Field(
        description="The 2-4 sentence visual creative-direction brief (icon motif, color "
        "palette, typographic mood) — no markdown, plain prose."
    )


def generate_ai_creative_direction(company_name: str, industry: str, style_keywords: str) -> str:
    """Returns a short visual creative-direction brief for a business with no
    explicit suggestion. Safe to feed straight into build_generation_prompt()
    as the `suggestion` argument.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8)
    structured_llm = llm.with_structured_output(_CreativeDirectionOut)

    style_keywords_line = f"Brand personality/style: {style_keywords}" if style_keywords else ""
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        company_name=company_name, industry=industry, style_keywords_line=style_keywords_line
    )

    result = structured_llm.invoke(
        [
            ("system", _SYSTEM_PROMPT),
            ("user", user_prompt),
        ]
    )
    return result.direction
