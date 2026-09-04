from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BlogGenerationRequestCreate(BaseModel):
    """The submitted form. JSON rather than multipart, unlike the post and logo
    briefs: a blog cluster has no image assets."""

    client_name: str = Field(min_length=1)
    website_url: str = Field(min_length=1)
    cluster_theme_1: str = Field(min_length=1)
    cluster_theme_2: Optional[str] = None
    cluster_theme_3: Optional[str] = None
    cluster_number: Optional[int] = Field(default=None, ge=1, le=100)
    blog_schema_raw: str = Field(min_length=1)

    @field_validator("website_url")
    @classmethod
    def _require_scheme(cls, value: str) -> str:
        """Firecrawl needs an absolute URL. A bare "example.com" fails there with
        a much less obvious message than it does here."""
        cleaned = value.strip()
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        return cleaned

    @field_validator(
        "client_name", "cluster_theme_1", "cluster_theme_2", "cluster_theme_3", "blog_schema_raw"
    )
    @classmethod
    def _trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class BlogGenerationRequestUpdate(BlogGenerationRequestCreate):
    """Editing the brief. Same shape as creating one."""


class BlogQcRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    round_number: int
    score: Optional[int] = None
    result: Optional[str] = None
    word_count: Optional[int] = None
    fixes: List[str] = []
    breakdown: Dict[str, int] = {}
    created_at: datetime


class BlogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    blog_number: int
    title: str
    funnel_stage: Optional[str] = None
    service_areas: List[str] = []
    keywords: List[str] = []

    content: Optional[str] = None
    gmb_post: Optional[str] = None
    gmb_faq: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    general_notes: Optional[str] = None

    qc_score: Optional[int] = None
    qc_result: Optional[str] = None
    qc_word_count: Optional[int] = None
    qc_fixes: List[str] = []
    qc_breakdown: Dict[str, int] = {}
    revision_attempts: int = 0
    #: Our own count of the body, shown beside the QC agent's. The two disagreeing
    #: is itself a signal that the audit misread the draft.
    word_count: int = 0

    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BlogDetailOut(BlogOut):
    """One blog plus its audit history. Only the detail endpoint returns the
    rounds — a 12-blog list would otherwise carry up to 48 nested audits."""

    qc_rounds: List[BlogQcRoundOut] = []


class BlogUpdate(BaseModel):
    """Direct manual edit, no LLM involved. The QC verdict is left untouched:
    it describes what the model produced, and silently repointing it at hand-edited
    text would misreport what was audited."""

    content: str
    gmb_post: Optional[str] = None
    gmb_faq: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class BlogGenerationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_name: str
    website_url: str
    cluster_theme_1: str
    cluster_theme_2: Optional[str] = None
    cluster_theme_3: Optional[str] = None
    cluster_number: Optional[int] = None
    blog_schema_raw: str
    # The two phases fail independently, so the UI needs both: metadata can be
    # complete while content is still failed.
    metadata_status: str
    content_status: str
    error_message: Optional[str] = None
    # The scrape and its structured form are large. The UI only needs to know
    # they exist, so the text itself is not shipped in the list payload.
    has_scraped_website: bool = False
    has_website_content: bool = False
    blog_count: int = 0
    passed_count: int = 0
    created_at: datetime
    updated_at: datetime


class MetadataResult(BaseModel):
    """What the extract-metadata endpoint returns: the request row plus the blog
    briefs it created, with no content yet."""

    request: BlogGenerationRequestOut
    blogs: List[BlogOut]


class BlogGenerationResult(BaseModel):
    """What the generate endpoint returns immediately. Generation runs in the
    background, so this is the accepted-and-started state, not the finished one —
    poll GET /{id} and GET /{id}/blogs for progress."""

    request: BlogGenerationRequestOut
    blogs: List[BlogOut]
    started: bool = True
