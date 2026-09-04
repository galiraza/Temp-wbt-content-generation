import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base

#: The static slots in the month, and the content type each one carries. Straight
#: from the WF1 Content Generator prompt's slot table. Slots 2, 5, 8 and 11 are
#: missing on purpose: those are reels (see models.post_generation.reel).
#:
#: Keyed by slot number rather than being a 0-7 list, because the numbers are no
#: longer contiguous. Regenerating one post has to know which slot it is filling,
#: or post 3 stops being the myth-busting post and the month loses its shape.
POST_SLOT_THEMES = {
    1: "Educational",
    3: "Myth-busting",
    4: "Benefit-led",
    6: "Behind the scenes",
    7: "Trust-building",
    9: "Lifestyle and family",
    10: "Lifestyle and seasonal",
    12: "Inspirational",
}

#: Slot numbers that are static posts.
POST_SLOTS = tuple(sorted(POST_SLOT_THEMES))


class Post(Base):
    """One generated social post: title, caption, hashtags.

    Separate table from Review rather than one table with a `kind` column: the
    two carry different fields, and every review-only column would otherwise sit
    null on eight post rows.
    """

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("post_generation_requests.id"), nullable=False, index=True
    )
    # One of POST_SLOTS, so 1, 3, 4, 6, 7, 8, 10 or 12. The slot in the 12-item
    # month, not a 1-8 sequence: the gaps are where the reels sit.
    post_number = Column(Integer, nullable=False)
    theme = Column(String, nullable=False)  # one of POST_SLOT_THEMES.values()

    title = Column(String, nullable=False)
    caption = Column(Text, nullable=False)  # includes the CTA block
    hashtags = Column(Text, nullable=True)  # JSON-encoded list of "#tag" strings
    # The hero photo the content-matching agent picked for this post, out of
    # the request's shared pool of 12. Nullable: content generation and hero
    # image generation are separate steps, so a post can exist with no match
    # yet. Set null rather than deleted if its HeroImage is ever removed -
    # the post's own content must never disappear because of an image
    # cleanup.
    hero_image_id = Column(Integer, ForeignKey("hero_images.id"), nullable=True)

    status = Column(String, nullable=False, default="pending")  # pending | approved
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def hashtag_list(self) -> list:
        """The hashtags column decoded. Stored as JSON text like every other list
        column here, but read as a list everywhere so callers never have to
        remember which side of the boundary they are on."""
        if not self.hashtags:
            return []
        try:
            value = json.loads(self.hashtags)
        except (json.JSONDecodeError, TypeError):
            return []
        return value if isinstance(value, list) else []

    request = relationship("PostGenerationRequest", back_populates="posts")
    hero_image = relationship("HeroImage")
    chat_messages = relationship(
        "PostChatMessage",
        back_populates="post",
        order_by="PostChatMessage.created_at",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "PostImage",
        back_populates="post",
        order_by="PostImage.created_at",
        cascade="all, delete-orphan",
    )
