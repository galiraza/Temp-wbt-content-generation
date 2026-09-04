"""Logo generation agents: produce the 3 initial logo images for a request
and revise a single logo image from chat feedback.

  Generator (generator_agent.py): generate_logo_concepts() for "from
    scratch" (text-to-image, 3 concept directions) and generate_logo_edits()
    for "from previous logo" (image-to-image, 3 variation directions).
  Editor (editor_agent.py):       revises an existing generated logo image
    from chat feedback.
  Transcript extraction (transcript_extraction_agent.py): condenses a Fathom
    meeting transcript into a short logo/branding brief fed into generation.
  Creative Direction (creative_direction_agent.py): invents a visual brief
    when the user left "Your Suggestion" empty, for generate_logo_concepts().
  USP Style (usp_style_agent.py): distills raw USP text into 3-4 short
    brand-personality keywords, for generate_logo_concepts().
"""

from app.agents.logo.creative_direction_agent import generate_ai_creative_direction
from app.agents.logo.editor_agent import revise_logo_image
from app.agents.logo.generator_agent import generate_logo_concepts, generate_logo_edits
from app.agents.logo.transcript_extraction_agent import extract_logo_brief
from app.agents.logo.usp_style_agent import extract_usp_style_keywords

__all__ = [
    "generate_ai_creative_direction",
    "generate_logo_concepts",
    "generate_logo_edits",
    "revise_logo_image",
    "extract_logo_brief",
    "extract_usp_style_keywords",
]
