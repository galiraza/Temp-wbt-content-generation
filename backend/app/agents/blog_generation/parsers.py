"""Schemas and parsers for the blog agents' output.

Replaces the two n8n Code nodes:

  "Metadata Formatter"  regex-stripped a ```json fence, JSON.parse'd it, and
                        fanned it out into a hardcoded 12 items.
  "QC Formatter"        the same fence-stripping and JSON.parse on the audit.

Both are gone. The metadata extractor and the QC agent are bound to the Pydantic
schemas below via structured_llm(), so LangChain validates the reply and asks
again on a mismatch. In n8n a single malformed reply threw inside JSON.parse and
aborted the entire run, taking every remaining blog with it.

What still needs real parsing is the Blog Agent, which returns prose in a fixed
layout rather than JSON: General Notes, the blog, a GMB Post and a GMB FAQ, with
the meta title and description inside the blog body. split_blog_output reads that
layout back.
"""

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# Structured schemas — what the model is constrained to return
# --------------------------------------------------------------------------


class BlogMetadata(BaseModel):
    """One blog's brief, as parsed out of the pasted content plan."""

    blog_number: int = Field(description="Sequential number of the blog, starting at 1")
    blog_title: str = Field(description="The blog's exact title from the plan")
    funnel_stage: Optional[str] = Field(
        default=None,
        description="Informational, Commercial, Transactional or Navigational",
    )
    service_areas: List[str] = Field(
        default_factory=list, description="Locations this blog targets"
    )
    keywords: List[str] = Field(
        default_factory=list, description="Target keywords, in their labelled order"
    )


class BlogMetadataList(BaseModel):
    """The extractor's whole reply. The n8n prompt asked for exactly 12; the
    count is taken from what is actually returned instead, and reconciled against
    the request's cluster_number by the caller."""

    blogs: List[BlogMetadata] = Field(default_factory=list)


class QcBreakdown(BaseModel):
    """The eight weighted sub-scores, totalling 10. Names and weights are the QC
    prompt's own scoring table."""

    word_count: int = 0        # out of 1
    uk_grammar: int = 0        # out of 2
    structure: int = 0         # out of 1
    keywords: int = 0          # out of 2
    funnel_stage: int = 0      # out of 1
    brand_alignment: int = 0   # out of 1
    no_emoji: int = 0          # out of 1
    cta_strength: int = 0      # out of 1


class QcAudit(BaseModel):
    """One QC verdict. Mirrors the JSON block the QC prompt specifies.

    The two `before` validators exist because a malformed sub-field must not cost
    a whole blog. Seen in a live run: the model returned
    `"breakdown": "[object Object]"` — a JS-stringified object — and strict
    validation failed the entire audit, discarding a blog that had already been
    written. The score, verdict and fixes were all fine; only the sub-score
    breakdown was junk. Losing 1,229 words over that is the wrong trade, so an
    unreadable breakdown degrades to zeros and the audit still lands.
    """

    blog_number: Optional[int] = None
    score: int = Field(description="Total score out of 10")
    result: str = Field(description="PASS or FAIL")
    word_count: Optional[int] = None
    fixes_required: List[str] = Field(default_factory=list)
    breakdown: QcBreakdown = Field(default_factory=QcBreakdown)

    @field_validator("breakdown", mode="before")
    @classmethod
    def _coerce_breakdown(cls, value):
        """Anything that is not a mapping becomes an all-zero breakdown.

        Zeros rather than a guess: the sub-scores drive nothing but the display,
        and inventing them would misreport what the auditor actually said. The
        total in `score` is what the pass/fail decision uses.
        """
        if value is None:
            return QcBreakdown()
        if isinstance(value, (dict, QcBreakdown)):
            return value
        return QcBreakdown()

    @field_validator("fixes_required", mode="before")
    @classmethod
    def _coerce_fixes(cls, value):
        """Accepts the " | "-joined string form as well as a list.

        The n8n QC Formatter joined the fixes with " | " before storing them, so
        a model that has seen that shape sometimes returns the joined string.
        """
        if value is None:
            return []
        if isinstance(value, str):
            parts = [p.strip() for p in value.replace("\n", " | ").split("|")]
            return [p for p in parts if p]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return []

    @property
    def passed(self) -> bool:
        """Scored on the number, not on `result`.

        The two can disagree — the model has been seen to write "PASS" next to a
        6 — and the threshold is the rule the prompt actually defines. Comparing
        against the number keeps one source of truth.
        """
        from app.models.blog_generation.blog import PASS_THRESHOLD

        return self.score >= PASS_THRESHOLD


# --------------------------------------------------------------------------
# Blog body parsing
# --------------------------------------------------------------------------

#: The prompt names its three outputs in this order: General Notes, the blog
#: itself, the GMB Post, the GMB FAQ. Models mark them up inconsistently — with
#: or without a leading #, with "Google My Business Post" spelled out, wrapped in
#: ** — so each heading is matched loosely and anchored to the start of a line.
_GMB_POST_HEADER = re.compile(
    r"^\s*#{0,6}\s*\**\s*(?:\d\.\s*)?(?:Google My Business Post|GMB Post)\b[^\n]*\n",
    re.I | re.M,
)
_GMB_FAQ_HEADER = re.compile(
    r"^\s*#{0,6}\s*\**\s*(?:\d\.\s*)?(?:GMB FAQ|Google My Business FAQ)\b[^\n]*\n",
    re.I | re.M,
)
_GENERAL_NOTES_HEADER = re.compile(
    r"^\s*#{0,6}\s*\**\s*General Notes\b[^\n]*\n", re.I | re.M
)
_BLOG_HEADER = re.compile(
    r"^\s*#{0,6}\s*\**\s*(?:\d\.\s*)?(?:The Full Blog|Full Blog|The Blog)\b[^\n]*\n",
    re.I | re.M,
)

_META_TITLE = re.compile(
    r"^\s*#{0,6}\s*\**\s*Meta Title\**\s*[:\-]?\s*(.+?)\s*$", re.I | re.M
)
_META_DESCRIPTION = re.compile(
    r"^\s*#{0,6}\s*\**\s*Meta Description\**\s*[:\-]?\s*(.+?)\s*$", re.I | re.M
)


def _strip(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = text.strip().strip("-").strip()
    return cleaned or None


def _tidy_block(text: Optional[str]) -> Optional[str]:
    """Cleans up what removing a line leaves behind.

    Pulling the meta lines out of a block can leave a run of blank lines, or a
    "---" separator that now separates nothing. Collapsing them keeps the stored
    markdown looking hand-written rather than machine-gutted.
    """
    if not text:
        return text
    cleaned = re.sub(r"\n{3,}", "\n\n", text)
    # A separator with nothing but whitespace after it, at either end.
    cleaned = re.sub(r"^\s*-{3,}\s*$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _tidy_value(value: Optional[str]) -> Optional[str]:
    """A meta field captured off a heading line can keep stray emphasis."""
    if not value:
        return None
    return _strip(value.replace("**", "").strip().strip('"').strip())


def split_blog_output(raw: str) -> Dict[str, Optional[str]]:
    """Splits one Blog Agent reply into its parts.

    Returns content / gmb_post / gmb_faq / meta_title / meta_description /
    general_notes. Anything the model omitted comes back None rather than raising
    — a blog missing its GMB FAQ is still a blog worth showing and editing, and
    the QC agent is the thing that judges completeness.

    The sections are located from the end backwards (FAQ, then Post), because
    each header is the terminator of the section before it.
    """
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return {
            "content": None,
            "gmb_post": None,
            "gmb_faq": None,
            "meta_title": None,
            "meta_description": None,
            "general_notes": None,
        }

    gmb_faq = None
    faq_match = _GMB_FAQ_HEADER.search(text)
    if faq_match:
        gmb_faq = text[faq_match.end():]
        text = text[: faq_match.start()]

    gmb_post = None
    post_match = _GMB_POST_HEADER.search(text)
    if post_match:
        gmb_post = text[post_match.end():]
        text = text[: post_match.start()]

    general_notes = None
    notes_match = _GENERAL_NOTES_HEADER.search(text)
    if notes_match:
        # The notes block runs until the blog's own heading, if the model emitted
        # one; otherwise until the first markdown H1/H2 after it.
        rest = text[notes_match.end():]
        blog_match = _BLOG_HEADER.search(rest)
        if blog_match:
            general_notes = rest[: blog_match.start()]
            body = rest[blog_match.end():]
        else:
            next_heading = re.search(r"^#{1,2}\s+\S", rest, re.M)
            if next_heading:
                general_notes = rest[: next_heading.start()]
                body = rest[next_heading.start():]
            else:
                general_notes = rest
                body = ""
        text = body
    else:
        blog_match = _BLOG_HEADER.search(text)
        if blog_match:
            text = text[blog_match.end():]

    # The meta fields are searched for in the body first and then in the General
    # Notes block. The prompt asks for the word count and keywords under
    # "## General Notes" *and* for the meta title and description "at the start of
    # the blog", so both end up competing for the same position — in live runs the
    # model has put them inside the notes block, below the keyword list. Looking
    # only at the body missed them entirely.
    #
    # Extraction MOVES each value rather than copying it. They get their own
    # columns, so leaving the source line where it was meant every consumer that
    # renders the notes AND the columns showed the meta title and description
    # twice — which is exactly what the blog viewer did.
    def _take(pattern):
        nonlocal text, general_notes
        value = None
        if text:
            match = pattern.search(text)
            if match:
                value = _tidy_value(match.group(1))
                text = pattern.sub("", text)
        if general_notes:
            match = pattern.search(general_notes)
            if match:
                if value is None:
                    value = _tidy_value(match.group(1))
                general_notes = pattern.sub("", general_notes)
        return value

    meta_title = _take(_META_TITLE)
    meta_description = _take(_META_DESCRIPTION)

    return {
        "content": _strip(_tidy_block(text)),
        "gmb_post": _strip(gmb_post),
        "gmb_faq": _strip(gmb_faq),
        "meta_title": meta_title,
        "meta_description": meta_description,
        "general_notes": _strip(_tidy_block(general_notes)),
    }


def word_count(text: Optional[str]) -> int:
    """Words in the blog body, for showing next to the QC agent's own count.

    Markdown syntax is stripped first so a table-heavy blog is not credited for
    its pipes and dashes.
    """
    if not text:
        return 0
    plain = re.sub(r"[#*_>`|\-]+", " ", text)
    return len(plain.split())
