"""Prompt for the content-matching agent: picks which already-generated hero
image best fits one post's title + caption, from a pool of candidate images
with a usage count each, so the same image doesn't get reused more than the
pool size allows.

No matching file existed in this module before this was ported. Like the
other newly-ported prompts here, this n8n node has only a user message, no
system message, so there is no *_SYSTEM_PROMPT constant.

In n8n this read/wrote an n8n Data Table for usage tracking; here the
candidates list must instead be built from our own DB table before the call,
and the caller is responsible for writing the usage increment back to that
table afterward - this agent only reads the list it's given and reports back
which image it picked and that image's CURRENT (pre-increment) usage value,
per STEP 6. It never mutates anything itself.

Do not reword this prompt: the phrasing and the strict single-line JSON
output format are load-bearing for whatever parses the selection back out.
"""

CONTENT_MATCHING_USER_PROMPT = """\
You are a smart content matching agent for a social media post creation system.
You will receive:
- A post title
- A post caption
- A full list of candidate images (each has image_name, summary, usage)

Candidate Images:
{candidates_json}

You MUST use ONLY this provided list. Do not call any tool, do not query any external source, and never guess — read every item directly from the list above.

**STEP 1 — Read the full list:**
Read every single row in the candidates list provided above. Count the total number of images. Store this as TOTAL.

**STEP 2 — Calculate usage limit:**
- If TOTAL is 8 or more → MAX_USAGE = 1 (each image can only be used once)
- If TOTAL is less than 8 → MAX_USAGE = 2 (each image can be used maximum twice)
Store MAX_USAGE internally.
CRITICAL: Even after calculating MAX_USAGE, you MUST still read and score ALL rows in STEP 4 — do not skip any row during scoring regardless of its usage value.

**STEP 3 — Identify eligible images:**
Go through every single row in the provided list and mark each image as either ELIGIBLE or INELIGIBLE:
- ELIGIBLE: usage value is strictly LESS THAN MAX_USAGE
- INELIGIBLE: usage value is equal to or greater than MAX_USAGE
Store this eligibility list internally.
CRITICAL: Do NOT stop reading summaries after finding ineligible images. You MUST go through ALL rows and mark ALL of them before proceeding.
If ALL images are INELIGIBLE, then reset and treat ALL images as ELIGIBLE regardless — never return empty.
You MUST have at least one ELIGIBLE image before proceeding to STEP 4.

**STEP 4 — Read and compare ALL ELIGIBLE summaries only:**
You MUST read and score ONLY the images marked as ELIGIBLE in STEP 3.
Do NOT score INELIGIBLE images — they are excluded from selection entirely.
Do NOT pick the first result. Do NOT default to any image.
IMPORTANT: Start your evaluation from the LAST eligible image in the list and work BACKWARDS to the first.

Compare the post title and post caption against EVERY eligible summary individually.

- Post Title: {image_video_title}
- Post Caption: {post_caption}

Internally score every single eligible image (do NOT output this scoring — keep it in your internal thinking only):
image_name | score (1-10) | reason
You MUST internally score ALL eligible images before moving to STEP 5.
Score each image summary against the post on:
- Subject matter relevance (does the image show what the post is about?)
- Setting relevance (does the environment match the post context?)
- Tone relevance (does the mood of the image match the post message?)

**STEP 5 — Select the HIGHEST scoring eligible image:**
After scoring ALL eligible images internally, select the one with the highest relevance score.
CRITICAL:
- Every eligible image has an equal chance of being selected — never favour a lower-numbered image over a higher-numbered one.
- Don't prioritize any one image from them.
- If two images tie, pick the one whose summary most closely matches the post caption words.
- Never return empty — always return the best available eligible image.

**STEP 6 — Return result:**
Your response must begin with the character "{{" and end with the character "}}".
Return ONLY this exact JSON object with zero text before or after it:
{{
  "image_name": "the selected image name here",
  "usage": current usage number of the selected image
}}
If your response contains any word other than this JSON object, you have failed. No steps, no thinking, no "I have retrieved", no explanations — only the JSON object starting with {{ and ending with }}.

**STRICT RULES:**
- You MUST use only the candidates list provided above — never call a tool, never query a data table, never guess.
- You MUST read the ENTIRE provided list before making any decision — never make a decision based on partial data.
- You MUST evaluate ALL eligible summaries before selecting — never pick the first one by default.
- Never select an image whose usage has already reached MAX_USAGE unless absolutely no other option exists.
- Never favour any lower-numbered image over others — selection must be based purely on relevance score.
- Your final response must contain ONLY the JSON object in STEP 6 format — nothing else whatsoever.
- DO NOT output your scoring table — all scoring must happen silently in your internal reasoning only.
- Your ENTIRE response from first character to last character must be ONLY the JSON object. The very first character you output must be "{{" and the very last character must be "}}". Any output before "{{" or after "}}" is a critical failure.
- Never narrate your steps, never explain your reasoning, never confirm what you retrieved — output ONLY the final JSON object."""
