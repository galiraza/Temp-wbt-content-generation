"""Phase 2, the writing side: the Blog Agent and the Revision Agent.

    BLOG_CHAIN     = prompt | llm | text
    REVISION_CHAIN = prompt | llm | text

Both end at text rather than a parser. The prompt's output format is prose in
four named sections, and splitting it is parsers.split_blog_output's job — kept
separate so a reply the splitter cannot fully read still keeps the model's work
instead of raising and losing the call.

The revision agent is given the QC fixes and told to change only what was
flagged, which is why it receives the original content rather than starting over.
"""

import logging
from typing import Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.agents.blog_generation.client import text_llm
from app.agents.blog_generation.prompts.blog_prompt import (
    BLOG_SYSTEM_PROMPT,
    BLOG_USER_PROMPT,
)
from app.agents.blog_generation.prompts.revision_prompt import (
    REVISION_SYSTEM_PROMPT,
    REVISION_USER_PROMPT,
)

logger = logging.getLogger("app")

_BLOG_PROMPT = ChatPromptTemplate.from_messages(
    [("system", BLOG_SYSTEM_PROMPT), ("user", BLOG_USER_PROMPT)]
)
_REVISION_PROMPT = ChatPromptTemplate.from_messages(
    [("system", REVISION_SYSTEM_PROMPT), ("user", REVISION_USER_PROMPT)]
)

_NOT_PROVIDED = "Not provided"


def blog_chain(blog_number: int):
    """Writes one blog, plus its GMB Post and GMB FAQ, in one call."""
    return _BLOG_PROMPT | text_llm(label=f"blog-write-{blog_number}")


def revision_chain(blog_number: int, round_number: int):
    """Applies one round of QC fixes to one blog."""
    return _REVISION_PROMPT | text_llm(label=f"blog-revise-{blog_number}-r{round_number}")


def _value(value: Optional[str], fallback: str = _NOT_PROVIDED) -> str:
    """Empty optional fields read as "Not provided" rather than as a blank line,
    so the model can tell a field was left out instead of inventing something to
    fill the gap. Same convention as post_manager._value."""
    return (value or "").strip() or fallback


def _joined(values: Optional[List[str]]) -> str:
    """The n8n Metadata Formatter joined these arrays with ", " before they
    reached the prompt, so the prompts were written expecting a plain string."""
    if not values:
        return _NOT_PROVIDED
    return ", ".join(v for v in values if v) or _NOT_PROVIDED


def brief_fields(request, blog) -> Dict[str, object]:
    """The prompt variables shared by the blog and QC prompts."""
    return {
        "client_name": request.client_name,
        "website_content": _value(request.website_content, "Not available"),
        "cluster_theme_1": _value(request.cluster_theme_1),
        "cluster_theme_2": _value(request.cluster_theme_2),
        "cluster_theme_3": _value(request.cluster_theme_3),
        "blog_number": blog.blog_number,
        "blog_title": blog.title,
        "funnel_stage": _value(blog.funnel_stage),
        "service_area": _joined(blog.service_area_list),
        "keywords": _joined(blog.keyword_list),
    }


def write_blog(request, blog) -> str:
    """First draft. Returns the raw reply, unsplit."""
    return blog_chain(blog.blog_number).invoke(brief_fields(request, blog))


def revise_blog(request, blog, *, original: str, audit, round_number: int) -> str:
    """Applies one QC round's fixes. Returns the raw reply, unsplit.

    `qc_fixes` is a " | "-joined string because that is exactly what the n8n QC
    Formatter produced and what the revision prompt was written against.
    """
    fixes = " | ".join(audit.fixes_required) if audit.fixes_required else "No fixes listed."
    return revision_chain(blog.blog_number, round_number).invoke(
        {
            "blog_number": blog.blog_number,
            "blog_title": blog.title,
            "funnel_stage": _value(blog.funnel_stage),
            "service_area": _joined(blog.service_area_list),
            "keywords": _joined(blog.keyword_list),
            "qc_score": audit.score,
            "qc_fixes": fixes,
            "original_content": original,
        }
    )
