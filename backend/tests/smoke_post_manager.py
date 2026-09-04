# -*- coding: utf-8 -*-
"""End-to-end smoke test of Manager A against the live Anthropic API.

Uses a throwaway in-memory brief, writes nothing to the database. Manager A only,
so the run stays cheap: it exercises the web-search hashtag researcher, the
content agent, and the parser, which is where the risk is.
"""

import sys
import time

sys.path.insert(0, "F:/0001 Metaviz/Paid_Ads_Generation/backend")

from app.agents.post_generation.post_manager import generate_posts  # noqa: E402
from app.models.post_generation.post import POST_THEMES  # noqa: E402


class Brief:
    """Duck-types the columns the manager reads off a PostGenerationRequest."""

    id = 0
    company_name = "Stewart Temperature Solutions"
    phone = "01292 738598"
    email = "info@stewart-temp-solutions.com"
    website_url = "https://stewart-temp-solutions.com/"
    month = "September"
    industry = "Air Conditioning and Heat Pumps"
    main_topic = "Air source heat pump installation"
    promotion = "Free home survey through September"
    fixed_rules = "Never mention competitor names. Always mention the free survey."
    additional_resources = ""
    additional_notes = ""
    areas_covered = "Ayrshire, Glasgow"
    unique_selling_points = (
        "Government grant paperwork handled for you. "
        "Single-day installation. Ten year workmanship warranty."
    )


started = time.time()
posts, pool = generate_posts(Brief())
elapsed = time.time() - started

print("elapsed: %.1fs" % elapsed)
print("hashtag pool: %d chars" % len(pool))
print("posts returned: %d\n" % len(posts))

for p in posts:
    words = len(p["caption"].split())
    print("--- Post %d [%s]" % (p["post_number"], p["theme"]))
    print("    title   : %s" % p["title"])
    print("    caption : %d words, %d chars" % (words, len(p["caption"])))
    print("    first   : %s" % p["caption"].splitlines()[0][:88])
    print("    hashtags: %d %s" % (len(p["hashtags"]), " ".join(p["hashtags"][:4])))
    has_cta = "Find out more on our website" in p["caption"]
    print("    CTA     : %s" % ("present" if has_cta else "MISSING"))
    placeholder = "not returned" in p["title"]
    print("    status  : %s" % ("PLACEHOLDER (parse gap)" if placeholder else "real"))

real = [p for p in posts if "not returned" not in p["title"]]
print("\nsummary: %d/%d real, %d placeholders" % (len(real), len(posts), len(posts) - len(real)))
assert len(posts) == 8, "expected 8 posts"
assert [p["theme"] for p in posts] == POST_THEMES, "themes not in slot order"
assert all(p["hashtags"] for p in real), "a real post came back with no hashtags"
assert all("Find out more on our website" in p["caption"] for p in real), "CTA missing"
assert all("—" not in p["caption"] for p in real), "em dash survived"
print("ASSERTIONS PASSED")
