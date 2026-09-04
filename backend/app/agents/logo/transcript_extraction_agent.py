"""Condenses a raw Fathom meeting transcript into a short logo/branding
brief, so it can be fed into the generation prompt without dumping the
entire (often 10s of thousands of characters, mostly irrelevant) transcript
into an image-generation prompt.
"""

from langchain_openai import ChatOpenAI

from app.agents.logo.prompts.transcript_extraction_prompt import (
    TRANSCRIPT_EXTRACTION_SYSTEM_PROMPT,
    TRANSCRIPT_EXTRACTION_USER_PROMPT,
)

# Branding/logo discussion can happen anywhere in a meeting, not just the
# start — a real transcript had its color/icon guidance sitting at the
# ~25,000-char mark, well past a naive early cutoff, which silently dropped
# it from extraction entirely. gpt-4o-mini's 128k-token context window
# comfortably fits full transcripts at this size (roughly 4 chars/token, so
# 150k chars is ~37.5k tokens), so this is a generous safety cap rather than
# a "just the intro" slice.
_MAX_TRANSCRIPT_CHARS = 150_000


def extract_logo_brief(transcript: str) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    user_prompt = TRANSCRIPT_EXTRACTION_USER_PROMPT.format(
        transcript=transcript[:_MAX_TRANSCRIPT_CHARS]
    )
    result = llm.invoke(
        [
            ("system", TRANSCRIPT_EXTRACTION_SYSTEM_PROMPT),
            ("user", user_prompt),
        ]
    )
    return result.content.strip()
