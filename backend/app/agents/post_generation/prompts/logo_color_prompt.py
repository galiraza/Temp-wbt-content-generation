"""Prompt for the logo color-extraction agent: the first step of post-image
generation, which inspects the client's uploaded logo and derives a 4-color
palette (primary/accent/bg/neutral) for the post design to match.

No matching file existed in this module before this was ported. Like
hero_image_prompt.py, this n8n node has only a user message, no system
message, so there is no *_SYSTEM_PROMPT constant. There are no n8n
expression placeholders either - the logo image itself is the only input,
attached to the call as vision input, not interpolated into this text. The
literal braces in the JSON example are doubled ({{ / }}) purely so this
string survives a future ChatPromptTemplate/.format() call unscathed, the
same way the rest of this module's prompts are wired in - not because
anything is actually substituted into them.

Do not reword this prompt: the phrasing and the strict single-line JSON
output format are load-bearing for whatever parses the palette back out.
"""

LOGO_COLOR_USER_PROMPT = """\
You are a brand-color analyst. Inspect the attached company logo image and extract a 4-color palette suitable for a matching social media post design.
- **primary_hex**: the logo's dominant/boldest color, used for headlines and CTA fills.
- **accent_hex**: a secondary logo color (or a complementary color if the logo is monochrome), used for icons and small highlights.
- **bg_hex**: a very light/pale tint suitable as a canvas background (derive from the logo's hue family, not necessarily a color literally present in the logo).
- **neutral_hex**: a dark neutral (near-black or dark grey/navy) suitable for subheadline text.
All four must be valid 6-digit hex codes and must look cohesive together.

# OUTPUT
Return ONLY a single JSON object, no markdown, no commentary:
{{
  "primary_hex": "#......",
  "accent_hex": "#......",
  "bg_hex": "#......",
  "neutral_hex": "#......"
}}
The very first character of your response must be `{{`."""
