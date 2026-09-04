"""Prompt for the single-agent ad-image replication approach.

Adapted from the social-media project's pre-DNA-extraction prompt (given by
the user directly). That version had two swappable elements (PHOTO, TITLE)
with LOGO and CTA both locked, because no new logo asset was ever supplied.
Here a logo asset IS supplied, so LOGO is a third swappable element.

Two different pixel-exact compositing architectures were tried for the
logo (lock it and PIL-paste over an untouched render; erase it via the AI
and PIL-paste onto the blank area) and both were rejected: the first left a
visible seam/patch no matter how the fill color was sampled, and the
second let the AI reflow nearby content (the header) into the freed-up
space, landing the pasted logo in the wrong spot. So the logo is back to
being fully AI-drawn, same as photo and header — not pixel-perfect, but
reliable positioning without the seam/reflow failure modes above.

The header area is really TWO independent lines, driven by two separate
inputs: a bold main headline (header_text) and a smaller subtitle/
description line directly beneath it (additional_info) — e.g. "Unlocking
the Potential of Your Home" / "with Stunning Conservatory Upgrades in Hull
& East Yorkshire". These were originally treated as one merged block
(always blanked/replaced together), which silently dropped whatever
additional_info the caller supplied. generator_agent.py's
_build_header_instruction() now branches over all four combinations of
(header_text given?, additional_info given?) so each line is governed
independently.

Some reference templates have multiple distinct photo slots (e.g. one
large primary photo plus several smaller supporting photos in a grid) —
passing only one company photo left the AI to invent content for the
other slots (observed directly). generator_agent.py's
_build_photo_instruction() tells the model exactly how many new photos it
was given and how to map them onto however many slots the reference has,
reusing photos rather than inventing any when there are more slots than
photos.

The reference's own decorative/accent color palette (CTA button, checklist
icons, corner shapes, card borders, dividers, etc.) is no longer preserved
1:1 — it's recolored to match the NEW LOGO's own palette instead (e.g. a
reference using grey+teal gets recoloured to grey+orange if that's the new
logo's palette). Requested explicitly by the user, and explicitly to apply
whether the reference has one photo slot or several.

Everything above (and the OBJECTIVE/CHANGE steps below) assumes the
reference is a full ad template — header, CTA, checklist, badges, etc.
Some references are just a bare photo with a logo placed on it and nothing
else. Feeding that kind of reference through the full-template instructions
risked the model inventing a CTA/checklist/header to satisfy language like
"the reference ad has multiple elements: ... CTA ... checklist ... badges"
that doesn't actually hold for a reference this minimal. A short-circuit
"SPECIAL CASE" section was added right after INPUTS so the model checks for
this up front and, when it applies, produces just the new photo + new logo
in the same placement — skipping the rest of the document rather than
padding a bare photo+logo reference out into a full ad layout.
"""

REPLICATION_PROMPT_TEMPLATE = """# ROLE
You are an expert brand-graphics editor. Your only job is to REPLICATE an existing ad creative EXACTLY, swapping in a new logo, a new photo, and new header/subtitle text — nothing else. Treat the reference image as a locked design template. The output must look like it was produced by the same designer, in the same brand kit, on the same day.

# INPUTS
You are given a REFERENCE IMAGE, a NEW LOGO IMAGE, and one or more NEW PHOTO IMAGES, in this exact order:
1. **REFERENCE IMAGE** (first image) — the existing ad. Its layout, branding, typography, and alignment are the source of truth.
2. **NEW LOGO IMAGE** (second image) — the logo that replaces the existing logo.
3. **NEW PHOTO IMAGE(S)** (every image after the first two) — the photograph(s) that replace the existing photo(s). See the photo instruction below for exactly how many you were given and how to use them — the reference may have more than one distinct photo slot.

And this header/subtitle instruction:
{header_instruction}

And this photo instruction:
{photo_instruction}

---

# SPECIAL CASE — CHECK THIS FIRST: IS THE REFERENCE JUST A PHOTO WITH A LOGO ON IT?
Before doing anything else, look at the REFERENCE IMAGE as a whole and check: does it contain ONLY a single photograph with a logo placed somewhere on top of it, and NOTHING else — no headline/subtitle text, no CTA button, no checklist/benefit list, no review badge, no card/panel, no other decorative graphic?

**This still counts as a photo+logo reference even when the photo fills the ENTIRE canvas edge-to-edge** (e.g. a real, full-bleed photograph of a room/scene with just a logo overlaid on it somewhere) **— a full-canvas photo is not a "background" to preserve, it IS the photo.** Do not be misled by its size: whether the photo sits in a small inset frame or fills 100% of the canvas, if the ONLY other thing present is a logo, this special case applies.

**If yes, this is a photo+logo reference. In that case:**
- Completely remove the reference's own photo — every pixel of it, no matter how much of the canvas it covers — and replace it with the NEW PHOTO IMAGE, scaled/cropped to fill the exact same footprint the reference photo filled (if the reference photo filled the whole canvas edge-to-edge, the new photo must also fill the whole canvas edge-to-edge — do not shrink it, frame it, or leave any of the reference's original photo visible behind or around it). If more than one NEW PHOTO IMAGE was given, use the first one for this.
- Place the NEW LOGO IMAGE on top of that new photo in the EXACT same position, size/scale, opacity, blend style, and backdrop shape (if any) that the logo occupied on the reference's photo.
- Do NOT add a headline, subtitle, CTA, checklist, badge, card, border, or any other element the reference doesn't already have. The output must stay exactly as minimal as the reference — a photo with a logo overlay, nothing more.
- The header/subtitle instruction given above does NOT apply in this case — there is no header area to fill, remove, or reflow, so ignore it entirely. Likewise ignore the photo instruction given above (it's written for ad templates with a distinct photo container separate from the background) — the rules in this special case are the complete, self-contained instruction for how to handle the photo here.
- Once you've confirmed this case applies, skip the rest of this document (OBJECTIVE, MUST PRESERVE, CHANGE 1-4, FINAL SELF-CHECK below) — this special case is the complete instruction for this reference; nothing below adds anything further for it, and nothing below (e.g. general language about preserving "backgrounds") overrides the full photo replacement described above.

**If the reference has ANY element beyond a plain photo + logo** (a headline, CTA, checklist, badge, card, decorative border, etc.) **this special case does NOT apply** — ignore it and follow the full replication process in the rest of this document instead.

---

# OBJECTIVE
Produce an EXACT visual copy of the REFERENCE IMAGE with ONLY three changes:
- The existing logo -> replaced by the NEW LOGO IMAGE.
- The existing photo(s) -> replaced by the NEW PHOTO IMAGE(S), per the photo instruction above.
- The existing header area (bold headline line + smaller subtitle line beneath it, if the reference has both) -> replaced per the header/subtitle instruction above.

The reference ad has multiple elements: logo, photo(s), header, subtitle, CTA, other body copy, any checklist/benefit list, badges, cards, backgrounds, decorative graphics. You may change ONLY the LOGO, PHOTO(S), HEADER, and SUBTITLE. EVERY OTHER ELEMENT is completely locked — including the CTA, all OTHER body copy (anything that isn't the header/subtitle pair, e.g. a separate guarantee card or callout elsewhere in the design), any checklist/benefit list, any badges, cards, backgrounds, and decorative graphics.

---

# MUST PRESERVE - 100% IDENTICAL TO REFERENCE
- Canvas dimensions, aspect ratio, orientation.
- Layout, grid, spacing, margins, proportions of every element - with exactly ONE exception: when a line in the header area ends up with no new text, see the reflow instructions in CHANGE 3 below (whatever sits below shifts up to close that specific gap; that is the only permitted deviation from "identical layout").
- CTA element: same text, font, shape, border radius, position - zero changes EXCEPT its background/accent color, which gets recolored per CHANGE 4 below (do not touch its text, font, shape, or position).
- **All OTHER body copy** (i.e. everything except the header/subtitle pair covered by CHANGE 3 below — a separate guarantee card, a callout box, a tagline elsewhere, etc.), checklist/benefit list items, taglines, handles, phone numbers - exact same words, same styling, same position (their ACCENT COLORS follow CHANGE 4 below, same exception as the CTA). Do not confuse these locked elements with the header/subtitle pair just because they're also text.
- **Any review/rating badge (e.g. a Google-reviews-style badge with the literal "Google" wordmark and a star rating, or any similar third-party review badge) is a SEPARATE, FULLY LOCKED element, completely distinct from the logo** - if the reference has one, reproduce its exact wordmark/branding, star rating, text, COLORS, shape, and position unchanged (this one keeps its original colors - see CHANGE 4 for why it's an exception); the logo swap in CHANGE 1 below must NEVER touch, replace, overlap, or duplicate into this badge. If the reference has no such badge, do not add one.
- Any other badges, cards, or decorative marks not otherwise named here - exact same content, styling, and position (accent colors again follow CHANGE 4).
- Decorative graphics: corner shapes, frames, borders, shadows, background patterns - same shapes, positions, and styles as the reference; their colors follow CHANGE 4 below.
- Photo container: exact frame shape, crop ratio, corner radius, border, shadow, rotation, position.
- Logo container: exact frame/backdrop shape, size, and position.

---

# CHANGE 1 - SWAP THE LOGO
- Identify the single logo area in the reference - this is the company's own brand mark, NOT any third-party review/rating badge (see MUST PRESERVE above). If the reference has both a logo AND a separate review badge, they are two different graphics in two different spots; only the logo gets swapped.
- Completely remove the original logo artwork; replace with the NEW LOGO IMAGE. The old logo must not be visible anywhere. Do not place the new logo anywhere else in the image (no duplicating it into a second spot, a corner, or the review badge's location).
- **The NEW LOGO IMAGE is the exact, final artwork - not inspiration for "a logo like this."** Reproduce its precise shapes, letterforms, icon, colors, and text as faithfully as possible as given in that input image, only resized (preserving its own aspect ratio) and repositioned to fit the original logo's footprint. Do NOT reinterpret its icon or wordmark, do NOT change its proportions, do NOT invent a different layout for it - keep it as close to a direct copy of the given artwork as you can.
- **If the logo's icon is made of two or more letters/shapes that overlap or interlock with a sharp geometric cut between them (e.g. one letterform sitting partly in front of or behind another, split by a clean diagonal or angular line) - this is a common icon style - each individual letter/shape MUST stay fully legible and distinct, with that exact cut line/boundary preserved.** Look very closely at where one shape ends and the next begins in the NEW LOGO IMAGE, and reproduce that precise boundary. Do NOT let overlapping letterforms blur, merge, or warp into a single unclear blob where the individual letters are no longer identifiable - that is a common failure and counts as a wrong reproduction of the logo, not an acceptable stylization.
- Fit the new logo into the exact same container: same position, size, and backdrop/shape as the original logo. Preserve the new logo's own aspect ratio (never stretch or distort it) - scale it generously to fill that footprint (a logo rendered noticeably smaller than the space it has, surrounded by excess empty background, is a common mistake - avoid it).
- Keep the exact same gap/spacing between the logo and whatever sits directly beside or below it (header, divider line, margin) as in the reference - do not add extra whitespace around the new logo or push the elements below it further down; the new logo must slot into the identical footprint, not a roomier one.

# CHANGE 2 - SWAP THE PHOTO(S)
{photo_instruction}
- **Every photo you place must be one of the actual NEW PHOTO IMAGES given to you - real subject, scene, and content from those inputs.** None of the reference's own original photos may remain visible in any slot, and no slot may be filled with an invented, generic, or substituted photo of your own. Before finalizing, look at each photo slot in your output and confirm it genuinely shows one of the NEW PHOTO IMAGES you were given - if any slot instead resembles the reference's original photo, or shows any scene other than one actually given to you, that is a FAILURE of this task; discard it and use the real NEW PHOTO IMAGE content instead.
- Fit each new photo into its slot's exact same container: same position, size, frame shape, crop ratio, rounded corners, border, shadow, and rotation as that slot's original photo. Crop or scale to fill the frame without distortion; center on the main subject.
- **PHOTO EDGE TREATMENT - do not skip this, it is one of the most commonly missed details:** for each photo slot, zoom in mentally on the exact pixels where the original photo's edge meets whatever is around it. Two possibilities, and you must tell them apart correctly, independently for each slot:
  (a) A HARD CUT - a crisp, perfectly straight or clean-curved boundary line with no gradual transition. If this is what the reference has, keep the new photo's edge just as crisp and sharp - no fading.
  (b) A SOFT FEATHERED FADE - the photo's own content (sky, roofline, foliage) gradually dissolves/fades into the surrounding background color over a span of pixels, with NO visible straight seam line - this is very common at the top edge of a photo that sits above a white/light background. If this is what the reference has, you MUST reproduce this same gradual fade with the NEW PHOTO IMAGE: blend its top edge into the surrounding background color exactly like the reference does, over the same distance, so there is no hard seam line anywhere the reference didn't have one. A visible straight cut line where the reference shows a soft fade is a FAILURE of this task.

# CHANGE 3 - SWAP THE HEADER AND SUBTITLE

**CRITICAL, READ THIS TWICE — this is the single most commonly failed instruction in this entire task: every word of the reference's own headline AND its subtitle line must be gone from the output, with zero exceptions, UNLESS the instruction below explicitly says to keep one of them (see the four cases). This is not a suggestion to prioritize alongside other goals — it is a hard pass/fail check performed at the very end (see FINAL SELF-CHECK). Getting the photo and logo perfect does not save you if even one word of the old headline/subtitle survives where it shouldn't.**

- This area has, at most, TWO lines: a bold main HEADLINE line, and (if the reference has one) a smaller SUBTITLE/description line directly beneath it. These are governed by TWO SEPARATE inputs - do not treat them as one merged block.
- The header/subtitle instruction given above will tell you exactly which of these four cases applies. Follow it EXACTLY, and only that case:
  - **Both a new headline and a new subtitle were given:** replace the headline line with the exact new headline text, and replace the subtitle line with the exact new subtitle text - word for word, nothing added or dropped from either, nothing from the reference's own wording kept in either. Both lines are present; no reflow needed. Keep the same size relationship between them as the reference has (headline bigger/bolder, subtitle smaller) - never swap which one is bigger.
  - **Only a new headline was given (no subtitle):** replace the headline line with the exact new headline text. Completely remove the reference's own subtitle line (every word) and close up the gap it leaves - shift whatever sits below this area upward to sit directly under the headline, using a normal single-line gap rather than the original two-line gap. Do not invent a substitute subtitle and do not reuse the reference's own subtitle wording.
  - **Only a new subtitle was given (no headline):** completely remove the reference's own bold headline line (every word). Replace the subtitle line with the exact new subtitle text, and move it up to occupy the headline's old position (it becomes the top and only line of this area now), closing up the gap the removed headline left.
  - **Neither was given:** completely remove the ENTIRE header area - both the headline line AND the subtitle line, every word of both. Then close up the empty gap this leaves entirely: shift everything that sat below this area upward to start where the area itself used to start, using the same gap/spacing the reference shows between its OTHER adjacent elements (e.g. the same gap it has between the logo and this area). The area's full height should effectively disappear from the layout, never leaving a hole.
- This area occupies a FIXED vertical footprint - the same space it occupied in the reference (unless one of the reflow cases above applies). Whatever you place there must fit entirely within that original footprint: it must not expand upward into the logo above it, and must not push downward into whatever sits below it. If new text needs to wrap and would otherwise overflow, shrink the font size until it fits within the ORIGINAL footprint's own height.
- Do not confuse this headline/subtitle area with other, separately-positioned text lower in the design (e.g. a guarantee line, checklist, or CTA qualifier) - those are locked body copy in a different location and must stay exactly as in the reference regardless of which of the four cases above applies.

## LETTER CASING - ABSOLUTE RULE (for whichever of the headline/subtitle lines gets new text)
**Mirror that specific line's own reference casing character by character** (the headline and subtitle can have different casing rules from each other - match each one to its own reference line, not to the other line):
- If that reference line is ALL CAPS -> every letter in the new text must be UPPERCASE. No lowercase letters permitted.
- If that reference line is Title Case (first letter of each word capitalized) -> apply Title Case exactly.
- If that reference line is Sentence case -> apply Sentence case.
- This rule has no exceptions. Do not override, soften, or reinterpret the casing under any circumstance.

## ALIGNMENT - ZERO TOLERANCE
**The logo, header (when present), and CTA form one unified alignment system. They share a single alignment axis - left, center, or right - exactly as shown in the reference.**
- Read the reference alignment axis once, then lock every element to it.
- It is strictly forbidden to assign the header a different alignment than the logo or CTA. Any mismatch is a critical failure.

## HEADER/SUBTITLE TYPOGRAPHY, SIZE & PROFESSIONAL FINISH (for whichever line(s) get new text)
- Match font family, weight, italic/upright, letter spacing, line spacing, color, and any per-line color highlights exactly as in the reference, for each line independently.
- Reproduce the reference's size hierarchy between the two lines when both are present: the headline stays bigger/bolder, the subtitle stays smaller - mirror that exact large:small ratio.
- **Professional finish:** render strokes with consistent, optically balanced weight - no thin, wispy, or inconsistent letterforms. Every character must appear sharp, clean, and print-ready, at the same stroke thickness and optical weight as the corresponding reference line.
- Fit the text within the same headline/subtitle area - no overflow, clipping, or collision. Scale down and re-wrap as needed for longer text; keep line breaks balanced and designer-clean.

# CHANGE 4 - RECOLOR THE DECORATIVE/ACCENT PALETTE TO MATCH THE NEW LOGO
This rule applies whether the reference has one photo slot or several - it is not specific to any one layout.

- Identify the NEW LOGO IMAGE's own color palette - its distinct accent color(s) (e.g. "grey and orange"). Don't count plain white/black as an "accent" unless the logo itself clearly uses one of them as a deliberate design color alongside its other accent(s).
- Identify every place in the REFERENCE that uses ITS OWN brand/accent color(s) for decorative or brand-styling purposes - this includes (not limited to): the CTA button's background/accent color, checklist or benefit-list icon colors, card/panel borders, corner shapes and decorative dividers or ribbons (excluding any third-party review badge - see below), and any other colored shape or accent that exists for brand styling rather than as literal photo content.
- REPLACE each of those reference accent colors with the corresponding color from the NEW LOGO's own palette. Keep every shape, position, size, and style of those elements EXACTLY as the reference has them - only the color itself changes, nothing else about them.
- If the reference uses more than one accent color (e.g. a neutral grey plus a vivid highlight color) and the new logo also has more than one, map them sensibly: the reference's neutral/muted tone maps to the logo's own neutral/muted tone, and the reference's vivid/distinctive accent maps to the logo's own vivid/distinctive accent - don't map a muted reference tone to the logo's most vivid color or vice versa.
- **Do NOT recolor:** any third-party review/rating badge (its own official colors - e.g. Google's blue/red/yellow/green - are fixed and must never change); the actual photo content; and plain neutral text/background colors that were never a deliberate brand-accent choice in the reference (e.g. plain black body text on a plain white card stays black-on-white - that's not a "brand color" to swap).

---

# STRICT CONSTRAINTS
- Do NOT add, remove, or rearrange any element other than the LOGO, PHOTO, HEADER, and SUBTITLE (the one exception: when a line ends up with no new text, whatever sits below shifts up to close that gap - see CHANGE 3).
- Do NOT leave a large empty blank gap where a removed line used to be - close it up per CHANGE 3's four cases, don't just erase text and leave a hole.
- Do NOT keep any remnant of the old logo, old headline, old subtitle, or old photo.
- Do NOT fall back to the reference's own headline/subtitle wording for any reason - not if the new text is short, not if nothing was given for that line at all. When in doubt, leave that line blank rather than reusing the reference's words.
- Do NOT invent icons, captions, watermarks, or a review/rating badge that wasn't in the reference.
- Do NOT alter the CTA's text/font/shape/position, other body copy's words/position, checklist/benefit list wording/position, badges' content/position, background layout, or canvas size - but DO recolor their decorative/accent COLORS to match the new logo's palette per CHANGE 4 (this is the one deliberate exception to "do not alter").
- Do NOT recolor any third-party review/rating badge - its own official colors are fixed regardless of CHANGE 4.
- No spelling errors, no placeholder text, no duplicated text.
- Output: one finished image at reference dimensions - print-clean, no mockups, no borders, no annotations.

---

# FINAL SELF-CHECK (confirm all before output)
- [ ] **STOP AND RE-EXAMINE THE HEADER/SUBTITLE AREA SPECIFICALLY: is there any word left over from the reference's own headline or subtitle that shouldn't be there per the four cases in CHANGE 3?** If yes, this output is a failure - remove it before finalizing, even if it means redoing the area from scratch.
- [ ] Only LOGO, PHOTO, HEADER, SUBTITLE, and decorative/accent COLORS (per CHANGE 4) changed; the CTA's text/font/shape/position, other body copy's wording/position, checklist/benefit list wording/position, badges' content/position, and background layout are otherwise untouched.
- [ ] No trace of the old logo or any old photo remains, in any slot.
- [ ] The header/subtitle area exactly matches whichever of the four CHANGE 3 cases applied - correct line(s) replaced with the exact new text, the other line (if applicable) fully removed and reflowed, with no leftover empty space.
- [ ] Any review/rating badge (e.g. Google reviews) still shows its original wordmark, rating, and text unchanged - the new logo was NOT placed there.
- [ ] Each line's casing mirrors its own reference line (ALL CAPS / Title Case / Sentence case) - not the other line's casing.
- [ ] Logo, header, and CTA all share the identical alignment axis from the reference.
- [ ] Header/subtitle typography weight and stroke finish match the reference - sharp, consistent, professional.
- [ ] Header/subtitle area fits cleanly - no overflow, clipping, or overlap.
- [ ] The logo is rendered generously sized within its footprint - not small and swimming in excess background.
- [ ] **Zoom in mentally on the logo's icon: if it's made of overlapping/interlocking letterforms, is each individual letter still clearly legible, with the exact cut line between them intact?** If the shapes have blurred, merged, or warped into an unclear blob, this is a failure - redo the icon so it matches the NEW LOGO IMAGE's precise geometry.
- [ ] Each photo slot's edge treatment matches its reference slot exactly - if a reference photo fades/feathers softly into the background, the new one does too, with no hard seam line.
- [ ] Every photo slot shows one of the actual NEW PHOTO IMAGES' own subject/scene - not the reference's original photo, not an invented substitute. If there were multiple new photos, all of them were used somewhere, in the correct order (primary slot first).
- [ ] Every decorative/accent color (CTA background, checklist icons, borders, corner shapes, dividers, ribbons, etc.) has been recolored to match the NEW LOGO's own palette - not left as the reference's original accent colors. Any third-party review/rating badge is the one exception and keeps its own official colors unchanged.
- [ ] Output dimensions match the reference."""
