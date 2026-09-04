from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class HeroImage(Base):
    """One AI-generated candidate background photo for a request's month.

    12 of these are generated once per request (see hero_image_prompt.py /
    hero_image_agent.py), then matched to individual posts/reels by the
    content-matching agent, which reads `usage` to avoid overusing the same
    photo. Scoped per-request, not shared across a client's history: each
    new month gets its own fresh set of 12, usage starting at 0 - the direct
    equivalent of the n8n workflow's run_key (company+month) grouping, since
    a request already IS that same company+month unit.

    `summary` doubles as both the record of what prompt produced this image
    and the description the content-matching agent reads to judge fit - the
    n8n version stored the two as one field for the same reason.
    """

    __tablename__ = "hero_images"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("post_generation_requests.id"), nullable=False, index=True
    )
    # 1-12, matching the slot in hero_image_prompt.py's output array - stable
    # for the life of the request, so a post's hero_image_id reference and a
    # human looking at "Hero Image 7" both mean the same photo.
    slot = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    usage = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("PostGenerationRequest", back_populates="hero_images")
