"""Prompt for the headline/mood extraction agent: splits a post title into a
headline + subheadline, and derives a short mood descriptor from the
industry, both consumed by the final branded post-image prompt (see
final_image_prompt.py).

No matching file existed in this module before this was ported. Like the
other newly-ported prompts here, this n8n node ("Extract Headline Mood") has
only a single prompt text, no separate system message, so there is no
*_SYSTEM_PROMPT constant. It ran on Claude Sonnet 4.6 in n8n; this module now
defaults to Claude Sonnet 5 (see client.py), so no new LLM wiring is needed
to reuse it here - just the existing text_llm()/structured_llm() chain.

Do not reword this prompt: the phrasing and the strict single-line JSON
output format are load-bearing for whatever parses the split back out.
"""

HEADLINE_MOOD_USER_PROMPT = """\
You are a copywriting specialist. Given a social media post title and the client's industry, produce a headline/subheadline split and a short mood descriptor.

Post Title: {image_video_title}
Industry: {industry}

**HEADLINE/SUBHEADLINE SPLIT** — split the title into a PRIMARY (headline) and SECONDARY (subheadline) portion, in this priority order:
1. Colon (:) or question mark (?) — split at whichever occurs first. Text before = headline, text after = subheadline.
2. Comma (,) — only if no colon/question mark exists. Split at the first comma; before = headline, after = subheadline.
3. No punctuation at all — split by meaning: the core/main hook phrase = headline, the supporting/descriptive part = subheadline (based on natural sentence logic, not word count).
If the title has no natural second part, leave subheadline as an empty string.

**MOOD** — from the industry, produce a short mood descriptor (2-5 words) capturing the tone the final image should have (e.g. "Air Con" -> "cool, crisp, refreshing"; "Boiler Installs" -> "warm, reliable, dependable").

# OUTPUT
Return ONLY a single JSON object, no markdown, no commentary:
{{
  "headline": "...",
  "subheadline": "...",
  "mood": "..."
}}
The very first character of your response must be `{{`."""
