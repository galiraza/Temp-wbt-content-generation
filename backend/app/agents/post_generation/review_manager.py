"""Manager B: mines the client's reviews page and writes 8 review posts.

    HASHTAG_CHAIN = prompt | llm(+web search) | text
    CONTENT_CHAIN = prompt | llm             | ReviewListParser()

Two steps genuinely run in parallel here — the Firecrawl scrape and the hashtag
research have no dependency on each other, and both feed the single content chain.
The scrape is the slowest step in the module, so overlapping the research with it
is most of the saving.

Unlike posts, a short batch is NOT padded. Fewer than 8 usable reviews on the page
means fewer than 8 review posts: the prompt forbids fabricating a review, and a
placeholder review would be exactly that.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.agents.post_generation.client import text_llm
from app.agents.post_generation.firecrawl import platform_from_url, scrape_reviews_page
from app.agents.post_generation.parsers import ReviewListParser, parse_reviews
from app.agents.post_generation.prompts.review_content_prompt import (
    REVIEW_CONTENT_SYSTEM_PROMPT,
    REVIEW_CONTENT_USER_PROMPT,
)
from app.agents.post_generation.prompts.review_hashtag_prompt import (
    REVIEW_HASHTAG_SYSTEM_PROMPT,
    REVIEW_HASHTAG_USER_PROMPT,
)
from app.agents.post_generation.prompts.single_item_prompts import (
    SINGLE_REVIEW_USER_PROMPT,
)
from app.errors import UpstreamServiceError

logger = logging.getLogger("app")

NUM_REVIEWS = 8

_HASHTAG_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVIEW_HASHTAG_SYSTEM_PROMPT), ("user", REVIEW_HASHTAG_USER_PROMPT)]
)
_CONTENT_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVIEW_CONTENT_SYSTEM_PROMPT), ("user", REVIEW_CONTENT_USER_PROMPT)]
)
_SINGLE_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVIEW_CONTENT_SYSTEM_PROMPT), ("user", SINGLE_REVIEW_USER_PROMPT)]
)


def hashtag_chain():
    """B2 - 20 to 30 review-themed UK hashtags, in 3 groups.

    The prompt bans trade and industry tags outright, which is what keeps this
    pool distinct from the post pool.
    """
    return _HASHTAG_PROMPT | text_llm(web_search=True, label="review-hashtag-research")


def content_chain():
    """B3 - extract the real reviews from the scraped page AND write 8 posts."""
    return _CONTENT_PROMPT | text_llm(label="review-content") | ReviewListParser()


def single_review_chain(review_id: int):
    """Rewrite ONE review post's headline and caption.

    Stops at text, like the post equivalent, so the fallback keeps the model's
    output instead of blanking a caption.
    """
    return _SINGLE_PROMPT | text_llm(label=f"review-regenerate-{review_id}")


def _value(request, attr: str, fallback: str = "Not provided") -> str:
    return (getattr(request, attr, None) or "").strip() or fallback


def research_hashtags(request) -> str:
    """Runs B2."""
    return hashtag_chain().invoke(
        {
            "company_name": request.company_name,
            "areas_covered": _value(request, "areas_covered"),
            "year": datetime.utcnow().year,
        }
    )


def _brief_fields(request, hashtag_pool: str, scraped: str) -> Dict[str, str]:
    return {
        "company_name": request.company_name,
        "phone": _value(request, "phone"),
        "email": _value(request, "email"),
        "website_url": _value(request, "website_url"),
        "promotion": _value(request, "promotion", "None"),
        "unique_selling_points": _value(request, "unique_selling_points"),
        "hashtag_pool": hashtag_pool,
        "scraped_reviews": scraped,
    }


def _finalise(parsed: List[Dict], request) -> List[Dict]:
    """Renumber in returned order and fill the two fields no agent produces."""
    reviews = parsed[:NUM_REVIEWS]
    platform = platform_from_url(request.company_reviews_page_url)
    for index, review in enumerate(reviews):
        review["review_number"] = index + 1
        review["platform"] = platform
        if not review.get("name"):
            review["name"] = "Verified customer"
        if not review.get("title"):
            # The graphic needs a headline; the reviewer's name is a safer
            # fallback than inventing a summary of their words.
            review["title"] = f"Review from {review['name']}"
    return reviews


def scrape(request) -> str:
    """B1. Raises if the page yields nothing — see the module docstring."""
    url = (request.company_reviews_page_url or "").strip()
    if not url:
        raise UpstreamServiceError(
            "Review generation",
            "This job has no reviews page URL, so there are no reviews to work from.",
            internal="company_reviews_page_url is empty",
        )
    return scrape_reviews_page(url)


def generate_reviews(request) -> Tuple[List[Dict], str, str]:
    """Runs B1 and B2 in parallel, then B3.

    Returns (reviews, hashtag_pool, scraped_markdown). Both the pool and the raw
    markdown are stored on the request: the pool so a single-review regeneration
    reuses it, the markdown so a re-extraction can pick a different 8 reviews
    without scraping the page again.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        scrape_future = pool.submit(scrape, request)
        hashtag_future = pool.submit(research_hashtags, request)
        # Resolve the scrape first: if the page is unreadable there is nothing to
        # write from, and its error is the one worth surfacing.
        scraped = scrape_future.result()
        hashtag_pool = hashtag_future.result()

    chain = _CONTENT_PROMPT | text_llm(label="review-content")
    raw = chain.invoke(_brief_fields(request, hashtag_pool, scraped))
    parsed = parse_reviews(raw)

    if len(parsed) < NUM_REVIEWS:
        logger.warning(
            "review_parse_short request_id=%s parsed=%s expected=%s",
            request.id,
            len(parsed),
            NUM_REVIEWS,
        )
    if not parsed:
        # Zero parsed items usually means the agent declined rather than
        # malfunctioned: too few positive reviews on the page, or none at all. It
        # explains itself in prose, and that explanation is far more useful to the
        # user than "no reviews found", so it gets passed through.
        raise UpstreamServiceError(
            "Review generation",
            _refusal_message(raw),
            internal=f"review parser returned zero items; agent said: {raw[:400]}",
        )
    return _finalise(parsed, request), hashtag_pool, scraped


def _refusal_message(raw: str) -> str:
    """Turns the agent's prose explanation into one user-facing line.

    Headings and bullets are dropped rather than flattened into the sentence
    stream: they read as fragments once the line breaks are gone.
    """
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        # Markdown headings and list items are labels, not explanation.
        if not stripped or re.match(r"^(#{1,6}\s|[-*>]\s|\|)", stripped):
            continue
        lines.append(re.sub(r"\*\*|`|^-{3,}$", "", stripped))

    prose = re.sub(r"\s+", " ", " ".join(lines)).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prose) if len(s.strip()) > 40]

    detail = ""
    for sentence in sentences[:3]:
        if len(detail) + len(sentence) > 300:
            break
        detail = f"{detail} {sentence}".strip()

    return (
        "Couldn't build 8 review posts from that page. "
        + (detail or "No usable customer reviews were found there.")
        + " Check the URL points at a page that lists your reviews, not a "
        "'write a review' form."
    )


def regenerate_review(request, review, hashtag_pool: str) -> Dict:
    """Rewrites ONE review post's title and caption.

    The customer's words are passed back in and pinned as verbatim, so a
    regeneration can never quietly reword the review itself.
    """
    fields = _brief_fields(request, hashtag_pool or "No researched pool available.", scraped="")
    fields.pop("scraped_reviews")

    raw = single_review_chain(review.id).invoke(
        {
            **fields,
            "review_number": review.review_number,
            "name": review.name,
            "review": review.review,
            "current_title": review.title,
            "current_caption": review.caption,
        }
    )
    parsed = parse_reviews(raw)
    if not parsed:
        logger.warning("review_regen_unparsed review_id=%s", review.id)
        return {
            "review_number": review.review_number,
            "name": review.name,
            "title": review.title,
            "review": review.review,
            "caption": raw.strip(),
            "hashtags": review.hashtag_list,
            "platform": review.platform,
        }
    result = parsed[0]
    result["review_number"] = review.review_number
    result["platform"] = review.platform
    # The quote and the attribution are the customer's, not the model's.
    result["review"] = review.review
    result["name"] = review.name or result.get("name") or "Verified customer"
    if not result.get("title"):
        result["title"] = review.title
    if not result["hashtags"]:
        result["hashtags"] = review.hashtag_list
    return result
