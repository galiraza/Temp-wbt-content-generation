"""User turns for regenerating ONE post or ONE review.

These are ours, not ported: the n8n workflows had no way to redo a single item,
which is the main reason the module was rewritten. Both reuse the batch SYSTEM
prompt unchanged, so every writing rule, word count, CTA requirement and hashtag
quota still applies — only the ask changes, from "write the set" to "write this
one". The output format is the batch format so the same parser reads it.
"""

SINGLE_POST_USER_PROMPT = """\
Rewrite ONE post for the following client. Output only that single post, in the
exact Static Post format from your instructions.

**Company Name:** {company_name}
**Phone:** {phone}
**Email:** {email}
**Website URL:** {website_url}
**Target Month:** {month}
**Main Topic:** {main_topic}
**Promotion:** {promotion}
**Fixed Rules:** {fixed_rules}
**Additional Resources:** {additional_resources}
**Additional Notes:** {additional_notes}
**USP's:** {unique_selling_points}

---

This post is slot {post_number} of 8, and its assigned content type is:
**{theme}**

Keep that content type. The month is designed to move through all eight types,
so this post must still fill this slot's role.

The current version is below. Write a genuinely different take on the same slot:
a new hook, a new angle, new wording. Do not simply reword it.

Current title: {current_title}
Current caption: {current_caption}

---

Reminder:
- Output exactly ONE post, headed "Post {post_number} - Static Post"
- Follow the Static Post format, word counts, UK spelling, and CTA block exactly
- End with a hashtag block of 5 to 8 tags, company name hashtag first
- Use hashtags only from:
  {hashtag_pool}
"""


SINGLE_REVIEW_USER_PROMPT = """\
Rewrite ONE review post for the following client. Output only that single review
post, in the exact format from your instructions.

Company Name:  {company_name}
Promotion:     {promotion}
USP's:         {unique_selling_points}

# CTA BLOCK (use exactly as given below)
\U0001f310 Find out more on our website! {website_url}
\U0001f4de Give us a call: {phone}
\U0001f4e7 Or send us an email at {email}

# TRENDING HASHTAGS
{hashtag_pool}

---

This is review post {review_number}. The customer's review is fixed and must be
reproduced VERBATIM in the Review Quote field: never paraphrase it, never
shorten it, never improve its grammar.

Reviewer name: {name}
Review Quote (verbatim, do not alter): {review}

Rewrite only the Post Title and the Post Caption. Write a genuinely different
warm response to the same review, with a different opening and a different
closing line.

Current title: {current_title}
Current caption: {current_caption}

---

Reminder:
- Output exactly ONE review post, headed "Review Post {review_number}"
- Reproduce the Review Quote exactly as given above
- End with a hashtag block of 5 to 7 tags, company name hashtag first
- Use hashtags only from the Trending Hashtags list above
"""


SINGLE_REEL_USER_PROMPT = """\
Rewrite ONE reel for the following client. Output only that single reel, in the
exact Reel Post format from your instructions.

**Company Name:** {company_name}
**Phone:** {phone}
**Email:** {email}
**Website URL:** {website_url}
**Target Month:** {month}
**Main Topic:** {main_topic}
**Promotion:** {promotion}
**Fixed Rules:** {fixed_rules}
**Additional Resources:** {additional_resources}
**Additional Notes:** {additional_notes}
**USP's:** {unique_selling_points}

---

This reel is slot {reel_number} of the 12 item month, and its assigned angle is:
**{theme}**

Keep that angle. The month is designed to move through all twelve slots, so this
reel must still fill this slot's role.

The current version is below. Write a genuinely different take on the same angle:
a new hook, a new scene, new wording. Do not simply reword it.

Current reel text: {current_reel_text}
Current caption: {current_caption}

---

Reminder:
- Output exactly ONE reel, headed "Post {reel_number} - Reel Post"
- Reel Text is the on-screen script: one short line per text card, under 8 words
  a line, 30 to 50 words in total
- Reel Caption is 3 paragraphs, 55 to 75 words in total
- Follow UK spelling and the CTA block exactly
- End with a hashtag block of 5 to 8 tags, company name hashtag first
- Use hashtags only from:
  {hashtag_pool}
"""
