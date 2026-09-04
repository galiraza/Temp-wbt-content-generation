from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class LogoFromScratchRequest(Base):
    __tablename__ = "logo_from_scratch_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    industry = Column(String, nullable=False)
    usps = Column(Text, nullable=True)
    fathom_url = Column(String, nullable=True)
    fathom_transcript = Column(Text, nullable=True)
    suggestion = Column(Text, nullable=True)
    use_ai_suggestion = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = relationship(
        "LogoImage",
        back_populates="scratch_request",
        order_by="LogoImage.slot, LogoImage.created_at",
        cascade="all, delete-orphan",
    )
