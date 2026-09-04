"""USP Style Agent — converts raw USP/differentiator text into a handful of
short personality/style keywords.

Raw USPs ("Fixed pricing", "Employed staff, no subcontractors") are business
claims, not visual descriptors — feeding them straight into the image
generation prompt risks the model rendering them as literal on-image text or
just misreading/ignoring them. This agent translates them once into 3-4
concrete style/personality keywords (e.g. "trustworthy, professional,
hands-on, no-nonsense") that build_generation_prompt() and
generate_ai_creative_direction() use to steer color/icon/typography choices,
instead of raw business copy.

Mirrors the ChatOpenAI(model="gpt-4o-mini") + structured-output pattern used
elsewhere in this module (see creative_direction_agent.py, editor_agent.py).
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_SYSTEM_PROMPT = """You translate a business's USPs (unique selling points / what makes them \
stand out) into short brand-personality keywords for a logo designer.

Given raw USP text, output 3-4 single-word-or-short-phrase style/personality keywords that \
capture the FEELING the brand should visually project — not the USPs themselves. For example, \
"Fixed pricing, employed staff, no subcontractors" might become "trustworthy, professional, \
hands-on, no-nonsense". Never repeat the USP text verbatim; always translate it into a mood/\
personality a designer could use to pick colors, icon style, and typography."""

_USER_PROMPT_TEMPLATE = """USPs: {usps}

Give the 3-4 style/personality keywords."""


class _UspStyleOut(BaseModel):
    keywords: list[str] = Field(
        description="3-4 short style/personality keywords (single words or very short phrases), "
        "e.g. ['trustworthy', 'professional', 'hands-on', 'no-nonsense']. Never the raw USP text."
    )


def extract_usp_style_keywords(usps: str) -> str:
    """Returns a comma-separated string of 3-4 style/personality keywords
    distilled from raw USP text. Safe to feed into an image-generation
    prompt directly — never contains the raw USP copy.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
    structured_llm = llm.with_structured_output(_UspStyleOut)

    result = structured_llm.invoke(
        [
            ("system", _SYSTEM_PROMPT),
            ("user", _USER_PROMPT_TEMPLATE.format(usps=usps)),
        ]
    )
    return ", ".join(result.keywords)
