from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class PostChatMessage(Base):
    """The copy chat board for one post OR one review.

    Exactly one of post_id / review_id is set — the same polymorphic-parent
    pattern LogoImage already uses for its two request types.

    An assistant turn that proposes a change stores JSON holding ONLY the fields
    it wants to change, so one turn can rewrite the hashtags without touching the
    caption. A conversational reply with nothing to approve is stored as plain
    text. Nothing is applied until the user approves the message.
    """

    __tablename__ = "post_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=True, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="chat_messages")
    review = relationship("Review", back_populates="chat_messages")
