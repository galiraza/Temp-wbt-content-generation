"""Parsers for the agents' plain-text output.

Ported from the two n8n Code nodes, WF1 "Markdown Formatter" and WF4 "Review
Markdown Formatter". The prompts are kept verbatim, which means the output shape
is the n8n one, which means the parsing has to match. Both parsers follow the
same four steps as the originals: clean, split into blocks, pull each labelled
section out of a block, then lift the hashtag line off the end.

One model call returns all 12 items, statics and reels mixed. parse_posts reads
the static blocks and parse_reels reads the reel blocks, each ignoring the other's
headers, so the same raw text is parsed twice rather than split by hand.
"""

import re
from typing import Dict, List, Optional

from langchain_core.output_parsers import BaseOutputParser

# "Post 3 - Static Post" — the block header the content prompt emits. Hyphen,
# en dash and em dash are all accepted because models substitute them freely.
_POST_HEADER = re.compile(r"^#?\s*Post\s+(\d+)\s*[-–—]\s*Static Post", re.I | re.M)
_REEL_HEADER = re.compile(r"^#?\s*Post\s+(\d+)\s*[-–—]\s*Reel Post", re.I | re.M)
_REVIEW_HEADER = re.compile(r"^#?\s*Review Post\s+(\d+)", re.I | re.M)
# Either kind of item, used only to find where one block ends and the next
# begins. See _split_blocks.
_ITEM_HEADER = re.compile(r"^#?\s*Post\s+\d+\s*[-–—]\s*(?:Static|Reel) Post", re.I | re.M)

# A hashtag line: three or more #tags on one line. The prompts put it last,
# after the CTA block.
_HASHTAG_LINE = re.compile(r"^[ \t]*(#[A-Za-z0-9_]+(?:[ \t]+#[A-Za-z0-9_]+){2,})[ \t]*$", re.M)

_DASH = re.compile(r"\s*[–—]\s*")


def _clean(raw: str) -> str:
    """Step 1 of both n8n formatters: unescape newlines and drop markdown
    emphasis. Agents wrap labels in ** even when the format block does not."""
    return (
        raw.replace("\\n", "\n")
        .replace("**", "")
        .replace("\r\n", "\n")
    )


def _strip_dashes(text: str) -> str:
    """The prompts forbid em/en dashes in every generated field, but models reach
    for them anyway. Same code-level backstop the ad-angle agent uses."""
    return _DASH.sub(", ", text)


def _split_blocks(text: str, header: re.Pattern, boundary: re.Pattern = None) -> List[str]:
    """Step 2: cut the response into one block per item, keeping each header.

    `boundary` is what ends a block, `header` is what starts one worth keeping.
    They differ for the post/reel split: one call returns statics and reels
    interleaved, so a static block has to stop at the next item of EITHER type.
    Cutting only on static headers let a block swallow the reel that followed it,
    and since the hashtags are taken from the last hashtag line in a block, post 1
    would silently end up wearing post 2's reel hashtags.
    """
    edges = sorted(m.start() for m in (boundary or header).finditer(text))
    if not edges:
        return []
    bounds = edges + [len(text)]
    blocks = [text[bounds[i]:bounds[i + 1]].strip() for i in range(len(edges))]
    return [b for b in blocks if header.match(b)]


def _section(block: str, label: str, until: List[str]) -> str:
    """Step 3: the text under `label:` up to whichever of `until` comes first."""
    stop = "|".join(until + [r"\Z"])
    match = re.search(
        rf"{label}\s*:?[ \t]*\n(.*?)(?={stop})",
        block,
        re.S | re.I,
    )
    return match.group(1).strip() if match else ""


def _split_hashtags(block: str) -> List[str]:
    """Step 4: the trailing hashtag line, as a list.

    Takes the LAST matching line, because a caption can legitimately mention a
    hashtag mid-body and the real block is always last.
    """
    matches = _HASHTAG_LINE.findall(block)
    if not matches:
        return []
    return normalise_hashtags(matches[-1].split())


def normalise_hashtags(tags: List[str]) -> List[str]:
    """Force every tag to "#OneWord" and drop duplicates, preserving order.

    Same normalisation the post agent used before: models drop the leading hash,
    split a tag across spaces, or repeat one twice in a block.
    """
    cleaned: List[str] = []
    seen = set()
    for tag in tags:
        collapsed = re.sub(r"[^0-9A-Za-z_]+", "", tag or "")
        if not collapsed:
            continue
        normalised = "#" + collapsed
        key = normalised.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalised)
    return cleaned


def _without_hashtag_line(text: str) -> str:
    """Captions keep their CTA block but not the hashtag line: hashtags are their
    own column, and leaving them in the caption would render them twice."""
    return _HASHTAG_LINE.sub("", text).rstrip()


def parse_posts(raw: str) -> List[Dict]:
    """WF1 "Markdown Formatter", static posts only.

    Returns dicts of post_number / title / caption / hashtags, ordered as the
    agent emitted them.
    """
    text = _clean(raw)
    results: List[Dict] = []

    for block in _split_blocks(text, _POST_HEADER, _ITEM_HEADER):
        header = _POST_HEADER.search(block)
        number = int(header.group(1)) if header else len(results) + 1

        title = _section(block, r"Image/Video Title", [r"Post Caption\s*:", r"\n---"])
        caption = _section(block, r"Post Caption", [r"\n---", r"^#?\s*Post\s+\d+\s*[-–—]"])

        if not title and not caption:
            continue

        results.append(
            {
                "post_number": number,
                # A title that wrapped across lines is one headline, not two.
                "title": _strip_dashes(" ".join(title.split())),
                "caption": _strip_dashes(_without_hashtag_line(caption)),
                "hashtags": _split_hashtags(block),
            }
        )
    return results


def parse_reels(raw: str) -> List[Dict]:
    """The reel blocks of the same response parse_posts reads.

    A reel has no title: the prompt gives it Reel Text (the on-screen script) and
    Reel Caption, and nothing else. Returns dicts of
    reel_number / reel_text / caption / hashtags.
    """
    text = _clean(raw)
    results: List[Dict] = []

    for block in _split_blocks(text, _REEL_HEADER, _ITEM_HEADER):
        header = _REEL_HEADER.search(block)
        number = int(header.group(1)) if header else len(results) + 1

        reel_text = _section(
            block, r"Reel Text(?:\s*\(On-Screen\))?", [r"Reel Caption\s*:", r"\n---"]
        )
        caption = _section(
            block, r"Reel Caption", [r"\n---", r"^#?\s*Post\s+\d+\s*[-–—]"]
        )

        if not reel_text and not caption:
            continue

        results.append(
            {
                "reel_number": number,
                # The on-screen script is multi-line on purpose: each line is a
                # separate text card for the editor, so line breaks are kept.
                "reel_text": _strip_dashes(reel_text),
                "caption": _strip_dashes(_without_hashtag_line(caption)),
                "hashtags": _split_hashtags(block),
            }
        )
    return results


def _split_review_title(post_title: str) -> tuple:
    """The review prompt's Post Title is "Review by: Name - headline".

    Returns (name, headline). Either half may be missing: models sometimes drop
    the "Review by:" prefix, and occasionally give only a headline.
    """
    line = " ".join(post_title.split())
    line = re.sub(r"^\s*Review\s+by\s*:?\s*", "", line, flags=re.I)
    parts = re.split(r"\s*[-–—:]\s*", line, maxsplit=1)
    if len(parts) == 2 and parts[0].strip():
        return parts[0].strip(), parts[1].strip()
    return "", line.strip()


def parse_reviews(raw: str) -> List[Dict]:
    """WF4 "Review Markdown Formatter".

    Returns dicts of review_number / name / title / review / caption / hashtags.
    `review` is the customer's verbatim words, so it gets quote-trimming but no
    dash rewriting — altering it would break the prompt's verbatim rule.
    """
    text = _clean(raw)
    results: List[Dict] = []

    for block in _split_blocks(text, _REVIEW_HEADER):
        header = _REVIEW_HEADER.search(block)
        number = int(header.group(1)) if header else len(results) + 1

        post_title = _section(block, r"Post Title", [r"Review Quote\s*:", r"\n---"])
        quote = _section(block, r"Review Quote", [r"Post Caption\s*:", r"\n---"])
        caption = _section(
            block, r"Post Caption", [r"\n---", r"^#?\s*Review Post\s+\d+"]
        )

        if not quote and not caption:
            continue

        name, headline = _split_review_title(post_title)
        results.append(
            {
                "review_number": number,
                "name": name,
                "title": _strip_dashes(headline),
                "review": quote.strip().strip('"').strip("“”").strip(),
                "caption": _strip_dashes(_without_hashtag_line(caption)),
                "hashtags": _split_hashtags(block),
            }
        )
    return results


def parse_hashtag_pool(raw: str) -> Dict[str, List[str]]:
    """Groups a hashtag agent's tiered output by its tier heading.

    Only used for display and for reuse on a later single-item regeneration; the
    content agents receive the pool as the raw text the researcher returned, so
    they see it exactly as the n8n prompt intended.
    """
    tiers: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in _clean(raw).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^(?:TIER|Type)\s*\d+\s*[-:–—]?\s*(.*)$", stripped, re.I)
        if heading and "#" not in stripped:
            current = re.sub(r"[:\s]+$", "", heading.group(1)).strip() or stripped
            tiers.setdefault(current, [])
            continue
        found = re.findall(r"#[A-Za-z0-9_]+", stripped)
        if found and current:
            tiers[current].extend(normalise_hashtags(found))
    return {k: v for k, v in tiers.items() if v}


# --- LangChain output parsers -------------------------------------------------
# These wrap the functions above so they can sit at the end of an LCEL chain:
#     prompt | llm | PostListParser()
# The parsing logic stays in the plain functions, which keeps it directly
# testable without building a chain.


class PostListParser(BaseOutputParser):
    """Model text -> list of parsed post dicts."""

    def parse(self, text: str) -> List[Dict]:
        return parse_posts(text)

    @property
    def _type(self) -> str:
        return "post_list"


class ReelListParser(BaseOutputParser):
    """Model text -> list of parsed reel dicts."""

    def parse(self, text: str) -> List[Dict]:
        return parse_reels(text)

    @property
    def _type(self) -> str:
        return "reel_list"


class ReviewListParser(BaseOutputParser):
    """Model text -> list of parsed review dicts."""

    def parse(self, text: str) -> List[Dict]:
        return parse_reviews(text)

    @property
    def _type(self) -> str:
        return "review_list"
