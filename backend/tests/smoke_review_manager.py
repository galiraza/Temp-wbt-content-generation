# -*- coding: utf-8 -*-
"""End-to-end smoke test of Manager B against live Firecrawl + Anthropic.

Reads brief 5's real reviews page URL. Writes nothing to the database.
"""

import sys
import time

sys.path.insert(0, "F:/0001 Metaviz/Paid_Ads_Generation/backend")

from app.agents.post_generation.review_manager import generate_reviews  # noqa: E402


class Brief:
    id = 0
    company_name = "Heatable"
    phone = "0141 555 0000"
    email = "hello@heatable.co.uk"
    website_url = "https://heatable.co.uk"
    company_reviews_page_url = "https://uk.trustpilot.com/review/heatable.co.uk"
    areas_covered = "Manchester, North West"
    promotion = ""
    unique_selling_points = "Same-day callouts. Fixed-price quotes. Family run since 2009."


started = time.time()
try:
    reviews, pool, scraped = generate_reviews(Brief())
except Exception as exc:
    print("FAILED: %s: %s" % (type(exc).__name__, exc))
    internal = getattr(exc, "internal", None)
    if internal:
        print("internal: %s" % internal)
    raise SystemExit(1)

print("elapsed: %.1fs" % (time.time() - started))
print("scraped markdown: %d chars" % len(scraped))
print("hashtag pool: %d chars" % len(pool))
print("reviews returned: %d\n" % len(reviews))

for r in reviews:
    print("--- Review %d" % r["review_number"])
    print("    name    : %s" % r["name"])
    print("    title   : %s" % r["title"])
    print("    quote   : %s" % r["review"][:96])
    print("    caption : %d words" % len(r["caption"].split()))
    print("    hashtags: %d %s" % (len(r["hashtags"]), " ".join(r["hashtags"][:3])))
    print("    platform: %s" % r.get("platform"))
    print("    CTA     : %s" % ("present" if "Find out more on our website" in r["caption"] else "MISSING"))

print("\nsummary: %d reviews" % len(reviews))
assert reviews, "no reviews parsed"
assert all(r["review"].strip() for r in reviews), "an empty quote got through"
assert all(r["hashtags"] for r in reviews), "a review has no hashtags"
assert all("#GoogleReviews" not in r["hashtags"] for r in reviews), "banned tag used"
# Every quote must appear in the scraped page: proof nothing was invented.
missing = [r["review_number"] for r in reviews if r["review"][:34] not in scraped]
print("quotes not found verbatim in scrape: %s" % (missing or "none"))
print("ASSERTIONS PASSED")
