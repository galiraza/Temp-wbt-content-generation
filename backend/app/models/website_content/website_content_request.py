import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base

#: How many refinement passes one section gets. Mirrors
#: app.agents.website_content.refine.MAX_TURNS, which is the n8n loop_condition
#: (`turn > 2`) it came from. Declared here too so the API layer can report the
#: ceiling without importing the agent package.
MAX_REFINEMENT_TURNS = 2


class WebsiteContentRequest(Base):
    """One website-content brief for one client, and the run it produced.

    The n8n workflow this replaces kept nothing. Its form fed straight into the
    agents and the finished markdown was POSTed to a Zapier webhook, so a run
    could not be re-read, re-run, corrected or audited afterwards -- and the
    intermediate work that shaped every page (the meeting analysis, the parsed
    sitemap, the industry classification) was discarded the moment it was used.
    Every one of those is a column here.

    One status, not two, unlike BlogGenerationRequest: this module runs the whole
    chain from a single submit, so there is no cheap phase to commit to first.
    `intake_*` columns record what the first half produced, but they are not a
    separate user-facing step.
    """

    __tablename__ = "website_content_requests"

    id = Column(Integer, primary_key=True, index=True)

    # --- the form, one column per field ---
    business_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    email = Column(String, nullable=False)
    address = Column(String, nullable=False)
    country = Column(String, nullable=False)
    state_province_region = Column(String, nullable=False)
    zip_postal_code = Column(String, nullable=False)
    usps = Column(Text, nullable=False)

    # The agreed page list. Highest authority in every prompt: no page, service
    # or area may appear in the output unless it appears here.
    sitemap_text = Column(Text, nullable=False)

    # JSON-encoded list of the ticked industry options, plus the free-text box
    # for anything not on the list. Same JSON-in-a-Text-column convention as
    # Blog.keywords -- see industries_list below.
    industries = Column(Text, nullable=True)
    other_industries = Column(Text, nullable=True)

    # Fathom is fetched by URL; Loom is pasted as text. That asymmetry is the
    # workflow's, and Command HQ's API documentation spells it out for callers.
    fathom_meeting_1_url = Column(String, nullable=True)
    fathom_meeting_2_url = Column(String, nullable=True)
    fathom_meeting_3_url = Column(String, nullable=True)
    loom_1_summary = Column(Text, nullable=True)
    loom_1_transcript = Column(Text, nullable=True)
    loom_2_summary = Column(Text, nullable=True)
    loom_2_transcript = Column(Text, nullable=True)
    loom_3_summary = Column(Text, nullable=True)
    loom_3_transcript = Column(Text, nullable=True)

    # --- what the intake phase produced ---
    #: The Meeting Insights object: services, areas, pricing, exclusions, pending
    #: approvals, strategic priorities. Every page prompt injects this whole
    #: blob, so it is stored whole rather than shredded into columns.
    meeting_insights = Column(Text, nullable=True)
    #: The parsed sitemap, as the extractor returned it.
    sitemap_data = Column(Text, nullable=True)
    #: The ticked industries joined with anything the classifier matched out of
    #: `other_industries`. This exact string is what routes the page agents to
    #: their knowledge-base tools.
    resolved_industries = Column(Text, nullable=True)

    # --- the run ---
    # pending | generating | complete | partial | failed
    #   complete -> every section written, all passed their evaluator
    #   partial  -> written, but at least one section needs review or failed
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    #: The kickoff-meeting warning, in the wording Command HQ's callers are
    #: already told to expect. Empty on a normal run.
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sections = relationship(
        "WebsiteSection",
        back_populates="request",
        order_by="WebsiteSection.position",
        cascade="all, delete-orphan",
    )

    @property
    def industries_list(self) -> list:
        """The ticked industries. Bad JSON reads as empty rather than raising:
        a display path must not 500 because one row was written oddly. Same
        convention as Blog.keyword_list."""
        if not self.industries:
            return []
        try:
            value = json.loads(self.industries)
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []

    @property
    def insights(self) -> dict:
        if not self.meeting_insights:
            return {}
        try:
            value = json.loads(self.meeting_insights)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @property
    def sitemap(self) -> dict:
        if not self.sitemap_data:
            return {}
        try:
            value = json.loads(self.sitemap_data)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}
