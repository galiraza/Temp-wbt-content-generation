"""The cross-page uniqueness reconcile.

The second half of what splitting the bundled page agents costs. The first half
is the sibling openings each single-page task is handed while the run is still
going; this is the pass that sees every finished page at once, which is the view
the bundled reply used to have.

Two stages, deliberately:

  find     pure Python. Normalise every sentence, count which ones appear on
           more than one page, drop the ones that are allowed to. No model call,
           so a run with no duplication costs nothing here and, more usefully,
           the model is never asked to judge whether something is a duplicate.
  rewrite  one model call per offending page, and only for pages that have an
           offence. Given the exact sentences to replace and told to change
           nothing else.

The find stage being deterministic is the point. A model asked "are these pages
too similar" will always find something, and the trust bar and the sitewide call
to action are the most repeated text on the site, so it finds those first. Here
they are excluded before the model is involved at all.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from langchain_core.prompts import ChatPromptTemplate

from app.agents.website_content.client import text_llm
from app.services.content_run.tasks import TaskResult

logger = logging.getLogger(__name__)

#: Sentences shorter than this are not duplication, they are English.
#:
#: "Get in touch." appearing on nine pages is not a finding. Measured in words
#: rather than characters because a short heading and a long one are the same
#: kind of thing at different lengths.
_MIN_WORDS = 6

#: Headings whose block is meant to be identical on every page, so nothing
#: inside them counts.
#:
#: These are the "MAY be consistent" list from the CROSS-PAGE UNIQUENESS block
#: in service_page_prompt.py, kept in the same words. If that block is ever
#: edited, this has to move with it: the prompt promises the copy will be
#: identical here, and a dedupe pass that then rewrites it makes the prompt a
#: liar in a way nobody would think to look for.
_EXEMPT_HEADINGS = (
    "why choose",
    "areas we cover",
    "area we cover",
    "trust",
    "accreditation",
    "get in touch",
    "contact",
    "ready to",
    "next step",
    "what happens next",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _normalise(text: str) -> str:
    """Case, punctuation and whitespace removed, so near misses collide.

    Aggressive on purpose. The failure being caught is the same sentence with a
    different noun or a comma moved, and an exact-string comparison misses all
    of it.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _blocks(page: str) -> List[Tuple[str, str]]:
    """Splits a page into (heading, body) pairs, so headings can be exempted.

    Text before the first heading belongs to no heading and is returned under
    an empty one, which is correct: the H1 and the hero line sit there and they
    are the two things that must be unique.
    """
    out: List[Tuple[str, str]] = []
    heading = ""
    buffer: List[str] = []
    for line in (page or "").splitlines():
        if line.lstrip().startswith("#"):
            if buffer:
                out.append((heading, "\n".join(buffer)))
                buffer = []
            heading = line.lstrip("# ").strip()
        else:
            buffer.append(line)
    if buffer:
        out.append((heading, "\n".join(buffer)))
    return out


def _is_exempt(heading: str) -> bool:
    low = heading.lower()
    return any(marker in low for marker in _EXEMPT_HEADINGS)


def _sentences(page: str) -> List[str]:
    """Every sentence that is allowed to be judged, headings included.

    A repeated H1 is the worst version of this problem, so headings are
    returned as sentences in their own right rather than skipped.
    """
    picked: List[str] = []
    for heading, body in _blocks(page):
        if _is_exempt(heading):
            continue
        if heading:
            picked.append(heading)
        for raw in _SENTENCE_SPLIT.split(body):
            line = raw.strip().lstrip("-*").strip()
            if line and len(line.split()) >= _MIN_WORDS:
                picked.append(line)
    return picked


def find_duplicates(pages: Dict[str, str]) -> Dict[str, List[str]]:
    """Which pages carry a sentence that also appears on another page.

    Keyed by page key, valued with that page's own offending sentences in their
    original wording, because that is what the rewrite call has to be given.

    The first page to use a sentence keeps it. Arbitrary but necessary: some
    page has to, and rewriting all of them would churn copy that is fine.
    """
    seen: Dict[str, str] = {}
    offences: Dict[str, List[str]] = defaultdict(list)

    for key, page in pages.items():
        for sentence in _sentences(page):
            norm = _normalise(sentence)
            if len(norm.split()) < _MIN_WORDS:
                continue
            owner = seen.get(norm)
            if owner is None:
                seen[norm] = key
            elif owner != key:
                offences[key].append(sentence)

    return {key: value for key, value in offences.items() if value}


_REWRITE_SYSTEM = """You are fixing duplicated copy on one page of a website.

Several pages were written at the same time by different writers, so a few
sentences ended up on more than one page. You are given one page and the exact
sentences on it that also appear elsewhere.

Rewrite ONLY those sentences. Say the same thing about the same service in
different words. Everything else on the page stays exactly as it is, character
for character: same headings, same order, same structure, same length.

Do not improve anything. Do not shorten. Do not reorder. Do not add. If a
sentence is not in the list, it is not yours to touch.

Never use a dash as sentence punctuation. Not the em dash, not the en dash, not
a double hyphen. This applies to the sentences you write as replacements.

Return the complete page, with those sentences replaced and nothing else
changed."""

_REWRITE_USER = """The service or area this page is about: {subject}

The sentences to replace, exactly as they appear on the page:
{offences}

The page:
{page}"""


def _rewrite(page: str, subject: str, offences: List[str], label: str) -> str:
    """One model call for one page. Returns the page unchanged on any failure.

    Returning the original rather than raising is the right trade here: the page
    is good copy that happens to share a sentence with a sibling, and losing it
    over a failed cosmetic pass would be much worse than shipping the repeat.
    """
    template = ChatPromptTemplate.from_messages(
        [("system", _REWRITE_SYSTEM), ("user", _REWRITE_USER)]
    )
    # text_llm, not structured_llm: the reply is a whole markdown page rather
    # than a schema, and text_llm already applies the shared dash guardrail and
    # distinguishes a refusal from a truncation.
    try:
        text = (template | text_llm(label=label)).invoke(
            {
                "subject": subject,
                "offences": "\n".join(f"- {line}" for line in offences),
                "page": page,
            }
        )
    except Exception:
        logger.exception("dedupe_rewrite_failed label=%s", label)
        return page

    text = (text or "").strip()

    # A rewrite that lost most of the page is a failed rewrite, not a shorter
    # page. The pass is meant to swap a handful of sentences, so anything under
    # three quarters of the original means the model summarised instead, and the
    # original is the better answer.
    if len(text) < len(page) * 0.75:
        logger.warning(
            "dedupe_rewrite_too_short label=%s before=%s after=%s",
            label,
            len(page),
            len(text),
        )
        return page
    return text


def reconcile_pages(results: List[TaskResult], brief: Dict) -> Dict[str, str]:
    """Finds duplication across a run's pages and rewrites only what repeats.

    Returns the bodies that changed, keyed by task key, which is the contract
    `Plan.reconcile` has: a run with no duplication returns {} and the caller
    writes nothing.
    """
    pages = {r.task.key: r.body for r in results if r.ok and r.body}
    if len(pages) < 2:
        return {}

    offences = find_duplicates(pages)
    if not offences:
        logger.info("dedupe_clean pages=%s", len(pages))
        return {}

    logger.info(
        "dedupe_found pages=%s affected=%s sentences=%s",
        len(pages),
        len(offences),
        sum(len(v) for v in offences.values()),
    )

    by_key = {r.task.key: r for r in results}
    changed: Dict[str, str] = {}
    for key, sentences in offences.items():
        result = by_key[key]
        subject = result.task.payload.get("subject") or result.task.title
        rewritten = _rewrite(pages[key], subject, sentences, label=f"dedupe-{key}")
        if rewritten != pages[key]:
            changed[key] = rewritten

    logger.info("dedupe_rewritten pages=%s", len(changed))
    return changed
