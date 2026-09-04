"""LLM agent that writes Meta (Facebook/Instagram) ad angles for a company's
service, grounded in real client examples retrieved from Pinecone (see
app.rag.retrieval).
"""

import hashlib
import re
from typing import List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.agents.meta_ads.ad_angles.prompts.ad_angle_prompts import (
    FEEDBACK_SYSTEM_PROMPT,
    SINGLE_SYSTEM_PROMPT,
    SINGLE_USER_PROMPT,
    SYSTEM_PROMPT,
    USER_PROMPT,
    format_rag_examples_block,
)
from app.rag.retrieval import retrieve_examples

NUM_ANGLES = 6

_DASH_RE = re.compile(r"\s*[—–]\s*")

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "]️?"
)


def _strip_dashes(text: str) -> str:
    """The style guide tells the LLM to never use em/en dashes, but models
    reach for them anyway (a well-known LLM writing tic). Enforce it here in
    code as a guaranteed backstop rather than relying on the prompt alone.
    """
    return _DASH_RE.sub(", ", text)


def _move_emoji_to_start(headline: str) -> str:
    """The style guide tells the LLM to put exactly one emoji at the very
    start of the headline, but models sometimes tack it on the end instead.
    Enforce the position here in code: pull out the first emoji found
    (dropping any extras) and re-prepend it, rather than relying on the
    prompt alone.
    """
    match = _EMOJI_RE.search(headline)
    if not match:
        return headline
    first_emoji = match.group(0)
    rest = re.sub(r"\s+", " ", _EMOJI_RE.sub("", headline)).strip()
    return f"{first_emoji} {rest}"


_BULLET_EMOJI_RULES = [
    (re.compile(r"hour|minute|second|\bday\b|days|week|fast|quick|speed|rapid|same-day|same day|24/7|turnaround|response|instant", re.I), "⏱️"),
    (re.compile(r"£|\$|price|pricing|cost|save|saving|financ|apr|payment|fee|discount|\boff\b|afford", re.I), "💰"),
    (re.compile(r"warrant|guarantee|certif|registered|gas safe|insur|protect|peace of mind|risk-free|risk free", re.I), "🛡️"),
    (re.compile(r"install|engineer|technician|\bfit\b|fitted|fitting|service|maintenance|repair|workmanship|commission", re.I), "🔧"),
    (re.compile(r"star|rated|rating|review|quality|trusted|award|best|excellen|premium", re.I), "⭐"),
    (re.compile(r"eco|green|energy|efficien|renewable|sustainab|a-rated|a rated", re.I), "🌿"),
    (re.compile(r"support|contact|call|available|help|assist|friendly", re.I), "📞"),
    (re.compile(r"home|room|house|propert|conservatory|space", re.I), "🏠"),
]
_DEFAULT_BULLET_EMOJI = "✅"
# Chance to use the plain checkmark even when a themed emoji would also fit,
# so ✅ stays a normal, recurring member of the mix rather than disappearing
# entirely once every bullet has a keyword match (some angles should end up
# all-tick, others mostly themed, others a blend — see _pick_bullet_emoji).
_TICK_PROBABILITY = 0.4


def _pick_bullet_emoji(bullet_text: str) -> str:
    """Choose a bullet's emoji from its own wording instead of trusting
    whatever the LLM picked (models are told to vary the emoji per bullet
    based on content, but often ignore that and reuse the same one for
    every bullet in an angle). A themed match isn't forced every time
    though: the plain checkmark is used for a portion of bullets even when
    a theme would fit, since ✅ is a normal, always-valid choice and should
    stay part of the natural mix rather than vanish once a keyword match
    exists for nearly every bullet.

    The tick-or-themed choice is derived from a hash of the bullet's own
    text rather than true randomness, so re-sanitizing the same bullet
    (e.g. on every turn of a feedback chat, where most bullets are carried
    over unchanged) always reproduces the same emoji for it. Only a bullet
    whose wording actually changed gets a freshly (but still deterministic)
    computed emoji — untouched bullets never get disturbed by re-rolls.
    """
    digest = hashlib.md5(bullet_text.encode("utf-8")).hexdigest()
    roll = int(digest[:8], 16) / 0xFFFFFFFF
    if roll < _TICK_PROBABILITY:
        return _DEFAULT_BULLET_EMOJI
    for pattern, emoji in _BULLET_EMOJI_RULES:
        if pattern.search(bullet_text):
            return emoji
    return _DEFAULT_BULLET_EMOJI


def _strip_stray_emojis(primary_text: str, *, reassign_bullet_emoji: bool = True) -> str:
    """The style guide restricts emojis to the very start of bullet/list
    lines, but models still slip one into a hook or CTA line mid-sentence.
    Enforce it here per line: a line that starts with an emoji is a bullet,
    so its leading emoji is kept — or, when reassign_bullet_emoji is True,
    replaced with one chosen from that bullet's own wording (see
    _pick_bullet_emoji) — and any other emoji in the line is dropped; any
    other line gets every emoji stripped, since it isn't allowed one at all.

    reassign_bullet_emoji must be False for the feedback-chat flow: a user
    can explicitly ask to change one bullet's emoji, and overriding the
    model's answer back to the keyword-matched pick would silently ignore
    that request. It stays True for fresh generation, where guaranteeing
    contextual, varied emojis matters more than preserving an exact model
    choice.
    """
    lines = primary_text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        match = _EMOJI_RE.match(stripped)
        if match:
            leading_emoji = match.group(0)
            rest = re.sub(r"\s+", " ", _EMOJI_RE.sub("", stripped[match.end() :])).strip()
            emoji = _pick_bullet_emoji(rest) if reassign_bullet_emoji else leading_emoji
            cleaned_lines.append(f"{emoji} {rest}")
        else:
            cleaned_lines.append(re.sub(r"\s+", " ", _EMOJI_RE.sub("", stripped)).strip())
    return "\n".join(cleaned_lines)


def _collapse_blank_lines(primary_text: str) -> str:
    """Lines should only ever be separated by a single newline — no blank-line
    gaps between them (a prior version of this sanitizer inserted a blank
    line before every bullet; that's now unwanted, so any blank line the LLM
    itself produces is stripped too)."""
    lines = primary_text.split("\n")
    return "\n".join(line for line in lines if line.strip() != "")


def _sanitize_angle(
    headline: str, primary_text: str, *, reassign_bullet_emoji: bool = True
) -> Tuple[str, str]:
    headline = _move_emoji_to_start(_strip_dashes(headline))
    primary_text = _collapse_blank_lines(
        _strip_stray_emojis(_strip_dashes(primary_text), reassign_bullet_emoji=reassign_bullet_emoji)
    )
    return headline, primary_text


def _format_rag_examples(industry: List[str], service_content: str) -> str:
    """Retrieves real client example angles for this industry (best-effort) and
    formats them as few-shot examples for the prompt. Returns "" if none found.
    """
    primary_industry = industry[0] if industry else ""
    if not primary_industry:
        return ""
    examples = retrieve_examples(primary_industry, service_content, k=3)
    return format_rag_examples_block(primary_industry, examples)


class _AngleFields(BaseModel):
    headline: str = Field(description="Short punchy headline, under 10 words")
    primary_text: str = Field(
        description="Full ad body: hook, checklist of benefits with emojis, CTA. 80-150 words."
    )


class _AdAngles(BaseModel):
    angles: List[_AngleFields] = Field(description=f"Exactly {NUM_ANGLES} distinct ad angles")


def _build_chain():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.9)
    structured_llm = llm.with_structured_output(_AdAngles)
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("user", USER_PROMPT)]
    )
    return prompt | structured_llm


def generate_ad_angles(
    company_name: str,
    industry: List[str],
    service_name: str,
    service_content: str,
    usps: str,
    offers: List[str],
    previous_angles: str = "",
    count: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Returns a list of (headline, primary_text) tuples.

    `count` overrides NUM_ANGLES for this call, so the content hub's per-client
    setting can ask for a different number. A parameter rather than the caller
    reassigning the module constant: two runs generating at once would otherwise
    read each other's value, and the failure would be a run silently producing
    the wrong number of angles.
    """
    wanted = NUM_ANGLES if count is None else max(1, count)
    chain = _build_chain()
    result = chain.invoke(
        {
            "num_angles": wanted,
            "company_name": company_name,
            "industry": ", ".join(industry) if industry else "N/A",
            "service_name": service_name,
            "service_content": service_content,
            "usps": usps,
            "offers": ", ".join(offers) if offers else "None",
            "previous_angles": previous_angles or "None",
            "rag_examples": _format_rag_examples(industry, service_content),
        }
    )
    angles = [_sanitize_angle(a.headline, a.primary_text) for a in result.angles[:wanted]]
    while len(angles) < wanted:
        i = len(angles) + 1
        angles.append((f"{service_name} for {company_name}", f"[Angle {i}] placeholder ad copy."))
    return angles


def _build_single_chain():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.9)
    structured_llm = llm.with_structured_output(_AngleFields)
    prompt = ChatPromptTemplate.from_messages(
        [("system", SINGLE_SYSTEM_PROMPT), ("user", SINGLE_USER_PROMPT)]
    )
    return prompt | structured_llm


def regenerate_single_angle(
    company_name: str,
    industry: List[str],
    service_name: str,
    service_content: str,
    usps: str,
    offers: List[str],
    existing_headline: str = "",
    existing_primary_text: str = "",
) -> Tuple[str, str]:
    """Returns a (headline, primary_text) tuple."""
    chain = _build_single_chain()
    result = chain.invoke(
        {
            "company_name": company_name,
            "industry": ", ".join(industry) if industry else "N/A",
            "service_name": service_name,
            "service_content": service_content,
            "usps": usps,
            "offers": ", ".join(offers) if offers else "None",
            "existing_headline": existing_headline or "None",
            "existing_primary_text": existing_primary_text or "None",
            "rag_examples": _format_rag_examples(industry, service_content),
        }
    )
    return _sanitize_angle(result.headline, result.primary_text)


class _FeedbackReply(BaseModel):
    is_relevant: bool = Field(
        description="True if the user's latest message is feedback about modifying or "
        "improving THIS specific ad angle (its wording, tone, length, emojis, bullets, "
        "structure, etc.). False for anything else: small talk, questions unrelated to this "
        "angle, or requests outside the scope of editing this angle's copy."
    )
    reply_message: str = Field(
        description="Only used when is_relevant is False: a short, friendly one-sentence "
        "chatbot reply explaining you're only here to help modify this ad angle, so the "
        "user knows to ask again with real feedback. Leave this empty when is_relevant is "
        "True."
    )
    headline: str = Field(
        description="When is_relevant is True, the revised headline. When is_relevant is "
        "False, this must be EXACTLY the current headline, completely unchanged."
    )
    primary_text: str = Field(
        description="When is_relevant is True, the revised primary text. When is_relevant "
        "is False, this must be EXACTLY the current primary text, completely unchanged."
    )


def regenerate_angle_with_feedback(
    company_name: str,
    industry: List[str],
    service_name: str,
    service_content: str,
    usps: str,
    offers: List[str],
    current_headline: str,
    current_primary_text: str,
    chat_history: List[dict],
) -> Tuple[str, str, Optional[str]]:
    """chat_history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    Returns a (headline, primary_text, off_topic_reply) tuple. off_topic_reply is None when
    the feedback was actually about this angle and it was revised; otherwise headline/
    primary_text come back unchanged and off_topic_reply holds a short chatbot reply to show
    instead of an angle revision.
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(_FeedbackReply)

    context = (
        f"Company: {company_name}\n"
        f"Industry: {', '.join(industry) if industry else 'N/A'}\n"
        f"Service name: {service_name}\n"
        f"Service content: {service_content}\n"
        f"USPs: {usps}\n"
        f"Offers: {', '.join(offers) if offers else 'None'}\n"
        f"Current headline: {current_headline}\n"
        f"Current primary text: {current_primary_text}\n"
        f"{_format_rag_examples(industry, service_content)}"
    )

    messages = [("system", FEEDBACK_SYSTEM_PROMPT), ("user", context)]
    for msg in chat_history:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append((role, msg["content"]))

    result = structured_llm.invoke(messages)
    if not result.is_relevant:
        return current_headline, current_primary_text, result.reply_message

    headline, primary_text = _sanitize_angle(
        result.headline, result.primary_text, reassign_bullet_emoji=False
    )
    return headline, primary_text, None
