# -*- coding: utf-8 -*-
"""Exercise split_blog_output against output shaped like the blog prompt's own
required layout, including the ways models deviate from it: ** wrapping, a
numbered "2. Google My Business Post" heading, missing sections, and the meta
fields sitting inside the blog body rather than above it.

Run: backend/venv/Scripts/python.exe tests/test_blog_parsers.py
"""

import os
import sys

# Resolve the repo from this file, so the suite runs wherever it is checked out.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.blog_generation.parsers import (  # noqa: E402
    QcAudit,
    QcBreakdown,
    split_blog_output,
    word_count,
)

# The layout the prompt asks for: General Notes, the blog, GMB Post, GMB FAQ.
FULL = """\
## General Notes

Word count: 1,480
Keywords used: boiler installation glasgow (3), gas boiler installation glasgow (2)

## The Full Blog

Meta Title: Boiler Installation Glasgow: What It Really Costs
Meta Description: A clear guide to boiler installation in Glasgow, covering costs, timings and what to expect from a qualified installer.

# How Much Does Boiler Installation in Glasgow Cost?

Replacing a boiler is rarely a planned purchase.

## What Affects the Price?

| Factor | Impact |
| --- | --- |
| Boiler type | High |

- Combi boilers suit smaller homes
- System boilers suit larger households

[CTA 1] Speak to our team for tailored advice.

## Frequently Asked Questions

**How long does it take?** Usually one day.

## 2. Google My Business Post

Thinking about a new boiler this winter? Our Glasgow team can talk you through
costs and timings. Get in touch for a bespoke quote.

## 3. GMB FAQ

**How much does boiler installation in Glasgow cost?** Most installations range
from £1,800 to £3,500 depending on the boiler type and the work involved.
"""

# Emphasis instead of headings, and no General Notes at all.
NO_NOTES = """\
**Meta Title:** Solar Panels Falkirk: A Simple Guide
**Meta Description:** What solar panels cost in Falkirk and how much you could save.

# Are Solar Panels Worth It in Falkirk?

Solar has changed a lot in five years.

**GMB Post**

Considering solar in Falkirk? Here's what it really costs.

**GMB FAQ**

**Do solar panels work in Scotland?** Yes - daylight matters more than heat.
"""

# The failure case worth handling: the model ignored the layout entirely.
BARE = """\
# Insulation Grants in Cardiff

Loft insulation is the cheapest upgrade most homes can make.
"""

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append("%s\n   expected: %r\n   actual:   %r" % (label, expected, actual))


def contains(label, haystack, needle):
    if not haystack or needle not in haystack:
        failures.append("%s\n   %r not found in %r" % (label, needle, (haystack or "")[:120]))


def absent(label, haystack, needle):
    if haystack and needle in haystack:
        failures.append("%s\n   %r should NOT be in %r" % (label, needle, haystack[:120]))


# --- the full, well-formed layout -----------------------------------------
full = split_blog_output(FULL)

check("full meta_title", full["meta_title"], "Boiler Installation Glasgow: What It Really Costs")
contains("full meta_description", full["meta_description"], "clear guide to boiler installation")
contains("full general_notes", full["general_notes"], "Word count: 1,480")
contains("full content keeps the body", full["content"], "Replacing a boiler is rarely")
contains("full content keeps the table", full["content"], "| Factor | Impact |")
contains("full content keeps the CTA marker", full["content"], "[CTA 1]")
contains("full gmb_post", full["gmb_post"], "Thinking about a new boiler")
contains("full gmb_faq", full["gmb_faq"], "£1,800 to £3,500")

# The three outputs must not bleed into each other.
absent("gmb_post not in content", full["content"], "Thinking about a new boiler")
absent("gmb_faq not in content", full["content"], "£1,800 to £3,500")
absent("gmb_faq not in gmb_post", full["gmb_post"], "£1,800 to £3,500")
absent("blog body not in gmb_post", full["gmb_post"], "Replacing a boiler")
absent("notes not in content", full["content"], "Keywords used:")

# --- emphasis-marked headings, no General Notes ---------------------------
no_notes = split_blog_output(NO_NOTES)

check("no_notes general_notes is None", no_notes["general_notes"], None)
check("no_notes meta_title", no_notes["meta_title"], "Solar Panels Falkirk: A Simple Guide")
contains("no_notes content", no_notes["content"], "Solar has changed a lot")
contains("no_notes gmb_post", no_notes["gmb_post"], "Considering solar in Falkirk")
contains("no_notes gmb_faq", no_notes["gmb_faq"], "daylight matters more than heat")
absent("no_notes gmb_post not in content", no_notes["content"], "Considering solar in Falkirk")

# --- the model ignored the format -----------------------------------------
bare = split_blog_output(BARE)

contains("bare keeps the content", bare["content"], "Loft insulation is the cheapest")
check("bare gmb_post is None", bare["gmb_post"], None)
check("bare gmb_faq is None", bare["gmb_faq"], None)
check("bare meta_title is None", bare["meta_title"], None)

# --- empty input must not raise -------------------------------------------
empty = split_blog_output("")
check("empty content", empty["content"], None)
empty_none = split_blog_output(None)
check("None content", empty_none["content"], None)

# --- word_count strips markdown ------------------------------------------
check("word_count ignores markdown syntax", word_count("## Hi **there** | - |"), 2)
check("word_count of None", word_count(None), 0)

# --- the QC pass rule is the score, not the label -------------------------
# The model has been seen writing "PASS" next to a failing number; the threshold
# is what the prompt actually defines, so the number wins.
check("score 7 passes", QcAudit(score=7, result="FAIL").passed, True)
check("score 6 fails despite PASS label", QcAudit(score=6, result="PASS").passed, False)
check("score 10 passes", QcAudit(score=10, result="PASS").passed, True)

# --- the breakdown defaults to zeros rather than blowing up ---------------
audit = QcAudit(score=8, result="PASS")
check("breakdown default", audit.breakdown.model_dump(), QcBreakdown().model_dump())
check("breakdown has 8 areas", len(QcBreakdown().model_dump()), 8)


# Taken from a real run against claude-sonnet-4-6: the model put the meta fields
# INSIDE the General Notes block, below the keyword list, rather than in the blog
# body. Both are legitimate readings of the prompt, which asks for the notes and
# the meta fields at "the start of the blog". Parsing only the body missed them.
REAL_RUN_NOTES_META = """## General Notes

**Word Count:** Approximately 1,150 words

**Keywords Used:**
- **Keyword 1:** lead generation for tradespeople (target: 3 uses)
- **Keyword 2:** trade business leads (target: 2 uses)

---

**Meta Title:** How Do Trade Businesses Get More Leads Online?

**Meta Description:** Struggling to win more work online? Discover proven strategies for lead generation for tradespeople in Glasgow.

# How Do Trade Businesses Get More Leads Online?

Getting a steady flow of enquiries is one of the biggest challenges facing tradespeople.

## Why Is a Website Not Enough?

It needs traffic, and traffic needs a strategy.

## Google My Business Post

Tired of quiet spells between jobs? Our team helps trades build a steady pipeline.

## GMB FAQ

**How do trade businesses get more leads online?** Through local search, targeted ads
and a steady flow of reviews.
"""

real = split_blog_output(REAL_RUN_NOTES_META)

check("real-run meta_title from notes", real["meta_title"],
      "How Do Trade Businesses Get More Leads Online?")
contains("real-run meta_description from notes", real["meta_description"],
         "Struggling to win more work online")
contains("real-run notes keep the word count", real["general_notes"], "Approximately 1,150 words")
contains("real-run content starts at the H1", real["content"],
         "# How Do Trade Businesses Get More Leads Online?")
contains("real-run gmb_post", real["gmb_post"], "Tired of quiet spells")
contains("real-run gmb_faq", real["gmb_faq"], "local search, targeted ads")
absent("real-run meta not left in content", real["content"], "Meta Title")
absent("real-run notes not left in content", real["content"], "Keywords Used")

# --- QcAudit must survive a junk breakdown ------------------------------------
# A live run returned `"breakdown": "[object Object]"`, and strict validation
# failed the whole audit, discarding a blog that had already been written.
junk = QcAudit(score=8, result="PASS", word_count=1229, breakdown="[object Object]")
check("junk breakdown does not raise", junk.score, 8)
check("junk breakdown degrades to zeros",
      all(v == 0 for v in junk.breakdown.model_dump().values()), True)
check("real breakdown still parses",
      QcAudit(score=9, result="PASS",
              breakdown={"word_count": 1, "uk_grammar": 2, "structure": 1, "keywords": 2,
                         "funnel_stage": 1, "brand_alignment": 1, "no_emoji": 1,
                         "cta_strength": 0}).breakdown.uk_grammar, 2)

# fixes_required arrives as a " | "-joined string from some replies.
check("pipe-joined fixes split",
      QcAudit(score=5, result="FAIL", fixes_required="a | b | c").fixes_required,
      ["a", "b", "c"])
check("None fixes", QcAudit(score=5, result="FAIL", fixes_required=None).fixes_required, [])



# --- extraction MOVES the meta fields, it does not copy them ------------------
# They get their own columns, so leaving the source line in the notes made the
# blog viewer render the meta title and description twice: once from the notes
# block, once from the column. Every source block must lose the line it gave up.
moved = split_blog_output(REAL_RUN_NOTES_META)

absent("meta title moved out of notes", moved["general_notes"], "Meta Title")
absent("meta description moved out of notes", moved["general_notes"], "Meta Description")
absent("meta title not left in content", moved["content"], "Meta Title")
absent("meta description not left in content", moved["content"], "Meta Description")
# ...while everything the notes block is actually for survives.
contains("notes keep the word count", moved["general_notes"], "Approximately 1,150 words")
contains("notes keep the keyword list", moved["general_notes"], "Keyword 1")
check("meta title still captured", moved["meta_title"],
      "How Do Trade Businesses Get More Leads Online?")

# The same, with the meta fields in the BODY instead of the notes.
body_meta = split_blog_output(FULL)
check("body meta title captured", body_meta["meta_title"],
      "Boiler Installation Glasgow: What It Really Costs")
absent("body meta title moved out of content", body_meta["content"], "Meta Title:")
absent("body meta description moved out of content", body_meta["content"], "Meta Description:")
contains("body content otherwise intact", body_meta["content"], "Replacing a boiler is rarely")

# A stitched document must mention each meta field exactly once. This is the
# assertion that would have caught the duplication the viewer showed.
def _count(haystack, needle):
    return (haystack or "").count(needle)

stitched = "\n\n".join(
    part for part in (
        moved["general_notes"],
        f"**Meta Title:** {moved['meta_title']}",
        f"**Meta Description:** {moved['meta_description']}",
        moved["content"],
    ) if part
)
check("stitched doc has one Meta Title", _count(stitched, "Meta Title"), 1)
check("stitched doc has one Meta Description", _count(stitched, "Meta Description"), 1)


if failures:
    print("FAILED (%d)" % len(failures))
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all blog parser tests passed")
