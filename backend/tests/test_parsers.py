# -*- coding: utf-8 -*-
"""Exercise the parsers against output shaped like the prompts' own examples,
including the ways models deviate: ** wrapping, --- separators, wrapped titles,
em dashes, a missing "Review by:" prefix, and a stray hashtag mid-caption.
"""

import sys

sys.path.insert(0, "F:/0001 Metaviz/Paid_Ads_Generation/backend")

from app.agents.post_generation.parsers import (  # noqa: E402
    parse_hashtag_pool,
    parse_posts,
    parse_reviews,
)

POSTS = """\
Post 1 - Static Post

Image/Video Title:
Cut Bills, Not Comfort: Choose an Air Source
Heat Pump This Winter

Post Caption:
Your heating bill doesn't have to be the most stressful part of winter.

Thousands of UK homeowners are switching and saving up to 70%.

At Stewart Temperature Solutions, we handle everything.

\U0001f310 Find out more on our website! https://example.com/
\U0001f4de Give us a call: 01292 738598
\U0001f4e7 Or send us an email at info@example.com

#StewartTemperatureSolutions #HeatPumpUK #AirSourceHeatPump #Ayrshire #WarmHome

---

**Post 2 - Static Post**

**Image/Video Title:**
Think Heat Pumps Don't Work in Cold Weather — Here's the Truth

**Post Caption:**
One of the biggest myths holding UK homeowners back.

Modern units operate efficiently down to -20C.

We've installed systems across Ayrshire.

\U0001f310 Find out more on our website! https://example.com/
\U0001f4de Give us a call: 01292 738598

#StewartTemperatureSolutions #MythBusting #GreenHeating #Ayrshire #EcoHome #UKHomes

---
"""

REVIEWS = """\
Review Post 1

Post Title:
Review by: Sarah M - Fast, Tidy And Fixed First Time

Review Quote:
"They arrived on time, were spotlessly tidy, and had it fixed within the hour."

Post Caption:
Sarah, this is exactly what we aim for on every visit \U0001f60a

Being on time and leaving a clean home is not extra, it is the job.

We'd love to help you experience the same, so get in touch today!

\U0001f310 Find out more on our website! https://example.com/

#StewartTemperatureSolutions #CustomerReviews #TrustedLocal #FiveStar #HappyCustomer

---

Review Post 2

Post Title:
James P — Honest Advice, No Pressure

Review Quote:
Gave me honest advice and never once tried to upsell me. Refreshing.

Post Caption:
James, honest advice is the whole point \U0001f44f Mentioning #trust here mid-caption.

That is how we would want to be treated ourselves.

Get in touch and see for yourself!

\U0001f310 Find out more on our website! https://example.com/

#StewartTemperatureSolutions #HonestService #NoPressure #LocalTrade #Recommended
"""

POOL = """\
TIER 1 - BROAD REACH:
#UKHomes #HomeImprovement #WinterReady

TIER 2 - TOPIC SPECIFIC:
#HeatPumpUK #AirSourceHeatPump #EnergyEfficiency

TIER 3 - NICHE AND LOCAL (must include location tags):
#Ayrshire #AyrshireHomes #ScotlandHeating
"""

posts = parse_posts(POSTS)
print("POSTS parsed: %d" % len(posts))
for p in posts:
    print("  #%d title=%r" % (p["post_number"], p["title"]))
    print("     tags=%s" % p["hashtags"])
    print("     caption ends: %r" % p["caption"][-46:])
    assert "#" not in p["caption"], "hashtag line leaked into caption"
    assert "—" not in p["title"] and "–" not in p["title"], "dash not stripped"

reviews = parse_reviews(REVIEWS)
print("\nREVIEWS parsed: %d" % len(reviews))
for r in reviews:
    print("  #%d name=%r title=%r" % (r["review_number"], r["name"], r["title"]))
    print("     review=%r" % r["review"][:58])
    print("     tags=%s" % r["hashtags"])
    assert r["review"] and not r["review"].startswith('"'), "quote not trimmed"

pool = parse_hashtag_pool(POOL)
print("\nPOOL tiers: %d" % len(pool))
for tier, tags in pool.items():
    print("  %s -> %d tags %s" % (tier[:34], len(tags), tags[:3]))

assert len(posts) == 2, "expected 2 posts"
assert posts[0]["title"].startswith("Cut Bills, Not Comfort"), posts[0]["title"]
assert "\n" not in posts[0]["title"], "wrapped title not joined"
assert len(posts[0]["hashtags"]) == 5
assert len(reviews) == 2, "expected 2 reviews"
assert reviews[0]["name"] == "Sarah M", reviews[0]["name"]
assert reviews[1]["name"] == "James P", reviews[1]["name"]
assert len(reviews[1]["hashtags"]) == 5, reviews[1]["hashtags"]
assert len(pool) == 3
print("\nALL ASSERTIONS PASSED")
