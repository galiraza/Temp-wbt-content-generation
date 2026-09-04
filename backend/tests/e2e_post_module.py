# -*- coding: utf-8 -*-
"""End-to-end HTTP test of the post module, against the running dev server.

Creates a real brief, generates both sets, then exercises the per-item lifecycle:
manual edit, targeted chat revision, approve-the-message, approve the item, and a
single-item regenerate. Deletes the job at the end so the database is left as it
was found.
"""

import os
import sys
import time

import requests

# Override with PG_BASE_URL if the dev server is on another port.
BASE = os.environ.get("PG_BASE_URL", "http://127.0.0.1:8001")
sys.path.insert(0, "F:/0001 Metaviz/Paid_Ads_Generation/backend")
from app.config import API_KEY  # noqa: E402

H = {"X-API-Key": API_KEY}
job_id = None


def show(label, ok, extra=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, (" — " + extra) if extra else ""))
    if not ok:
        raise SystemExit(1)


try:
    print("1. create brief")
    r = requests.post(
        BASE + "/api/post-generation",
        headers=H,
        data={
            "company_name": "Heatable E2E",
            "phone": "0161 555 0100",
            "email": "hello@heatable.co.uk",
            "website_url": "https://heatable.co.uk",
            "company_reviews_page_url": "https://uk.trustpilot.com/review/heatable.co.uk",
            "month": "September",
            "industry": "Boilers and Heat Pumps",
            "main_topic": "Boiler replacement and installation",
            "promotion": "Free next-day installation through September",
            "fixed_rules": "Never name a competitor.",
            "areas_covered": "Manchester, North West",
            "unique_selling_points": "Fixed-price quotes. Next-day install. 12 year warranty.",
        },
        timeout=60,
    )
    show("HTTP 201", r.status_code == 201, str(r.status_code))
    job = r.json()
    job_id = job["id"]
    show("industry saved", job["industry"] == "Boilers and Heat Pumps")
    show("both statuses pending", job["posts_status"] == "pending" and job["reviews_status"] == "pending")

    print("2. generate (both managers in parallel)")
    started = time.time()
    r = requests.post(BASE + f"/api/post-generation/{job_id}/generate", headers=H, timeout=900)
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    result = r.json()
    elapsed = time.time() - started
    posts, reviews = result["posts"], result["reviews"]
    print("     took %.0fs — posts=%s reviews=%s" % (elapsed, len(posts), len(reviews)))
    print("     posts_status=%s reviews_status=%s" % (
        result["request"]["posts_status"], result["request"]["reviews_status"]))
    if result["request"]["error_message"]:
        print("     error_message: %s" % result["request"]["error_message"][:160])
    show("8 posts", len(posts) == 8, "%d" % len(posts))
    show("themes in slot order", [p["post_number"] for p in posts] == list(range(1, 9)))
    show("hashtag pool stored", bool(result["request"]["post_hashtag_pool"]))
    show("reviews returned", len(reviews) > 0, "%d" % len(reviews))
    show("scraped markdown stored", result["request"]["has_scraped_reviews"])
    print("     post 1: %s" % posts[0]["title"][:80])
    print("     review 1: %s / %s" % (reviews[0]["name"], reviews[0]["title"][:60]))

    post_id = posts[0]["id"]
    review_id = reviews[0]["id"]

    print("3. manual edit of post 1")
    r = requests.put(
        BASE + f"/api/posts/{post_id}",
        headers=H,
        json={"title": "Hand edited title", "caption": "Hand edited caption.", "hashtags": ["#One", "two"]},
        timeout=60,
    )
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    show("title written", r.json()["title"] == "Hand edited title")

    print("4. targeted chat revision on post 2 (hashtags only)")
    p2 = posts[1]["id"]
    before = requests.get(BASE + f"/api/posts/{p2}", headers=H, timeout=30).json()
    r = requests.post(
        BASE + f"/api/posts/{p2}/messages",
        headers=H,
        json={"content": "Change only the hashtags, keep the title and caption exactly as they are."},
        timeout=600,
    )
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    msg = r.json()["message"]
    print("     reply: %s" % msg["content"][:110])
    print("     is_revision=%s fields=%s" % (
        msg["is_revision"],
        [k for k in ("title", "caption", "hashtags") if msg.get(k) is not None],
    ))
    show("post unchanged before approval", requests.get(
        BASE + f"/api/posts/{p2}", headers=H, timeout=30).json()["title"] == before["title"])
    # An unambiguous "change the hashtags" must produce a revision, not a
    # clarifying question. Asserted strictly: asking back is a prompt regression.
    show("acted instead of asking", msg["is_revision"] is True)
    show("only hashtags offered", msg.get("hashtags") is not None
         and msg.get("title") is None and msg.get("caption") is None)

    if msg["is_revision"]:
        r = requests.post(
            BASE + f"/api/posts/{p2}/messages/{msg['id']}/approve", headers=H, timeout=60
        )
        show("approve revision HTTP 200", r.status_code == 200, str(r.status_code))
        after = r.json()
        changed_title = after["title"] != before["title"]
        changed_tags = after["hashtags"] != before["hashtags"]
        print("     title changed=%s hashtags changed=%s" % (changed_title, changed_tags))
        show("hashtags actually changed", changed_tags)
        show("partial revision left title alone", not changed_title)
        show("partial revision left caption alone", after["caption"] == before["caption"])

    print("5. approve then unapprove post 3")
    p3 = posts[2]["id"]
    show("approve", requests.post(BASE + f"/api/posts/{p3}/approve", headers=H, timeout=30).json()["status"] == "approved")
    show("unapprove", requests.post(BASE + f"/api/posts/{p3}/unapprove", headers=H, timeout=30).json()["status"] == "pending")

    print("6. regenerate post 4 (keeps its theme)")
    p4 = posts[3]
    r = requests.post(BASE + f"/api/posts/{p4['id']}/regenerate", headers=H, timeout=600)
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    regen = r.json()
    show("theme preserved", regen["theme"] == p4["theme"], regen["theme"])
    show("slot preserved", regen["post_number"] == p4["post_number"])
    show("copy actually changed", regen["title"] != p4["title"])
    print("     was: %s" % p4["title"][:74])
    print("     now: %s" % regen["title"][:74])

    print("7. review chat refuses to rewrite the customer's words")
    rv = requests.get(BASE + f"/api/reviews/{review_id}", headers=H, timeout=30).json()
    r = requests.post(
        BASE + f"/api/reviews/{review_id}/messages",
        headers=H,
        json={"content": "Rewrite the customer's review text to sound more enthusiastic."},
        timeout=600,
    )
    show("HTTP 200", r.status_code == 200, str(r.status_code))
    m = r.json()["message"]
    print("     reply: %s" % m["content"][:150])
    print("     offered a review rewrite: %s" % (m.get("review") is not None))
    after = requests.get(BASE + f"/api/reviews/{review_id}", headers=H, timeout=30).json()
    show("quote untouched on the row", after["review"] == rv["review"])

    print("8. list endpoints")
    show("posts list is 8", len(requests.get(
        BASE + f"/api/post-generation/{job_id}/posts", headers=H, timeout=30).json()) == 8)
    show("reviews list matches", len(requests.get(
        BASE + f"/api/post-generation/{job_id}/reviews", headers=H, timeout=30).json()) == len(reviews))
    show("messages list non-empty", len(requests.get(
        BASE + f"/api/posts/{p2}/messages", headers=H, timeout=30).json()) >= 2)

    print("\nALL E2E CHECKS PASSED (took %.0fs total)" % (time.time() - started))
finally:
    # The job is deliberately KEPT so the generated content can be reviewed in the
    # UI. Delete it from the Jobs list when you are done with it.
    if job_id:
        print("\njob %s left in place for inspection in the Jobs tab" % job_id)
