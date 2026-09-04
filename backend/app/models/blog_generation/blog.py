import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base

#: The QC score a blog must reach to pass, out of 10. Straight from the n8n
#: "If" node (score >= 7) and the QC prompt's own scoring rules.
PASS_THRESHOLD = 7

#: How many QC rounds one blog gets: the first draft's audit plus up to three
#: re-audits after revision. n8n used `revision_attempts == 4` against a single
#: shared counter row; this is the same ceiling, counted per blog.
MAX_QC_ROUNDS = 4


class Blog(Base):
    """One blog in a cluster: its brief, its three outputs, and its QC verdict.

    The n8n data table stored only blog_number, blog_content and blog_score, so
    the title, funnel stage, keywords, GMB Post and GMB FAQ were generated and
    then thrown away. All of them are columns here.

    `revision_attempts` is per blog on purpose. n8n kept it in one shared row of
    a separate "Revision Attempts Saver" table, filtered `>= 0`, so two runs at
    once corrupted each other's retry counts.
    """

    __tablename__ = "blogs"
    __table_args__ = (
        # The blog number identifies a blog within its cluster, so it has to be
        # unique there — a duplicate would make "regenerate blog 7" ambiguous.
        UniqueConstraint("request_id", "blog_number", name="uq_blogs_request_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("blog_generation_requests.id"), nullable=False, index=True
    )

    # --- the brief, from the metadata extractor ---
    blog_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    funnel_stage = Column(String, nullable=True)
    service_areas = Column(Text, nullable=True)  # JSON-encoded list of strings
    keywords = Column(Text, nullable=True)  # JSON-encoded list of strings

    # --- the three required outputs ---
    content = Column(Text, nullable=True)  # the blog itself, markdown
    gmb_post = Column(Text, nullable=True)  # <= 300 chars, <= 2 emoji
    gmb_faq = Column(Text, nullable=True)  # <= 70 words

    # Pulled out of the blog body, which is where the prompt puts them.
    meta_title = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    general_notes = Column(Text, nullable=True)

    # --- the QC verdict of the most recent round ---
    qc_score = Column(Integer, nullable=True)
    qc_result = Column(String, nullable=True)  # PASS | FAIL
    qc_word_count = Column(Integer, nullable=True)
    qc_fixes = Column(Text, nullable=True)  # JSON-encoded list of strings
    qc_breakdown = Column(Text, nullable=True)  # JSON-encoded dict of 8 sub-scores
    revision_attempts = Column(Integer, nullable=False, default=0)

    # pending | generating | passed | failed_qc | failed
    #   passed    -> qc_score >= PASS_THRESHOLD
    #   failed_qc -> ran out of rounds still below the threshold; the content is
    #                kept and shown, because a 6/10 blog is worth editing
    #   failed    -> the model or the parse blew up; there is nothing to show
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    request = relationship("BlogGenerationRequest", back_populates="blogs")
    qc_rounds = relationship(
        "BlogQcRound",
        back_populates="blog",
        order_by="BlogQcRound.round_number",
        cascade="all, delete-orphan",
    )

    def _decode_list(self, raw) -> list:
        """Same JSON-in-a-Text-column convention as Post.hashtag_list. Bad JSON
        reads as empty rather than raising: a display path must not 500 because
        one row was written oddly."""
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @property
    def keyword_list(self) -> list:
        return self._decode_list(self.keywords)

    @property
    def service_area_list(self) -> list:
        return self._decode_list(self.service_areas)

    @property
    def fix_list(self) -> list:
        return self._decode_list(self.qc_fixes)

    @property
    def breakdown(self) -> dict:
        if not self.qc_breakdown:
            return {}
        try:
            value = json.loads(self.qc_breakdown)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
