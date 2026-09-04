"""Manager A: writes the month's 12 items, 8 static posts and 4 reels.

Two chains, run in this order because the order is forced — the researcher's pool
is injected into the content prompt, so it has to finish first:

    HASHTAG_CHAIN = prompt | llm(+web search) | text
    CONTENT_CHAIN = prompt | llm              | text

ONE call produces all 12. The same response is then parsed twice, by parse_posts
and parse_reels, and each item is routed to its table by slot number: 2, 5, 8 and
11 are reels, the other eight are posts. One call rather than two because the
prompt's variety rules operate across the whole set, and because the reel writer
would otherwise be blind to the angles the posts already used.

The content chain also picks each item's 5-8 tags out of the pool itself, with the
tier quotas the prompt spells out. That is not a separate agent, it is part of the
one call, exactly as WF1 did it.

Parallelism happens a level up: this manager runs concurrently with the review
manager (see pipeline.py).
"""

import logging
from typing import Dict, List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.agents.post_generation.client import text_llm
from app.agents.post_generation.parsers import parse_posts, parse_reels
from app.agents.post_generation.prompts.post_content_prompt import (
    POST_CONTENT_SYSTEM_PROMPT,
    POST_CONTENT_USER_PROMPT,
)
from app.agents.post_generation.prompts.post_hashtag_prompt import (
    POST_HASHTAG_SYSTEM_PROMPT,
    POST_HASHTAG_USER_PROMPT,
)
from app.agents.post_generation.prompts.single_item_prompts import (
    SINGLE_POST_USER_PROMPT,
    SINGLE_REEL_USER_PROMPT,
)
from app.models.post_generation.post import POST_SLOT_THEMES, POST_SLOTS
from app.models.post_generation.reel import REEL_SLOT_THEMES, REEL_SLOTS

logger = logging.getLogger("app")

NUM_POSTS = len(POST_SLOTS)   # 8 static slots
NUM_REELS = len(REEL_SLOTS)   # 4 reel slots
NUM_ITEMS = NUM_POSTS + NUM_REELS

# Templates are module-level and built once. The prompt text is verbatim from the
# n8n nodes; only the n8n expressions became {field} placeholders.
_HASHTAG_PROMPT = ChatPromptTemplate.from_messages(
    [("system", POST_HASHTAG_SYSTEM_PROMPT), ("user", POST_HASHTAG_USER_PROMPT)]
)
_CONTENT_PROMPT = ChatPromptTemplate.from_messages(
    [("system", POST_CONTENT_SYSTEM_PROMPT), ("user", POST_CONTENT_USER_PROMPT)]
)
_SINGLE_PROMPT = ChatPromptTemplate.from_messages(
    [("system", POST_CONTENT_SYSTEM_PROMPT), ("user", SINGLE_POST_USER_PROMPT)]
)
_SINGLE_REEL_PROMPT = ChatPromptTemplate.from_messages(
    [("system", POST_CONTENT_SYSTEM_PROMPT), ("user", SINGLE_REEL_USER_PROMPT)]
)


def hashtag_chain():
    """A1 - research 40 to 50 trending UK hashtags, in 3 tiers.

    Ends at text, not a parser: the content prompt asks the model to honour a
    per-tier quota, so it needs the tiers as the researcher wrote them. Parsing
    the pool into a flat list would destroy the structure the quota depends on.
    """
    return _HASHTAG_PROMPT | text_llm(web_search=True, label="post-hashtag-research")


def content_chain():
    """A2 - write all 12 items, statics and reels, hashtags included, in one call.

    Ends at text rather than a parser because the SAME response feeds two
    parsers: parse_posts reads the static blocks, parse_reels reads the reel
    blocks. One call is also what the prompt's variety rules assume, since they
    work across all 12 ("never use the same angle twice across 12 posts").
    """
    return _CONTENT_PROMPT | text_llm(label="post-content")


def single_post_chain(post_id: int):
    """Rewrite ONE post. Reuses the batch system prompt, so every writing rule,
    word count, CTA requirement and hashtag quota still applies.

    Deliberately stops at text instead of ending in PostListParser: if the model
    ignores the output format there is nothing to parse, and the fallback needs
    the raw text so a regeneration never silently blanks a caption.
    """
    return _SINGLE_PROMPT | text_llm(label=f"post-regenerate-{post_id}")


def single_reel_chain(reel_id: int):
    """Rewrite ONE reel. Same batch system prompt, so the reel format, word counts
    and CTA rules all still apply."""
    return _SINGLE_REEL_PROMPT | text_llm(label=f"reel-regenerate-{reel_id}")


def _value(request, attr: str, fallback: str = "Not provided") -> str:
    """Empty optional fields read as "Not provided" rather than as a blank line,
    so the model can tell a field was left out instead of inventing something to
    fill the gap."""
    return (getattr(request, attr, None) or "").strip() or fallback


def research_hashtags(request) -> str:
    """Runs A1. Returns the researcher's tiered output as raw text."""
    return hashtag_chain().invoke(
        {
            "main_topic": _value(request, "main_topic"),
            "areas_covered": _value(request, "areas_covered"),
        }
    )


def _brief_fields(request, hashtag_pool: str) -> Dict[str, str]:
    return {
        "company_name": request.company_name,
        "phone": _value(request, "phone"),
        "email": _value(request, "email"),
        "website_url": _value(request, "website_url"),
        "month": _value(request, "month", "this month"),
        "main_topic": _value(request, "main_topic"),
        "promotion": _value(request, "promotion", "None"),
        "fixed_rules": _value(request, "fixed_rules", "None"),
        "additional_resources": _value(request, "additional_resources"),
        "additional_notes": _value(request, "additional_notes"),
        "unique_selling_points": _value(request, "unique_selling_points"),
        "hashtag_pool": hashtag_pool,
    }


def _placeholder(number: int, kind: str) -> Dict:
    """A short batch would leave the grid with fewer cards and no explanation. An
    obvious, editable placeholder is easier to notice and fix than a card that
    never appeared."""
    body = (
        f"[Slot {number}] The writer returned fewer than {NUM_ITEMS} items. "
        "Regenerate this one on its own to fill it in."
    )
    if kind == "reel":
        return {"reel_number": number, "reel_text": body, "caption": body, "hashtags": []}
    return {
        "post_number": number,
        "title": f"Slot {number} — not returned",
        "caption": body,
        "hashtags": [],
    }


def _finalise(parsed: List[Dict], kind: str) -> List[Dict]:
    """Fit whatever came back onto the fixed slot list for this kind.

    The slots are fixed by the prompt, so they are the source of truth rather
    than the model's numbering: an item claiming slot 5 when 5 is a reel slot,
    or two items claiming the same slot, would otherwise corrupt the month. Items
    are taken in the order returned and assigned to the slots in order, and any
    missing tail becomes a placeholder.
    """
    slots = REEL_SLOTS if kind == "reel" else POST_SLOTS
    themes = REEL_SLOT_THEMES if kind == "reel" else POST_SLOT_THEMES
    number_key = "reel_number" if kind == "reel" else "post_number"

    # Prefer the model's own slot number when it is a legal slot for this kind,
    # so a response that came back out of order still lands correctly.
    by_slot: Dict[int, Dict] = {}
    spare: List[Dict] = []
    for item in parsed:
        claimed = item.get(number_key)
        if claimed in slots and claimed not in by_slot:
            by_slot[claimed] = item
        else:
            spare.append(item)

    result: List[Dict] = []
    for slot in slots:
        item = by_slot.get(slot) or (spare.pop(0) if spare else _placeholder(slot, kind))
        item[number_key] = slot
        item["theme"] = themes[slot]
        result.append(item)
    return result


def generate_posts(request) -> Tuple[List[Dict], List[Dict], str]:
    """Runs A1 then A2, and splits the one response into posts and reels.

    Returns (posts, reels, hashtag_pool). The pool is stored on the request so a
    later single-item regeneration reuses it instead of paying for another web
    search.
    """
    hashtag_pool = research_hashtags(request)

    raw = content_chain().invoke(_brief_fields(request, hashtag_pool))
    # Same text, parsed twice: the routing to each table is by slot number, which
    # is what the prompt assigns and what the two parsers read back.
    posts = parse_posts(raw)
    reels = parse_reels(raw)

    if len(posts) < NUM_POSTS or len(reels) < NUM_REELS:
        logger.warning(
            "post_parse_short request_id=%s posts=%s/%s reels=%s/%s",
            request.id,
            len(posts),
            NUM_POSTS,
            len(reels),
            NUM_REELS,
        )
    return _finalise(posts, "post"), _finalise(reels, "reel"), hashtag_pool


def regenerate_post(request, post, hashtag_pool: str) -> Dict:
    """Rewrites ONE post, keeping its slot and theme."""
    fields = _brief_fields(request, hashtag_pool or "No researched pool available.")
    raw = single_post_chain(post.id).invoke(
        {
            **fields,
            "post_number": post.post_number,
            "theme": post.theme,
            "current_title": post.title,
            "current_caption": post.caption,
        }
    )
    parsed = parse_posts(raw)
    if not parsed:
        # Nothing parsed means the model ignored the output format. Keep its work
        # as the caption rather than losing the call; the user can edit or retry.
        logger.warning("post_regen_unparsed post_id=%s", post.id)
        return {
            "post_number": post.post_number,
            "theme": post.theme,
            "title": post.title,
            "caption": raw.strip(),
            "hashtags": post.hashtag_list,
        }
    result = parsed[0]
    result["post_number"] = post.post_number
    result["theme"] = post.theme
    if not result["hashtags"]:
        result["hashtags"] = post.hashtag_list
    return result


def regenerate_reel(request, reel, hashtag_pool: str) -> Dict:
    """Rewrites ONE reel, keeping its slot and angle."""
    fields = _brief_fields(request, hashtag_pool or "No researched pool available.")
    raw = single_reel_chain(reel.id).invoke(
        {
            **fields,
            "reel_number": reel.reel_number,
            "theme": reel.theme,
            "current_reel_text": reel.reel_text,
            "current_caption": reel.caption,
        }
    )
    parsed = parse_reels(raw)
    if not parsed:
        logger.warning("reel_regen_unparsed reel_id=%s", reel.id)
        return {
            "reel_number": reel.reel_number,
            "theme": reel.theme,
            "reel_text": reel.reel_text,
            "caption": raw.strip(),
            "hashtags": reel.hashtag_list,
        }
    result = parsed[0]
    result["reel_number"] = reel.reel_number
    result["theme"] = reel.theme
    if not result["hashtags"]:
        result["hashtags"] = reel.hashtag_list
    return result
