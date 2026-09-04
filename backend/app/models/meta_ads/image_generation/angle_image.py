from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AngleImage(Base):
    __tablename__ = "angle_images"

    id = Column(Integer, primary_key=True, index=True)
    angle_id = Column(Integer, ForeignKey("ad_angles.id"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    header_text = Column(String, nullable=False)
    additional_info = Column(Text, nullable=True)
    reference_image_path = Column(String, nullable=True)
    logo_path = Column(String, nullable=True)
    # JSON-encoded array of Supabase Storage URLs — mirrors how offers/industry
    # are stored as JSON text elsewhere (AdAngleRequest), since a single angle's
    # image can use more than one company photo.
    company_image_paths = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    angle = relationship("AdAngle", back_populates="images")
    chat_messages = relationship(
        "AngleImageChatMessage",
        back_populates="angle_image",
        order_by="AngleImageChatMessage.created_at",
        cascade="all, delete-orphan",
    )


class AngleImageChatMessage(Base):
    __tablename__ = "angle_image_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    angle_image_id = Column(Integer, ForeignKey("angle_images.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    attachment_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    angle_image = relationship("AngleImage", back_populates="chat_messages")
