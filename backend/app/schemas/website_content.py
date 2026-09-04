from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The industry options the form offers, exactly as the n8n form trigger listed
#: them and as Command HQ's API documentation tells callers to send them --
#: including "ASHP " with its trailing space and "Signage and  Shoplifting" with
#: its double space, both of which are in the live option list. They are trimmed
#: on the way in (see WebsiteContentRequestCreate._clean_industries) but the
#: display strings are kept verbatim so a value copied from either system
#: matches.
INDUSTRY_OPTIONS = [
    "Air Conditioner",
    "ASHP",
    "Bathroom Installation",
    "Boiler",
    "Canopy Verandas",
    "Damp Proofing",
    "Doors and Windows",
    "Driveway and Patio",
    "ECO4",
    "Electrical",
    "EV Charger",
    "Fire Protection",
    "Garden Rooms",
    "Insulation",
    "Insurance Claim",
    "Networking Service",
    "Painting and Decorating",
    "Property Maintenance",
    "Roofing",
    "Security Installer",
    "Signage and Shoplifting",
    "Skin Booster",
    "Solar",
    "Stairlifts and Homelifts",
    "Swimming pool",
    "Television",
    "Wood Burning Stove",
]


class WebsiteContentRequestCreate(BaseModel):
    """The submitted brief. JSON rather than multipart: there are no assets.

    Required-ness matches the n8n form trigger exactly. Everything about the
    meetings is optional -- a run with no meeting at all still produces content,
    and says so in `note`.
    """

    business_name: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    email: str = Field(min_length=1)
    address: str = Field(min_length=1)
    country: str = Field(min_length=1)
    state_province_region: str = Field(min_length=1)
    zip_postal_code: str = Field(min_length=1)
    usps: str = Field(min_length=1)
    sitemap_text: str = Field(min_length=1)

    industries: List[str] = []
    other_industries: Optional[str] = None

    fathom_meeting_1_url: Optional[str] = None
    fathom_meeting_2_url: Optional[str] = None
    fathom_meeting_3_url: Optional[str] = None
    loom_1_summary: Optional[str] = None
    loom_1_transcript: Optional[str] = None
    loom_2_summary: Optional[str] = None
    loom_2_transcript: Optional[str] = None
    loom_3_summary: Optional[str] = None
    loom_3_transcript: Optional[str] = None

    @field_validator("industries", mode="before")
    @classmethod
    def _clean_industries(cls, value):
        """Trims and de-duplicates, preserving order.

        Not validated against INDUSTRY_OPTIONS: the list is a prompt input, not
        an enum, and the page agents map whatever arrives onto their five
        knowledge bases by meaning. Rejecting an unlisted industry here would
        turn a prefill mismatch into a failed submit.
        """
        if value is None:
            return []
        if isinstance(value, str):
            value = [v for v in value.split(",")]
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("*", mode="before")
    @classmethod
    def _trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class WebsiteContentRequestUpdate(WebsiteContentRequestCreate):
    """Editing the brief. Same shape as creating one."""


class CarryForwardOut(BaseModel):
    """One issue the evaluator handed to the next Critic round."""

    issue: str = ""
    tag: str = ""
    severity: str = ""
    text: str = ""


class RefinementRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turn: int
    critic_report: Optional[str] = None
    refined_content: Optional[str] = None
    verdict: Optional[str] = None
    reason: Optional[str] = None
    checks: Dict[str, bool] = {}
    carry_forward: List[CarryForwardOut] = []
    created_at: datetime


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    section_key: str
    section_title: str
    position: int

    content: Optional[str] = None
    #: Our own count of the shipped markdown, so the UI can show section sizes
    #: without every client re-counting the same text.
    word_count: int = 0

    blog_industry: Optional[str] = None
    blog_service: Optional[str] = None
    blog_titles: Optional[str] = None
    blog_keywords: Optional[str] = None

    refinement_turns: int = 0
    verdict: Optional[str] = None
    verdict_reason: Optional[str] = None
    checks: Dict[str, bool] = {}

    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SectionDetailOut(SectionOut):
    """One section plus its refinement history and its pre-refinement draft.

    Only the detail endpoint returns these: a six-section list would otherwise
    carry up to twelve critic reports and twelve full page rewrites.
    """

    draft: Optional[str] = None
    rounds: List[RefinementRoundOut] = []


class SectionUpdate(BaseModel):
    """Direct manual edit, no LLM involved. The verdict is left untouched: it
    describes what the model produced, and silently repointing it at hand-edited
    text would misreport what was evaluated."""

    content: str


class WebsiteContentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_name: str
    phone_number: str
    email: str
    address: str
    country: str
    state_province_region: str
    zip_postal_code: str
    usps: str
    sitemap_text: str
    industries: List[str] = []
    other_industries: Optional[str] = None

    fathom_meeting_1_url: Optional[str] = None
    fathom_meeting_2_url: Optional[str] = None
    fathom_meeting_3_url: Optional[str] = None
    loom_1_summary: Optional[str] = None
    loom_1_transcript: Optional[str] = None
    loom_2_summary: Optional[str] = None
    loom_2_transcript: Optional[str] = None
    loom_3_summary: Optional[str] = None
    loom_3_transcript: Optional[str] = None

    #: The ticked industries plus whatever the classifier matched out of the
    #: free-text box. This is what actually routed the knowledge-base tools, so
    #: it is worth showing rather than leaving the user to infer it.
    resolved_industries: Optional[str] = None

    status: str
    error_message: Optional[str] = None
    note: Optional[str] = None

    # The meeting analysis and the parsed sitemap are large, and the list view
    # only needs to know they exist.
    has_meeting_insights: bool = False
    has_sitemap_data: bool = False
    section_count: int = 0
    passed_count: int = 0
    total_words: int = 0

    created_at: datetime
    updated_at: datetime


class WebsiteContentRequestDetailOut(WebsiteContentRequestOut):
    """The brief plus the intake work that shaped it.

    `meeting_insights` and `sitemap_data` are the two things the n8n workflow
    used and threw away. They explain every downstream decision, so the detail
    view carries them.
    """

    meeting_insights: Dict[str, Any] = {}
    sitemap_data: Dict[str, Any] = {}


class WebsiteContentResult(BaseModel):
    """What the generate endpoint returns immediately.

    Generation runs in the background, so this is the accepted-and-started state,
    not the finished one -- poll GET /{id} and GET /{id}/sections for progress.
    """

    request: WebsiteContentRequestOut
    sections: List[SectionOut] = []
    started: bool = True
