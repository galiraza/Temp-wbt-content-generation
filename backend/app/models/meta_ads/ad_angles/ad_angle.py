from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AdAngleRequest(Base):
    __tablename__ = "ad_angle_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    offers = Column(Text, nullable=False)
    service_name = Column(String, nullable=False)
    service_content = Column(Text, nullable=False)
    industry = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    angles = relationship(
        "AdAngle",
        back_populates="request",
        order_by="AdAngle.order",
        cascade="all, delete-orphan",
    )


class AdAngle(Base):
    __tablename__ = "ad_angles"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("ad_angle_requests.id"), nullable=False, index=True)
    headline = Column(String, nullable=False)
    primary_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | approved
    order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    request = relationship("AdAngleRequest", back_populates="angles")
    chat_messages = relationship(
        "AngleChatMessage",
        back_populates="angle",
        order_by="AngleChatMessage.created_at",
        cascade="all, delete-orphan",
    )
    images = relationship(
        "AngleImage",
        back_populates="angle",
        order_by="AngleImage.created_at",
        cascade="all, delete-orphan",
    )


class AngleChatMessage(Base):
    __tablename__ = "angle_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    angle_id = Column(Integer, ForeignKey("ad_angles.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    angle = relationship("AdAngle", back_populates="chat_messages")
