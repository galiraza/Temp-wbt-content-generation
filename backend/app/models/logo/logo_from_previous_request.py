from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class LogoFromPreviousRequest(Base):
    __tablename__ = "logo_from_previous_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=True)
    logo_path = Column(String, nullable=False)
    suggestion = Column(Text, nullable=True)
    use_ai_suggestion = Column(Boolean, nullable=False, default=False)
    fathom_url = Column(String, nullable=True)
    fathom_transcript = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = relationship(
        "LogoImage",
        back_populates="previous_request",
        order_by="LogoImage.slot, LogoImage.created_at",
        cascade="all, delete-orphan",
    )
