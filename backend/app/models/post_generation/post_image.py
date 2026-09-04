from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class PostImage(Base):
    """One generated image version for a post or a review.

    Deliberately holds no generation inputs. Everything the image is built from
    already exists in other rows: title/caption/hashtags on the parent, and
    logo_path / post_image_paths / industry on the request. Storing them again
    would be a second copy that can drift from the first.

    Versioned by INSERT: an approved revision adds a row rather than overwriting,
    so the image chat keeps a full history. Copy, by contrast, overwrites in
    place.
    """

    __tablename__ = "post_images"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=True, index=True)
    file_path = Column(String, nullable=False)
    # Which candidate photo this version was composed from, and which of the
    # layout variants was rolled. Kept only so "try another layout" and "keep
    # this layout, redo it" are possible — the variant is picked at random.
    background_path = Column(String, nullable=True)
    layout_variant = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="images")
    review = relationship("Review", back_populates="images")
    chat_messages = relationship(
        "PostImageChatMessage",
        back_populates="post_image",
        order_by="PostImageChatMessage.created_at",
        cascade="all, delete-orphan",
    )


class PostImageChatMessage(Base):
    """The image chat board, a separate thread from the copy chat.

    Hangs off post_images.id, so it serves posts and reviews with no extra
    column. An assistant turn carrying an approvable candidate stores
    {"file_path": ...} as JSON; approving it inserts a new PostImage row.
    """

    __tablename__ = "post_image_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    post_image_id = Column(Integer, ForeignKey("post_images.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    attachment_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post_image = relationship("PostImage", back_populates="chat_messages")
