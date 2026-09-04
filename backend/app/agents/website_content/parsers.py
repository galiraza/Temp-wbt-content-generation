"""Schemas and parsers for the website-content agents' output.

Replaces five n8n Code nodes:

  "Parse Json of Sitemap Data Extractor"   fence-strip, JSON.parse, split the
                                           extractor's six fields into lists
  "Parse Json of Analyst Node"             fence-strip, JSON.parse the analyst
  "Parse Json of Json Correction Agent"    the same, on the repaired output
  "Parse Json"                             fence-strip the industry classifier,
                                           pull out matched_industry
  "loop_increment"                         read the evaluator's verdict

Everything here is deliberately forgiving in the same places n8n was, and strict
in the one place it was not. n8n's `JSON.parse` threw on any malformed reply and
took the whole run down with it; the two paths that could survive that are given
a real fallback below, and the evaluator -- which n8n backed with a Structured
Output Parser -- is a Pydantic model bound through structured_llm instead.

The page agents themselves need no parsing at all: their prompts end with "clean
Markdown ... starting immediately with the H1 heading", and markdown is what gets
stored.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("app")

#: Both n8n fence-strippers ran this same pair of replaces before parsing. Models
#: still wrap JSON in a fence sometimes, despite every prompt saying not to.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def strip_fence(raw: str) -> str:
    """Removes a leading ```json / ``` and a trailing ```, then trims."""
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    text = _FENCE.sub("", text)
    return text.strip()


def parse_json_object(raw: str) -> Any:
    """Fence-strip, then json.loads. Raises ValueError with the raw text attached.

    The message carries the head of the reply because the only useful next step
    after a parse failure is looking at what the model actually said -- and by
    the time this reaches a log line the reply itself is long gone.
    """
    text = strip_fence(raw)
    try:
        return json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{exc}") from exc


def find_json_object(raw: str) -> Any:
    """parse_json_object, falling back to the first {...} span in the text.

    n8n had no equivalent: a reply with so much as a "Here is the JSON:" prefix
    threw. Every prompt here forbids that prefix, and the models mostly comply,
    but the analyst reply is the input to five hours of downstream work and is
    worth one more attempt before spending a repair call on it.
    """
    try:
        return parse_json_object(raw)
    except ValueError:
        pass

    text = strip_fence(raw)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object found in the reply")
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise ValueError("no JSON object found in the reply")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------
# Sitemap Data Extractor
# --------------------------------------------------------------------------


def _to_list(value: Any) -> List[str]:
    """n8n's `toList`: an array stays an array, a block of text splits on newlines.

    The extractor is told to preserve the source's own wording and order, so the
    services and areas blocks come back as one newline-joined string about as
    often as they come back as an array.
    """
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [line.strip() for line in str(value).split("\n") if line.strip()]


def _to_description_list(value: Any) -> List[Dict[str, str]]:
    """n8n's `toDescriptionList`: {page: description} -> [{page, description}]."""
    if not isinstance(value, dict):
        return []
    return [
        {"page": str(page), "description": str(description)}
        for page, description in value.items()
    ]


class SitemapData(BaseModel):
    """What the Sitemap Data Extractor found, after the Code node's reshaping.

    Field names are the ones that node emitted, because the Form Data node fed
    them straight into the analyst prompt under those names.
    """

    services_offered: List[str] = Field(default_factory=list)
    areas_covered: List[str] = Field(default_factory=list)
    other_pages: List[str] = Field(default_factory=list)
    other_pages_descriptions: List[Dict[str, str]] = Field(default_factory=list)
    # Optional in the prompt's own words: "omit this field entirely from the
    # output ... no empty strings, no N/A, no placeholder values".
    accreditation: Optional[str] = None
    pricing_info: Optional[str] = None


def parse_sitemap_output(raw: str) -> SitemapData:
    """Reads the extractor's JSON reply. Raises ValueError if it is unreadable."""
    parsed = find_json_object(raw)
    if not isinstance(parsed, dict):
        raise ValueError("the sitemap extractor did not return a JSON object")
    return SitemapData(
        services_offered=_to_list(parsed.get("Services Offered")),
        areas_covered=_to_list(parsed.get("Areas Covered")),
        other_pages=_to_list(parsed.get("Other Pages")),
        other_pages_descriptions=_to_description_list(
            parsed.get("Description for Other Pages")
        ),
        accreditation=parsed.get("Accreditation") or None,
        pricing_info=parsed.get("Pricing Info") or None,
    )


# --------------------------------------------------------------------------
# Select Industry
# --------------------------------------------------------------------------


def parse_matched_industries(raw: str) -> List[str]:
    """Pulls `classifications[].matched_industry` out of the classifier's reply.

    n8n wrapped this whole node in try/catch and returned `matched_industries: []`
    on any failure, so a junk reply cost the extra industries and nothing else.
    Kept: the industries the user ticked are already in the brief, and losing the
    free-text extras is not worth failing a run over.
    """
    try:
        parsed = find_json_object(raw)
    except ValueError as exc:
        logger.warning("website_industry_parse_failed error=%s", exc)
        return []

    if not isinstance(parsed, dict):
        return []
    matched = []
    for item in parsed.get("classifications") or []:
        if isinstance(item, dict) and item.get("matched_industry"):
            matched.append(str(item["matched_industry"]).strip())
    return [m for m in matched if m]


# --------------------------------------------------------------------------
# Evaluator Agent
# --------------------------------------------------------------------------


class EvaluatorChecks(BaseModel):
    """The six pass-critical checks, in the evaluator prompt's own names.

    All positive polarity, as the prompt spells out: true means the check PASSED.
    """

    critic_issues_resolved: bool = False
    no_over_correction: bool = False
    no_new_fingerprints: bool = False
    british_english_clean: bool = False
    no_fabrication: bool = False
    facts_and_leadgen_preserved: bool = False


class CarryForwardIssue(BaseModel):
    """One surviving or newly introduced issue, handed to the next Critic round."""

    issue: str = ""
    tag: str = ""       # HARD | DENSITY
    severity: str = ""  # High | Medium | Low
    text: str = ""      # the exact offending quote


class EvaluatorVerdict(BaseModel):
    """The gatekeeper's reply. Mirrors "Structured Output Parser7" exactly.

    `checks` and `carry_forward` both degrade rather than raise, for the same
    reason app.agents.blog_generation.parsers.QcAudit does: by the time the
    evaluator runs, a full page has already been written and refined. Failing the
    whole page because one sub-object came back oddly shaped throws away work
    that is fine, and the two fields that actually drive the loop -- `pass` and
    `carry_forward` -- are read independently of the rest.
    """

    verdict: str = "REVISE"
    passed: bool = Field(default=False, alias="pass")
    reason: str = ""
    checks: EvaluatorChecks = Field(default_factory=EvaluatorChecks)
    carry_forward: List[CarryForwardIssue] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("checks", mode="before")
    @classmethod
    def _coerce_checks(cls, value):
        if isinstance(value, (dict, EvaluatorChecks)):
            return value
        return EvaluatorChecks()

    @field_validator("carry_forward", mode="before")
    @classmethod
    def _coerce_carry_forward(cls, value):
        """Accepts the list of objects the schema asks for, and the two shapes
        models fall back to: a list of plain strings, or one joined string."""
        if not value:
            return []
        if isinstance(value, str):
            return [CarryForwardIssue(issue=value)]
        if isinstance(value, list):
            out = []
            for item in value:
                if isinstance(item, dict):
                    out.append(item)
                elif str(item).strip():
                    out.append({"issue": str(item).strip()})
            return out
        return []


def format_carry_forward(issues: List[CarryForwardIssue]) -> str:
    """Renders the carry-forward list for the next round's Critic prompt.

    n8n put it through `JSON.stringify` in loop_increment and pasted the result
    straight into the prompt under "# Issues from the previous evaluation". A
    readable list beats a JSON blob for a model being asked to prioritise it, so
    each issue becomes one line carrying the same four fields.
    """
    if not issues:
        return ""
    lines = []
    for index, issue in enumerate(issues, start=1):
        tags = " ".join(part for part in (issue.tag, issue.severity) if part)
        head = f"{index}. {issue.issue}".rstrip()
        if tags:
            head = f"{head} [{tags}]"
        if issue.text:
            # A comma, not an em dash. This string is injected into the Critic
            # prompt as `remaining_issues` on round 2, so a dash here is our own
            # code handing the model the character we forbid it to produce.
            head = f'{head}, exact text: "{issue.text}"'
        lines.append(head)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def word_count(text: Optional[str]) -> int:
    """Whitespace word count, for the UI's per-page figure."""
    if not text:
        return 0
    return len(text.split())
