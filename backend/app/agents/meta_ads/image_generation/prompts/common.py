"""Shared prompt text used across multiple image generation team agents."""

STYLE_GUIDE = (
    "Polished, professional Meta (Facebook/Instagram) ad creative image."
)

# ---------------------------------------------------------------------------
# WIREFRAME_RULE
# Role: the core instruction for how a user-supplied reference image should be
# used when one is present. The reference is passed to the image model as the
# FIRST input image (see generator_agent.py) — this rule tells the model, in
# those exact terms, to treat image #1 as a positions-only blueprint and the
# remaining images (company logo/photos) as the actual content to place into
# those positions. It is explicitly NOT a source of actual content: not its
# photo, not its words, not its own logo, not any extra design elements.
# Shared by editor_prompts.py (revision flow) so behavior stays consistent
# with the generation flow's rules.
# ---------------------------------------------------------------------------
WIREFRAME_RULE = (
    "The FIRST input image is the reference — use it ONLY as a positions blueprint, never as "
    "content and never as a color source. The remaining input images are the company's own "
    "logo/photos — these are the actual content AND the actual color source, and they must "
    "reach the final image UNALTERED (only placed, resized, and cropped to fit — never "
    "redrawn, recolored, restyled, or otherwise modified). Do only these four things:\n"
    "1. Logo location — place the company's own logo (one of the other input images) at the "
    "same spot/size the reference's logo/badge occupies, using the logo's own artwork and "
    "colors exactly as provided, unaltered. Exactly one logo, nowhere else. If the reference "
    "has no logo, add none.\n"
    "2. Text — if new text is given below (from header text or additional info), place it at "
    "the same spot/size the reference's text occupies, in a color taken from the company "
    "logo's own color palette (not the reference's text color). If NO new text is given below, "
    "render NO text anywhere in the image — do not use the reference's own words as a "
    "fallback, leave that area empty/blank instead.\n"
    "3. Image location — place the company photo (another one of the other input images) at "
    "the same spot/size/crop the reference's subject photo occupies, unaltered.\n"
    "4. Overall color scheme — do not need to change the reference's overall composition, but "
    "the logo's own color palette can be used for design accents and text color.\n"
    "Do NOT copy anything else from the reference image itself: not its actual photo/subject, "
    "not its actual words, not its own logo artwork, not its own colors, not its specific font "
    "choice, not any of its other design elements (shapes, icons, borders, extra badges, "
    "textures). Do not add anything that isn't one of the four items above. Do not duplicate "
    "the logo. Do not leave the reference's original text visible anywhere. Do not alter, "
    "redraw, recolor, or restyle the company's own logo/photo images — place them as-is."
)