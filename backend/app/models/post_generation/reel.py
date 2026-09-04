import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base

#: The four slots in the month that are reels, and the angle each one carries.
#: Straight from the WF1 Content Generator prompt's slot table, with the reel set
#: moved to 2, 5, 8, 11 (slots 2 and 9 were swapped, by explicit request).
REEL_SLOT_THEMES = {
    2: "Behind the scenes",
    5: "Urgency and seasonal",
    8: "Myth-busting",
    11: "Emotional wellbeing",
}

#: Slot numbers that are reels. Everything else in 1-12 is a static post, which
#: is what routes each parsed item to its table at insert time.
REEL_SLOTS = tuple(sorted(REEL_SLOT_THEMES))


class Reel(Base):
    """One generated reel: the on-screen script, a caption, and hashtags.

    A reel has NO title. The prompt gives a static post an Image/Video Title but
    gives a reel only Reel Text and Reel Caption, so inventing a title column
    would mean inventing the content to fill it.

    Its own table, chat board and images table rather than sharing the post ones:
    reels are an independent module.
    """

    __tablename__ = "reels"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("post_generation_requests.id"), nullable=False, index=True
    )
    # 2, 5, 8 or 11 — the slot in the 12-item month, not a 1-4 sequence. Keeping
    # the real slot number is what makes the calendar order meaningful and lets a
    # single reel be regenerated into the right angle.
    reel_number = Column(Integer, nullable=False)
    theme = Column(String, nullable=False)  # one of REEL_SLOT_THEMES.values()

    # The on-screen script. Multi-line on purpose: each line is a separate text
    # card for whoever edits the video, so the line breaks carry meaning.
    reel_text = Column(Text, nullable=False)
    caption = Column(Text, nullable=False)  # includes the CTA block
    hashtags = Column(Text, nullable=True)  # JSON-encoded list of "#tag" strings
    # Same hero-photo match as Post.hero_image_id - see that column's comment.
    hero_image_id = Column(Integer, ForeignKey("hero_images.id"), nullable=True)

    status = Column(String, nullable=False, default="pending")  # pending | approved
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def hashtag_list(self) -> list:
        if not self.hashtags:
            return []
        try:
            value = json.loads(self.hashtags)
        except (json.JSONDecodeError, TypeError):
            return []
        return value if isinstance(value, list) else []

    request = relationship("PostGenerationRequest", back_populates="reels")
    hero_image = relationship("HeroImage")
    chat_messages = relationship(
        "ReelChatMessage",
        back_populates="reel",
        order_by="ReelChatMessage.created_at",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "ReelImage",
        back_populates="reel",
        order_by="ReelImage.created_at",
        cascade="all, delete-orphan",
    )


class ReelChatMessage(Base):
    """The copy chat board for one reel.

    Its own table, so reel_id can be NOT NULL — unlike post_chat_messages, which
    carries two nullable FKs because it serves posts and reviews.

    An assistant turn proposing a change stores JSON holding ONLY the fields it
    wants to change, so one turn can rewrite the hashtags without touching the
    script. Nothing is applied until the user approves the message.
    """

    __tablename__ = "reel_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    reel_id = Column(Integer, ForeignKey("reels.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reel = relationship("Reel", back_populates="chat_messages")


class ReelImage(Base):
    """One generated image version for a reel.

    Holds no generation inputs, for the same reason PostImage does not: the script,
    caption and hashtags are on the parent, and logo_path / post_image_paths /
    industry are on the request. A second copy could only drift from the first.

    Versioned by INSERT — an approved revision adds a row rather than overwriting,
    so the image chat keeps a full history.

    Nothing writes here yet: reel image generation is not built.
    """

    __tablename__ = "reel_images"

    id = Column(Integer, primary_key=True, index=True)
    reel_id = Column(Integer, ForeignKey("reels.id"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    background_path = Column(String, nullable=True)
    layout_variant = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reel = relationship("Reel", back_populates="images")
    chat_messages = relationship(
        "ReelImageChatMessage",
        back_populates="reel_image",
        order_by="ReelImageChatMessage.created_at",
        cascade="all, delete-orphan",
    )


class ReelImageChatMessage(Base):
    """The image chat board for one reel image version, separate from the copy
    board. An assistant turn carrying an approvable candidate stores
    {"file_path": ...}; approving it inserts a new ReelImage row."""

    __tablename__ = "reel_image_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    reel_image_id = Column(Integer, ForeignKey("reel_images.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    attachment_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reel_image = relationship("ReelImage", back_populates="chat_messages")
