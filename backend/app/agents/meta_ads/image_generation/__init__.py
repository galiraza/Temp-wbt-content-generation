"""Image generation team: 2 agents that turn a required reference image +
header text + company logo/photo into a finished ad image.

  Generator (generator_agent.py): a single gpt-image-2 images.edit() call —
    reference image + logo + photo + header text — instructed (via
    prompts/replication_prompt.py) to replicate the reference exactly,
    swapping in only the logo, photo, and header.
  Editor (editor_agent.py):       revises an existing generated image from
    chat feedback.
"""

from app.agents.meta_ads.image_generation.editor_agent import revise_ad_image
from app.agents.meta_ads.image_generation.generator_agent import generate_ad_image

__all__ = [
    "generate_ad_image",
    "revise_ad_image",
]
