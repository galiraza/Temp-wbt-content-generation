"""Phase 1: turn a website and a pasted content plan into per-blog briefs.

Two chains, run in this order because the order is forced — the structurer needs
the scrape, and every blog prompt needs the structured result:

    WEBSITE_CHAIN  = prompt | llm | text
    METADATA_CHAIN = prompt | llm | BlogMetadataList

The scrape and the plan parse are independent of each other, so pipeline.py
overlaps them; the sequencing inside each is what this module owns.
"""

import logging
from typing import List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.agents.blog_generation.client import structured_llm, text_llm
from app.agents.blog_generation.firecrawl import scrape_homepage
from app.agents.blog_generation.parsers import BlogMetadata, BlogMetadataList
from app.agents.blog_generation.prompts.metadata_extraction_prompt import (
    METADATA_EXTRACTION_SYSTEM_PROMPT,
    METADATA_EXTRACTION_USER_PROMPT,
)
from app.agents.blog_generation.prompts.website_content_prompt import (
    WEBSITE_CONTENT_USER_PROMPT,
)

logger = logging.getLogger("app")

_WEBSITE_PROMPT = ChatPromptTemplate.from_messages(
    [("user", WEBSITE_CONTENT_USER_PROMPT)]
)
_METADATA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", METADATA_EXTRACTION_SYSTEM_PROMPT),
        ("user", METADATA_EXTRACTION_USER_PROMPT),
    ]
)


def website_content_chain():
    """Restructures a raw scrape into clean markdown.

    Ends at text, not a parser: the output is a markdown document injected
    wholesale into every blog prompt, so there is no structure to extract.
    """
    return _WEBSITE_PROMPT | text_llm(label="blog-website-content")


def metadata_chain():
    """Parses the pasted plan into one brief per blog.

    Constrained to BlogMetadataList rather than parsed out of a ```json fence,
    which is what the n8n Code node did.
    """
    return _METADATA_PROMPT | structured_llm(BlogMetadataList, label="blog-metadata")


def structure_website(website_url: str) -> Tuple[str, str]:
    """Scrapes the homepage and structures it.

    Returns (raw_markdown, structured_markdown). Both are persisted: the raw so a
    re-structure never needs a second scrape, the structured because every blog
    call injects it.
    """
    raw = scrape_homepage(website_url)
    structured = website_content_chain().invoke({"scraped_markdown": raw})
    logger.info(
        "blog_website_structured url=%s raw=%s structured=%s",
        website_url,
        len(raw),
        len(structured),
    )
    return raw, structured


#: Titles a model emits when it is padding the array to hit a target count.
#: The prompt now forbids padding, but a filter here is cheap and the cost of
#: missing one is a wasted write-QC-revise loop on a blog that does not exist.
_PLACEHOLDER_TITLES = {
    "", "<unknown>", "unknown", "n/a", "na", "none", "-", "tbd", "tbc",
    "placeholder", "untitled", "...", "[blog title]", "blog title",
}


def _is_real(blog: BlogMetadata) -> bool:
    title = (blog.blog_title or "").strip()
    return title.lower().strip("*_[]() ") not in _PLACEHOLDER_TITLES


def extract_metadata(blog_schema: str) -> List[BlogMetadata]:
    """Parses the pasted content plan into blog briefs.

    Drops padded entries before renumbering. The n8n prompt demanded "exactly 12
    objects", so a three-blog plan came back as three real briefs plus nine
    "<UNKNOWN>" ones; the prompt no longer asks for a fixed count, and anything
    that still looks like padding is discarded here rather than costing a full
    write-QC-revise loop each.

    Renumbers sequentially from 1 rather than trusting the model's own
    blog_number: dropping an entry leaves a gap, and a gap or duplicate would
    collide with the (request_id, blog_number) unique constraint.
    """
    result = metadata_chain().invoke({"blog_schema": blog_schema})
    returned = result.blogs or []
    blogs = [b for b in returned if _is_real(b)]

    dropped = len(returned) - len(blogs)
    if dropped:
        logger.warning(
            "blog_metadata_padding_dropped returned=%s kept=%s", len(returned), len(blogs)
        )

    for index, blog in enumerate(blogs, start=1):
        blog.blog_number = index
    logger.info("blog_metadata_extracted count=%s dropped=%s", len(blogs), dropped)
    return blogs
