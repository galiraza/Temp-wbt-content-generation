"""Headline/mood extraction agent: splits a post title into a headline +
subheadline and derives a short mood descriptor from the industry - see
prompts/headline_mood_prompt.py. Feeds directly into final_image_prompt.py.
"""

from typing import Dict

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.agents.post_generation.client import structured_llm
from app.agents.post_generation.prompts.headline_mood_prompt import HEADLINE_MOOD_USER_PROMPT
from app.config import has_anthropic_key

_HEADLINE_MOOD_PROMPT = ChatPromptTemplate.from_messages([("user", HEADLINE_MOOD_USER_PROMPT)])


class _HeadlineMoodOut(BaseModel):
    headline: str
    subheadline: str
    mood: str


def _stub_split(title: str, industry: str) -> Dict[str, str]:
    """No ANTHROPIC_API_KEY: split on the same punctuation priority the real
    prompt uses, well enough to keep the image pipeline testable, rather
    than failing. Same convention as this module's other stub paths."""
    for sep in (":", "?", ","):
        if sep in title:
            head, _, sub = title.partition(sep)
            return {"headline": head.strip(), "subheadline": sub.strip(), "mood": f"[Stub mood for {industry}]"}
    return {"headline": title.strip(), "subheadline": "", "mood": f"[Stub mood for {industry}]"}


def extract_headline_mood(title: str, industry: str) -> Dict[str, str]:
    """title: a post's title, or a reel's first on-screen line used the same
    way (see final_image_agent.py)."""
    industry = industry or "Not provided"
    if not has_anthropic_key():
        return _stub_split(title, industry)

    prompt_value = _HEADLINE_MOOD_PROMPT.invoke({"image_video_title": title, "industry": industry})
    result = structured_llm(_HeadlineMoodOut, label="headline-mood").invoke(prompt_value)
    return {"headline": result.headline, "subheadline": result.subheadline, "mood": result.mood}
