"""The three intake agents: sitemap extraction, meeting analysis, industry match.

    SITEMAP_CHAIN  = prompt | llm | text   -> parse_sitemap_output
    ANALYST_CHAIN  = prompt | llm | text   -> find_json_object
    REPAIR_CHAIN   = prompt | llm | text   -> find_json_object
    INDUSTRY_CHAIN = prompt | llm | text   -> parse_matched_industries

All four end at text rather than a structured parser, deliberately. Their prompts
specify their own JSON shapes at length -- the analyst's runs to sixty lines of
worked example -- and binding a Pydantic schema over the top would hand the model
a second, differently worded contract for the same reply. The prompts are not to
be changed, so the JSON they ask for is read back as written.

The analyst's repair path is the workflow's own: "Parse Json of Analyst Node" had
an error output wired to a "Json Correction Agent", whose repaired reply was then
parsed again. `analyse` reproduces that, one repair attempt and no more.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.agents.website_content.client import text_llm
from app.agents.website_content.parsers import (
    SitemapData,
    find_json_object,
    parse_matched_industries,
    parse_sitemap_output,
)
from app.agents.website_content.prompts.analyst_prompt import (
    ANALYST_PROMPT,
    JSON_CORRECTION_PROMPT,
)
from app.agents.website_content.prompts.industry_prompt import (
    SELECT_INDUSTRY_SYSTEM_PROMPT,
    SELECT_INDUSTRY_USER_PROMPT,
)
from app.agents.website_content.prompts.sitemap_prompt import SITEMAP_EXTRACTION_PROMPT
from app.errors import UpstreamServiceError

logger = logging.getLogger("app")

_SERVICE = "Website content generation"

# n8n's Sitemap Data Extractor and Analyst Node were both agent/chain nodes with
# no system message: the entire instruction sat in the user turn.
_SITEMAP_TEMPLATE = ChatPromptTemplate.from_messages([("user", SITEMAP_EXTRACTION_PROMPT)])
_ANALYST_TEMPLATE = ChatPromptTemplate.from_messages([("user", ANALYST_PROMPT)])
_REPAIR_TEMPLATE = ChatPromptTemplate.from_messages([("user", JSON_CORRECTION_PROMPT)])
_INDUSTRY_TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", SELECT_INDUSTRY_SYSTEM_PROMPT), ("user", SELECT_INDUSTRY_USER_PROMPT)]
)


# --------------------------------------------------------------------------
# Sitemap Data Extractor
# --------------------------------------------------------------------------


def extract_sitemap(sitemap_text: str) -> SitemapData:
    """Parses the pasted sitemap into services, areas and other pages.

    Everything downstream depends on this: the prompts call the sitemap the
    "highest authority" and forbid mentioning any service or area that is not on
    it. So unlike the industry classifier, an unreadable reply here raises.
    """
    chain = _SITEMAP_TEMPLATE | text_llm(label="sitemap")
    raw = chain.invoke({"sitemap_text": sitemap_text})
    try:
        return parse_sitemap_output(raw)
    except ValueError as exc:
        logger.warning("website_sitemap_parse_failed error=%s reply=%.400s", exc, raw)
        error = UpstreamServiceError(
            _SERVICE,
            "Couldn't read the sitemap. Check the pasted text and try again.",
            internal=f"sitemap parse failed: {exc}",
        )
        # One bad reply, not a standing condition -- worth asking again.
        error.retryable = True
        raise error from exc


# --------------------------------------------------------------------------
# Analyst Node (+ Json Correction Agent)
# --------------------------------------------------------------------------

#: The analyst prompt reads every field, and an absent one must read as absent
#: rather than as the literal string "undefined" that n8n would have inserted.
_EMPTY = ""


def analyst_fields(brief: Dict[str, Any]) -> Dict[str, Any]:
    """The analyst prompt's twenty-four inputs, defaulted to empty strings.

    Missing optional meetings arrive as "" here. The prompt already marks slots
    2 and 3 "[if exists]", so a blank reads correctly to the model.
    """
    return {key: brief.get(key, _EMPTY) or _EMPTY for key in _ANALYST_TEMPLATE.input_variables}


def analyse(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Runs the analyst, repairing its JSON once if the first reply won't parse.

    Returns the Meeting Insights object the rest of the workflow calls
    `complete_meeting_insights`.
    """
    chain = _ANALYST_TEMPLATE | text_llm(label="analyst")
    raw = chain.invoke(analyst_fields(brief))

    try:
        parsed = find_json_object(raw)
    except ValueError as exc:
        logger.warning("website_analyst_parse_failed error=%s", exc)
        repair = _REPAIR_TEMPLATE | text_llm(label="json_correction")
        repaired = repair.invoke({"raw_output": raw, "error_message": str(exc)})
        try:
            parsed = find_json_object(repaired)
        except ValueError as repair_exc:
            error = UpstreamServiceError(
                _SERVICE,
                "The meeting analysis came back unreadable. Please try again.",
                internal=f"analyst repair failed: {repair_exc}",
            )
            error.retryable = True
            raise error from repair_exc
        logger.info("website_analyst_repaired")

    if not isinstance(parsed, dict):
        error = UpstreamServiceError(
            _SERVICE,
            "The meeting analysis came back in an unexpected shape. Please try again.",
            internal=f"analyst returned {type(parsed).__name__}, expected object",
        )
        error.retryable = True
        raise error
    return parsed


# --------------------------------------------------------------------------
# Select Industry
# --------------------------------------------------------------------------


def classify_industries(other_industries: Optional[str]) -> List[str]:
    """Maps free-text "Other Industries" onto the five approved knowledge bases.

    Skipped entirely when the field is empty -- which is the `If` node in n8n,
    testing `other_industries` for existence before running the classifier at
    all. Never raises: see parse_matched_industries.
    """
    text = (other_industries or "").strip()
    if not text:
        return []

    chain = _INDUSTRY_TEMPLATE | text_llm(label="classify")
    try:
        raw = chain.invoke({"other_industries": text})
    except UpstreamServiceError as exc:
        # The ticked industries are already on the brief; losing the free-text
        # extras is not worth failing a run over.
        logger.warning("website_industry_classify_failed error=%s", exc.internal or exc)
        return []
    return parse_matched_industries(raw)
