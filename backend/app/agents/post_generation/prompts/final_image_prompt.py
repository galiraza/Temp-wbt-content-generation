"""Prompt builder for the final branded post-image generation call.

Ported from the n8n Code node "Build Final Image Prompt" (a JS template
literal). Combines:
  - the brand colors extracted from the logo (see logo_color_prompt.py)
  - the headline/subheadline/mood split (see headline_mood_prompt.py)
  - a layout variant's block text, picked at random from a variant library
    (a Google Doc in n8n; a DB table here once the 26 variants are provided)
  - the industry and the CTA text (the client's URL)

The variant's own block text carries {{PRIMARY_HEX}} / {{ACCENT_HEX}} /
{{BG_HEX}} / {{NEUTRAL_HEX}} placeholders that must be substituted with the
real hex values BEFORE the block is embedded in the final prompt - this is a
plain find/replace against arbitrary variant text, not a str.format() call,
because the variant text is external content that may contain other stray
braces .format() would choke on.

The finished prompt, plus two supplied images (the company logo and the
picked hero photo), are sent together to OpenAI's images.edit() - see the
n8n "Generate Final Image (OpenAI)" node, which used gpt-image-2 with
size="auto".

Do not reword this template: the phrasing and hard constraints are what keep
gpt-image-2 from distorting text and inventing extra decoration.
"""

_COLOR_PLACEHOLDER_KEYS = ("PRIMARY_HEX", "ACCENT_HEX", "BG_HEX", "NEUTRAL_HEX")

FINAL_IMAGE_PROMPT_TEMPLATE = """\
ROLE: You are a senior graphic designer producing a finished branded social media post.

OUTPUT: One 1080 x 1350 px (4:5 portrait) marketing graphic. A flat, vector-style layout
design — NOT a photograph of a poster, NOT a mockup, no device frame, no drop-shadowed
card floating on a background, no border around the canvas. The design fills the full canvas.

=== SUPPLIED ASSETS — USE VERBATIM ===
[IMAGE 1] COMPANY LOGO. Place it as-is. Preserve its exact shapes, letterforms, icon,
proportions and colours. Do NOT redraw, re-letter, restyle, recolour, crop, distort, add
effects to, or invent any part of it. Never add a white, light, or contrasting patch,
plate, halo, badge, or background shape behind the logo to make it stand out — the logo
sits directly on whatever background colour or texture already exists at that location,
unchanged, exactly like every other element in the design.

[IMAGE 2] HERO PHOTOGRAPH. This exact photo is the post's subject image. Keep its content
100% unchanged — same people, same equipment, same room, same lighting. You may ONLY scale,
crop and mask it into the required shape. Never substitute a different scene and never
generate new photographic content.

=== BRAND SYSTEM — use ONLY these colours, plus white and near-black ===
Primary {primary_hex} -> headline, CTA pill fill, large decorative shapes
Accent {accent_hex} -> icons, arrow button, small highlights
Background {bg_hex} -> canvas base
Neutral {neutral_hex} -> subheadline text
No other hues appear anywhere in the design.

=== COPY — render exactly, letter for letter ===
HEADLINE: "{headline}"
SUBHEADLINE: "{subheadline}"
CTA: "{cta_text}"

Spell every word correctly and render it fully legible. Do not paraphrase, shorten, or
re-order. Do not add taglines, phone numbers, addresses, hashtags, emoji, social icons,
or any text not listed above. If the chosen layout variant calls for any extra lead-in/eyebrow text derived from the headline, and that text would end up identical or nearly identical to the full headline, render that shared wording only ONCE — never show the same phrase twice as two separate text elements.

=== LAYOUT: VARIANT {variant} ===
{layout_block}

=== TYPOGRAPHY ===
Headline: geometric sans-serif, extra-bold / black weight, tight leading (~0.95x),
Title Case, broken into 2-4 optically balanced lines, the single largest element on the
canvas. Even letter-spacing, crisp edges. Every letter must keep its natural,
undistorted width-to-height proportions — never rendered taller/narrower or
shorter/wider than a normal letterform of the chosen typeface.
Subheadline: same family, regular or medium weight, 35-40% of the headline size, one line
where the copy allows.
CTA: semi-bold, ~45% of headline size, inside a fully-rounded pill with generous horizontal
padding (pill width = text width + 12% of canvas width).
Margins: 8% of canvas width on the left and right for every text block. Nothing touches
the canvas edge except intentional full-bleed shapes.

=== DECORATION — subtle only ===
A soft vertical gradient from {bg_hex} to white; one or two large, low-opacity organic
blobs or one smooth wave in {primary_hex}; optionally a single large, oversized version
of the logo's icon as a faint watermark at 4-6% opacity behind the headline. This watermark must
appear ONLY ONCE, as one single large shape — it must NEVER be tiled, scattered, or repeated
multiple times across the canvas; one large faint icon, not a pattern. This default only applies
when the chosen layout variant below does not describe its own treatment of the logo icon — if
the variant's own background description calls for something different (e.g. a scattered
repeated pattern), follow the variant's own description exactly instead. Keep at least 60% of
the canvas as calm negative space. No decoration may overlap or reduce the legibility of any
text.

=== INDUSTRY CONTEXT ===
Sector: {industry}. Mood: {mood}, professional and trustworthy — a established UK trade
company, not a tech startup. No clip-art, no cartoon mascots, no 3D renders.

=== HARD CONSTRAINTS ===
- STRICT, NON-NEGOTIABLE RULE ON TEXT PROPORTIONS: Every letter in the headline,
  subheadline, and CTA text must be rendered with its normal, undistorted proportions —
  never stretched taller/narrower or squashed shorter/wider than a standard letterform of
  the chosen typeface. When sizing any text block to fill its allotted space, scale
  letterform height and width by the exact same factor — uniform scaling only. Never
  increase a letter's height without increasing its width by that same proportion, and
  never stretch or compress text in only one direction. Before finalising the output,
  examine the headline, subheadline, and CTA text one letter at a time: does each letter
  look like a normal, evenly-proportioned character? If any text appears elongated,
  condensed, stretched, or squashed in only one direction, this is a failure and must be
  corrected before output.
- Print-crisp text: clean even edges, no warped, doubled, merged, cut-off or gibberish letters.
- No text drop shadows, no outlined/stroked text, no gradients inside letterforms.
- No stock-photo watermarks, no placeholder boxes, no lorem ipsum.
- The only photographic content in the entire image is [IMAGE 2].
- Headline block and photo block are visually balanced, not crowded.
- Headline, subheadline, and any eyebrow/lead-in text must never touch, overlap, or visually merge into each other — keep clear, unambiguous separating space between every text block at all times, with no letters from one block crossing into another."""


def substitute_variant_colors(layout_block: str, colors: dict) -> str:
    """Fills a layout variant's own {{PRIMARY_HEX}}/{{ACCENT_HEX}}/{{BG_HEX}}/
    {{NEUTRAL_HEX}} placeholders with real hex values.

    Plain find/replace, not str.format(): the variant block is external
    content (from the variant library) that may contain other stray braces,
    so treating it as a format string would risk a crash on content we don't
    control.
    """
    for key in _COLOR_PLACEHOLDER_KEYS:
        layout_block = layout_block.replace("{{" + key + "}}", colors[key.lower()])
    return layout_block


def build_final_image_prompt(
    *,
    primary_hex: str,
    accent_hex: str,
    bg_hex: str,
    neutral_hex: str,
    headline: str,
    subheadline: str,
    mood: str,
    variant: str,
    layout_block: str,
    industry: str,
    cta_text: str,
) -> str:
    """Builds the final images.edit() prompt. `layout_block` must already have
    had its own color placeholders substituted via substitute_variant_colors().
    """
    return FINAL_IMAGE_PROMPT_TEMPLATE.format(
        primary_hex=primary_hex,
        accent_hex=accent_hex,
        bg_hex=bg_hex,
        neutral_hex=neutral_hex,
        headline=headline,
        subheadline=subheadline,
        cta_text=cta_text,
        variant=variant,
        layout_block=layout_block,
        industry=industry,
        mood=mood,
    )
