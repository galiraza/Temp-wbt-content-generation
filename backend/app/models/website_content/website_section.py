import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base

#: The six sections, in the order the n8n Zapier node assembled them and the
#: order the UI shows them. `key` is the agent key; `title` is the exact
#: `section_title` string the workflow wrote and Command HQ's callback contract
#: documents -- including the plural/singular inconsistency between
#: "Services Page" and "Service Area Page", which is the workflow's own.
SECTION_KEYS = ["home", "about_us", "service", "service_area", "other", "blogs"]

SECTION_TITLES = {
    "home": "Home Page",
    "about_us": "About Us Page",
    "service": "Services Page",
    "service_area": "Service Area Page",
    "other": "Other Pages",
    "blogs": "Blogs",
}


class WebsiteSection(Base):
    """One of the six sections: its markdown, its status, and its blog brief.

    A section is one agent's whole output, not one web page. Three of the six
    contain several pages in a single markdown document -- one per service, one
    per area, one per "other page" -- because that is what their prompts produce
    and what the refinement loop then reads as a unit. Splitting them into rows
    would mean re-deriving each page's identity from a heading, and would break
    the cross-section repetition checks the Critic prompt is built around.

    `content` is the text that ships. `draft` is what the writing agent produced
    before refinement, kept because the refiner sometimes trims a real fact and
    having the original is the only way to notice.
    """

    __tablename__ = "website_sections"
    __table_args__ = (
        # One row per section per request: a duplicate would make "regenerate the
        # Home Page" ambiguous.
        UniqueConstraint("request_id", "section_key", name="uq_website_sections_request_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        Integer, ForeignKey("website_content_requests.id"), nullable=False, index=True
    )

    section_key = Column(String, nullable=False)   # home | about_us | ... | blogs
    section_title = Column(String, nullable=False)  # the delivered display name
    position = Column(Integer, nullable=False)      # index into SECTION_KEYS

    content = Column(Text, nullable=True)  # the refined markdown that ships
    draft = Column(Text, nullable=True)    # what the writing agent produced first

    # --- the blogs section only ---
    # The three lead-in calls' answers. n8n discarded these, which made "why did
    # it write about boilers" unanswerable after the fact.
    blog_industry = Column(String, nullable=True)
    blog_service = Column(String, nullable=True)
    blog_titles = Column(Text, nullable=True)
    blog_keywords = Column(Text, nullable=True)

    # --- the verdict of the last refinement pass ---
    refinement_turns = Column(Integer, nullable=False, default=0)
    verdict = Column(String, nullable=True)  # PASS | REVISE
    verdict_reason = Column(Text, nullable=True)
    checks = Column(Text, nullable=True)  # JSON-encoded dict of the six booleans

    # pending | generating | passed | needs_review | unrefined | failed
    #   passed       -> the evaluator returned PASS
    #   needs_review -> ran out of turns still on REVISE; the content is kept and
    #                   shown, because a page one flag short of clean is worth
    #                   editing rather than discarding
    #   unrefined    -> the page was written but the refinement loop broke; the
    #                   draft is the content
    #   failed       -> the writing agent blew up; there is nothing to show
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    request = relationship("WebsiteContentRequest", back_populates="sections")
    rounds = relationship(
        "WebsiteRefinementRound",
        back_populates="section",
        order_by="WebsiteRefinementRound.turn",
        cascade="all, delete-orphan",
    )

    @property
    def check_results(self) -> dict:
        if not self.checks:
            return {}
        try:
            value = json.loads(self.checks)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


class WebsiteRefinementRound(Base):
    """One Critic -> Refiner -> Evaluator pass over one section.

    n8n kept none of this: each pass overwrote the last inside the loop, so
    "what did the critic actually object to" was unanswerable once a run
    finished. One row per turn makes the loop inspectable after the fact, and is
    what any tuning of MAX_REFINEMENT_TURNS would need.
    """

    __tablename__ = "website_refinement_rounds"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("website_sections.id"), nullable=False, index=True)
    turn = Column(Integer, nullable=False)  # 1-based

    critic_report = Column(Text, nullable=True)     # the critic's markdown report
    refined_content = Column(Text, nullable=True)   # what the refiner produced
    verdict = Column(String, nullable=True)         # PASS | REVISE
    reason = Column(Text, nullable=True)
    checks = Column(Text, nullable=True)            # JSON-encoded dict
    carry_forward = Column(Text, nullable=True)     # JSON-encoded list of issues

    created_at = Column(DateTime, default=datetime.utcnow)

    section = relationship("WebsiteSection", back_populates="rounds")

    @property
    def check_results(self) -> dict:
        if not self.checks:
            return {}
        try:
            value = json.loads(self.checks)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @property
    def carry_forward_list(self) -> list:
        if not self.carry_forward:
            return []
        try:
            value = json.loads(self.carry_forward)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []
