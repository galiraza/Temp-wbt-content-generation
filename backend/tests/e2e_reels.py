# -*- coding: utf-8 -*-
"""End-to-end test of reels against the running dev server.

Proves the whole reel path: one generation call produces 8 posts AND 4 reels from
a single model response, the slot routing puts 2/5/8/11 in the reels table and the
rest in posts, and the per-reel lifecycle works.

  PG_BASE_URL   override the server (default http://127.0.0.1:8001)
  PG_JOB_ID     re-run the lifecycle checks against a job that has already been
                generated, instead of paying for another generation call

The job is left in place so it can be reviewed in the UI.
"""

import os
import sys
import time

import requests

sys.path.insert(0, "F:/0001 Metaviz/Paid_Ads_Generation/backend")
from app.config import API_KEY  # noqa: E402
from app.models.post_generation.post import POST_SLOTS  # noqa: E402
from app.models.post_generation.reel import REEL_SLOTS  # noqa: E402

BASE = os.environ.get("PG_BASE_URL", "http://127.0.0.1:8001")
H = {"X-API-Key": API_KEY}
REUSE = os.environ.get("PG_JOB_ID")


def show(label, ok, extra=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, (" — " + extra) if extra else ""))
    if not ok:
        raise SystemExit(1)


def get(path):
    return requests.get(BASE + path, headers=H, timeout=30).json()


def generate_fresh():
    """Steps 1 and 2: create a brief, then generate the whole month."""
    print("1. create brief")
    r = requests.post(
        BASE + "/api/post-generation",
        headers=H,
        data={
            "company_name": "Heatable Reels",
            "phone": "0161 555 0100",
            "email": "hello@heatable.co.uk",
            "website_url": "https://heatable.co.uk",
            "company_reviews_page_url": "https://uk.trustpilot.com/review/heatable.co.uk",
            "month": "September",
            "industry": "Boilers and Heat Pumps",
            "main_topic": "Boiler replacement and installation",
            "promotion": "Free next-day installation through September",
            "areas_covered": "Manchester, North West",
            "unique_selling_points": "Fixed-price quotes. Next-day install. 12 year warranty.",
        },
        timeout=60,
    )
    show("HTTP 201", r.status_code == 201, str(r.status_code))
    new_id = r.json()["id"]

    print("2. generate (one call -> posts + reels + reviews)")
    started = time.time()
    r = requests.post(BASE + f"/api/post-generation/{new_id}/generate", headers=H, timeout=900)
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    result = r.json()
    print(
        "     took %.0fs — posts=%s reels=%s reviews=%s"
        % (time.time() - started, len(result["posts"]), len(result["reels"]), len(result["reviews"]))
    )
    return new_id, result["posts"], result["reels"]


job_id = None
try:
    if REUSE:
        job_id = int(REUSE)
        print("reusing job %s, skipping generation" % job_id)
        posts = get(f"/api/post-generation/{job_id}/posts")
        reels = get(f"/api/post-generation/{job_id}/reels")
    else:
        job_id, posts, reels = generate_fresh()

    show("8 posts", len(posts) == 8, str(len(posts)))
    show("4 reels", len(reels) == 4, str(len(reels)))
    show(
        "post slots are 1,3,4,6,7,9,10,12",
        [p["post_number"] for p in posts] == list(POST_SLOTS),
        str([p["post_number"] for p in posts]),
    )
    show(
        "reel slots are 2,5,8,11",
        [x["reel_number"] for x in reels] == list(REEL_SLOTS),
        str([x["reel_number"] for x in reels]),
    )
    show(
        "no slot claimed twice",
        not ({p["post_number"] for p in posts} & {x["reel_number"] for x in reels}),
    )

    print("\n     THE MONTH:")
    for kind, number, theme, line in sorted(
        [("post", p["post_number"], p["theme"], p["title"]) for p in posts]
        + [("REEL", x["reel_number"], x["theme"], x["reel_text"].splitlines()[0]) for x in reels],
        key=lambda t: t[1],
    ):
        print("       %-4s %2d  %-22s %s" % (kind, number, theme, line[:52]))

    # Content quality is only meaningful on freshly generated copy. On the reuse
    # path a previous run's step 3 has already hand-edited reel[0], so asserting
    # the CTA here would fail on the test's own edit rather than on a real bug.
    if REUSE:
        print("\n     (reused job: skipping generated-content checks, rows may be edited)")
    else:
        print()
        for x in reels:
            n = x["reel_number"]
            show("reel %d script is multi-line" % n, "\n" in x["reel_text"])
            show("reel %d caption has the CTA" % n, "Find out more on our website" in x["caption"])
            show("reel %d has hashtags" % n, len(x["hashtags"]) >= 3, str(len(x["hashtags"])))

    rid = reels[0]["id"]

    print("\n3. manual edit of a reel")
    r = requests.put(
        BASE + f"/api/reels/{rid}",
        headers=H,
        json={
            "reel_text": "Hand edited line one.\nHand edited line two.",
            "caption": "Hand edited caption.",
            # Deliberately messy: bare word, duplicate in another case, junk.
            "hashtags": ["#Edited", "two", "#edited", "!!"],
        },
        timeout=60,
    )
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    show("script written", r.json()["reel_text"].startswith("Hand edited"))
    show(
        "hashtags normalised, deduped and junk dropped",
        r.json()["hashtags"] == ["#Edited", "#two"],
        str(r.json()["hashtags"]),
    )

    print("4. targeted reel chat (hashtags only)")
    r2 = reels[1]
    before = get(f"/api/reels/{r2['id']}")
    r = requests.post(
        BASE + f"/api/reels/{r2['id']}/messages",
        headers=H,
        json={"content": "Change only the hashtags, leave the script and caption alone."},
        timeout=600,
    )
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    msg = r.json()["message"]
    print("     reply: %s" % msg["content"][:90])
    print(
        "     is_revision=%s fields=%s"
        % (msg["is_revision"], [k for k in ("reel_text", "caption", "hashtags") if msg.get(k)])
    )
    show("acted instead of asking", msg["is_revision"] is True)
    show(
        "only hashtags offered",
        msg.get("hashtags") is not None
        and msg.get("reel_text") is None
        and msg.get("caption") is None,
    )
    show(
        "reel unchanged before approval",
        get(f"/api/reels/{r2['id']}")["reel_text"] == before["reel_text"],
    )

    r = requests.post(
        BASE + f"/api/reels/{r2['id']}/messages/{msg['id']}/approve", headers=H, timeout=60
    )
    show("approve HTTP 200", r.status_code == 200, str(r.status_code))
    after = r.json()
    show("hashtags changed", after["hashtags"] != before["hashtags"])
    show("script left alone", after["reel_text"] == before["reel_text"])
    show("caption left alone", after["caption"] == before["caption"])

    print("5. approve / unapprove")
    show(
        "approve",
        requests.post(BASE + f"/api/reels/{rid}/approve", headers=H, timeout=30).json()["status"]
        == "approved",
    )
    show(
        "unapprove",
        requests.post(BASE + f"/api/reels/{rid}/unapprove", headers=H, timeout=30).json()["status"]
        == "pending",
    )

    print("6. regenerate one reel (keeps its slot and angle)")
    r3 = reels[2]
    r = requests.post(BASE + f"/api/reels/{r3['id']}/regenerate", headers=H, timeout=600)
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    regen = r.json()
    show("slot preserved", regen["reel_number"] == r3["reel_number"], str(regen["reel_number"]))
    show("angle preserved", regen["theme"] == r3["theme"], regen["theme"])
    show("script actually changed", regen["reel_text"] != r3["reel_text"])
    print("     was: %s" % r3["reel_text"].splitlines()[0][:66])
    print("     now: %s" % regen["reel_text"].splitlines()[0][:66])

    print("7. list endpoint")
    listed = get(f"/api/post-generation/{job_id}/reels")
    show("4 reels listed", len(listed) == 4, str(len(listed)))
    show("ordered by slot", [x["reel_number"] for x in listed] == list(REEL_SLOTS))

    print("\nALL REEL CHECKS PASSED")
finally:
    if job_id:
        print("\njob %s left in place for inspection in the Jobs tab" % job_id)
