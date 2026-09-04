"""The blogs branch: industry -> service -> titles -> keywords -> four blogs.

Five n8n nodes in a straight line, and the only branch in the workflow that is
strictly sequential -- each step reads the last one's answer:

  "Get Industry"          meeting insights -> ONE of 28 industry names
  "Get Service "          meeting insights -> the most-discussed service name
  "Generate Titles"       that service -> four blog titles (web search, OpenAI)
  Get Industry Keywords
    + Aggregate + Keywords  industry -> its keyword row (now keywords.lookup)
  "Blogs"                 titles + keywords + brief -> four blogs, one call

Two things are worth knowing before changing any of it.

The industry and the service are picked by two DIFFERENT prompts from the SAME
input, and they are not interchangeable: the industry is matched against a fixed
28-item list because it is a lookup key for the keyword row, while the service is
free text because it is search-engine input for the titles. Collapsing them into
one call would break whichever of the two uses lost its wording.

"Generate Titles" is the only node in the workflow not on Claude. Its prompt says
"Always use web search in UK to gather the latest information about the topic",
so it ran on `gpt-4o-search-preview`. See client.search_llm.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate

from app.agents.website_content import keywords as keyword_table
from app.agents.website_content.client import search_llm, text_llm
from app.agents.website_content.knowledge_base import blogs_tools
from app.agents.website_content.page_agents import run_tool_agent
from app.agents.website_content.prompts.blog_prompts import (
    BLOGS_SYSTEM_PROMPT,
    BLOGS_USER_PROMPT,
    GENERATE_TITLES_PROMPT,
    GET_INDUSTRY_PROMPT,
    GET_SERVICE_PROMPT,
)
from app.errors import UpstreamServiceError

logger = logging.getLogger("app")

#: The section title the n8n Set node wrote. Part of the delivered contract.
BLOGS_SECTION_TITLE = "Blogs"

_INDUSTRY_TEMPLATE = ChatPromptTemplate.from_messages([("user", GET_INDUSTRY_PROMPT)])
_SERVICE_TEMPLATE = ChatPromptTemplate.from_messages([("user", GET_SERVICE_PROMPT)])
_TITLES_TEMPLATE = ChatPromptTemplate.from_messages([("user", GENERATE_TITLES_PROMPT)])
_BLOGS_TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", BLOGS_SYSTEM_PROMPT), ("user", BLOGS_USER_PROMPT)]
)


@dataclass
class BlogBrief:
    """What the three lead-in calls produced, kept so the UI can show it.

    n8n threw all of this away the moment the blogs were written, which made
    "why did it write about boilers" unanswerable after the fact. Each field is
    persisted on the request row instead.
    """

    industry: str = ""
    service: str = ""
    titles: str = ""
    keywords: str = ""
    notes: List[str] = field(default_factory=list)


def pick_industry(complete_meeting_insights: str) -> str:
    """One of the 28 industry names, used only as the keyword-row lookup key.

    The prompt says "Return EXACTLY one service name from the list above ... no
    quotes, explanations, or additional text", so the reply is used as-is beyond
    stripping whitespace and any quotes a model wrapped it in anyway. It is NOT
    validated against the list here: keywords.lookup already treats an
    unrecognised industry as a miss, which is the same outcome n8n reached.
    """
    chain = _INDUSTRY_TEMPLATE | text_llm(label="classify")
    raw = chain.invoke({"complete_meeting_insights": complete_meeting_insights})
    return raw.strip().strip('"').strip("'").strip()


def pick_service(complete_meeting_insights: str) -> str:
    """The single most-discussed service, as the seed for the blog titles."""
    chain = _SERVICE_TEMPLATE | text_llm(label="classify")
    raw = chain.invoke({"complete_meeting_insights": complete_meeting_insights})
    return raw.strip().strip('"').strip("'").strip()


def generate_titles(service: str) -> str:
    """Four blog titles, from a live UK web search.

    Returned as the model's raw text, not a parsed list, because that is exactly
    what the Blogs prompt receives under "## BLOG TOPIC(S)" -- it reads the block
    itself and writes "ONE complete blog post for EACH topic". Splitting it here
    and rejoining it would only risk changing the block the prompt was tuned on.
    """
    chain = _TITLES_TEMPLATE | search_llm()
    return chain.invoke({"service": service}).strip()


def build_brief(complete_meeting_insights: str) -> BlogBrief:
    """Runs the three lead-in calls and the keyword lookup.

    Each step degrades rather than raises. The blogs prompt can write from the
    business brief alone: without titles it has no topics and produces nothing
    useful, but without keywords or a matched industry it writes perfectly good
    blogs -- which is what n8n did whenever the data table had no matching row.
    """
    brief = BlogBrief()

    try:
        brief.industry = pick_industry(complete_meeting_insights)
    except UpstreamServiceError as exc:
        logger.warning("website_blog_industry_failed error=%s", exc.internal or exc)
        brief.notes.append("Could not identify the industry, so no keywords were applied.")

    try:
        brief.service = pick_service(complete_meeting_insights)
    except UpstreamServiceError as exc:
        logger.warning("website_blog_service_failed error=%s", exc.internal or exc)
        brief.notes.append("Could not identify the lead service for the blog titles.")

    brief.keywords = keyword_table.lookup(brief.industry)

    # No service means nothing to search for, and the titles prompt would be
    # searching an empty string. Fall back to the industry, which is the same
    # subject matter one level less specific.
    subject = brief.service or brief.industry
    if subject:
        try:
            brief.titles = generate_titles(subject)
        except UpstreamServiceError as exc:
            logger.warning("website_blog_titles_failed error=%s", exc.internal or exc)
            brief.notes.append("Could not generate blog titles.")
    else:
        brief.notes.append("No service or industry was identified, so no titles were generated.")

    logger.info(
        "website_blog_brief industry=%s service=%s has_keywords=%s has_titles=%s",
        brief.industry,
        brief.service,
        bool(brief.keywords),
        bool(brief.titles),
    )
    return brief


def write_blogs(brief: Dict[str, Any], blog_brief: BlogBrief) -> str:
    """Writes all four blogs in one call, as the n8n node did.

    One call, not four: the prompt's own duplication rule ("does not repeat any
    wording, phrasing, structures, intros, conclusions, or angles used in
    previous blogs for this client") only works when the model can see the blogs
    it has already written in this reply. Four separate calls would each be blind
    to the others.
    """
    if not blog_brief.titles:
        raise UpstreamServiceError(
            "Website content generation",
            "No blog titles were generated, so the blogs could not be written.",
            internal="write_blogs called with no titles",
        )

    fields = {key: brief.get(key, "") for key in _BLOGS_TEMPLATE.input_variables}
    fields["blog_titles"] = blog_brief.titles
    fields["keywords"] = blog_brief.keywords
    messages = _BLOGS_TEMPLATE.invoke(fields).to_messages()
    return run_tool_agent(messages, blogs_tools(), label="blogs")
