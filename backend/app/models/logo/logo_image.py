from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class LogoImage(Base):
    """One version of one of the 3 generated logo concepts for a request.

    Exactly one of scratch_request_id / previous_request_id is set, matching
    whichever of the two request types this logo belongs to. `slot` (1-3)
    identifies which of the 3 initial concepts a version belongs to — a
    request has 3 independent version histories, one per slot.
    """

    __tablename__ = "logo_images"

    id = Column(Integer, primary_key=True, index=True)
    scratch_request_id = Column(
        Integer, ForeignKey("logo_from_scratch_requests.id"), nullable=True, index=True
    )
    previous_request_id = Column(
        Integer, ForeignKey("logo_from_previous_requests.id"), nullable=True, index=True
    )
    slot = Column(Integer, nullable=False)  # 1, 2, or 3
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    scratch_request = relationship("LogoFromScratchRequest", back_populates="images")
    previous_request = relationship("LogoFromPreviousRequest", back_populates="images")
    chat_messages = relationship(
        "LogoImageChatMessage",
        back_populates="logo_image",
        order_by="LogoImageChatMessage.created_at",
        cascade="all, delete-orphan",
    )


class LogoImageChatMessage(Base):
    __tablename__ = "logo_image_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    logo_image_id = Column(Integer, ForeignKey("logo_images.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    attachment_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    logo_image = relationship("LogoImage", back_populates="chat_messages")
