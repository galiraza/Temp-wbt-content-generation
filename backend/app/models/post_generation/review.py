import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Review(Base):
    """One generated review post, built from a real scraped customer review.

    `review` holds the customer's own words and is never rewritten by the
    generator: the WF4 Reviews Agent prompt requires the quote verbatim. `title`
    is the agent's short headline for the graphic, `caption` is the company's
    warm response to the review.
    """

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("post_generation_requests.id"), nullable=False, index=True
    )
    review_number = Column(Integer, nullable=False)  # 1-8, also the display order

    title = Column(String, nullable=False)  # the agent's 5-10 word headline
    name = Column(String, nullable=False)  # who the review is attributed to
    review = Column(Text, nullable=False)  # VERBATIM customer words
    caption = Column(Text, nullable=False)  # includes the CTA block
    hashtags = Column(Text, nullable=True)  # JSON-encoded list of "#tag" strings
    # Derived from the host of company_reviews_page_url, not generated: no agent
    # in the workflow produces it.
    platform = Column(String, nullable=True)

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

    request = relationship("PostGenerationRequest", back_populates="reviews")
    chat_messages = relationship(
        "PostChatMessage",
        back_populates="review",
        order_by="PostChatMessage.created_at",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "PostImage",
        back_populates="review",
        order_by="PostImage.created_at",
        cascade="all, delete-orphan",
    )
