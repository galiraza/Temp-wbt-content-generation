import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class BlogQcRound(Base):
    """One audit of one blog: the score, the verdict, and the fixes it asked for.

    n8n kept none of this — each QC reply overwrote the last, so "why did blog 7
    fail four times" was unanswerable. One row per round makes the revision loop
    inspectable after the fact, and is what any tuning of PASS_THRESHOLD needs.
    """

    __tablename__ = "blog_qc_rounds"

    id = Column(Integer, primary_key=True, index=True)
    blog_id = Column(Integer, ForeignKey("blogs.id"), nullable=False, index=True)
    # 1 for the first draft's audit, 2+ for audits of a revision.
    round_number = Column(Integer, nullable=False)

    score = Column(Integer, nullable=True)
    result = Column(String, nullable=True)  # PASS | FAIL
    word_count = Column(Integer, nullable=True)
    fixes = Column(Text, nullable=True)      # JSON-encoded list of strings
    breakdown = Column(Text, nullable=True)  # JSON-encoded dict of sub-scores

    created_at = Column(DateTime, default=datetime.utcnow)

    blog = relationship("Blog", back_populates="qc_rounds")

    @property
    def fix_list(self) -> list:
        if not self.fixes:
            return []
        try:
            value = json.loads(self.fixes)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @property
    def breakdown_dict(self) -> dict:
        if not self.breakdown:
            return {}
        try:
            value = json.loads(self.breakdown)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
