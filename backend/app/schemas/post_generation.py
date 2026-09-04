from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.agents.post_generation.parsers import normalise_hashtags


class _HashtagNormalising(BaseModel):
    """Forces hashtags to "#OneWord" on the way in.

    A manual edit arrives as whatever the caller typed, so "two" and "#two" and
    "two words" all have to land the same way the generated ones did. The
    frontend also tidies as you type, but the API cannot rely on its own client
    to do that.
    """

    @field_validator("hashtags", check_fields=False)
    @classmethod
    def _clean_hashtags(cls, value):
        return normalise_hashtags(value or [])


class PostGenerationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None
    company_reviews_page_url: Optional[str] = None
    month: Optional[str] = None
    industry: Optional[str] = None
    fixed_rules: Optional[str] = None
    main_topic: Optional[str] = None
    promotion: Optional[str] = None
    additional_resources: Optional[str] = None
    additional_notes: Optional[str] = None
    areas_covered: Optional[str] = None
    unique_selling_points: Optional[str] = None
    post_image_paths: List[str]
    logo_path: Optional[str] = None
    review_template_path: Optional[str] = None
    # The two managers run in parallel and fail independently, so the UI needs
    # both: posts can be complete while reviews are still failed.
    posts_status: str
    reviews_status: str
    # Hero-image generation is a separate step, triggered by its own endpoint
    # after content generation - see HeroImageOut.
    images_status: str = "pending"
    error_message: Optional[str] = None
    # Grouped by tier for display. The agents' raw text is what gets sent back to
    # the model on a regeneration; this is only for showing the user what was
    # researched.
    post_hashtag_pool: Dict[str, List[str]] = {}
    review_hashtag_pool: Dict[str, List[str]] = {}
    has_scraped_reviews: bool = False
    created_at: datetime
    updated_at: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    post_number: int
    theme: str
    title: str
    caption: str
    hashtags: List[str]
    status: str
    image_path: Optional[str] = None  # newest generated image, if any
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class PostUpdate(_HashtagNormalising):
    """Direct manual edit, no LLM involved."""

    title: str
    caption: str
    hashtags: List[str]


class ReelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    # 2, 5, 8 or 11: the slot in the 12-item month, not a 1-4 sequence.
    reel_number: int
    theme: str
    # The on-screen script. Multi-line: one line per text card.
    reel_text: str
    caption: str
    hashtags: List[str]
    status: str
    image_path: Optional[str] = None
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class ReelUpdate(_HashtagNormalising):
    """Direct manual edit, no LLM involved. A reel has no title."""

    reel_text: str
    caption: str
    hashtags: List[str]


class ReelChatMessageOut(BaseModel):
    id: int
    reel_id: int
    role: str
    content: str
    is_revision: bool = False
    # Only the fields this turn changes are present; absent means "unchanged".
    reel_text: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    created_at: datetime


class ReelFeedbackResponse(BaseModel):
    reel: ReelOut
    message: ReelChatMessageOut


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    review_number: int
    title: str
    name: str
    review: str
    caption: str
    hashtags: List[str]
    platform: Optional[str] = None
    status: str
    image_path: Optional[str] = None
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class ReviewUpdate(_HashtagNormalising):
    """Direct manual edit. `review` is included because a user may need to fix a
    transcription error, but the chat agent will not rewrite it."""

    title: str
    name: str
    review: str
    caption: str
    hashtags: List[str]


class ContentChatMessageOut(BaseModel):
    id: int
    post_id: Optional[int] = None
    review_id: Optional[int] = None
    role: str
    content: str
    # Present only on an assistant turn carrying an approvable revision, and only
    # for the fields that turn actually changes. An absent field means "unchanged".
    is_revision: bool = False
    title: Optional[str] = None
    name: Optional[str] = None
    review: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    created_at: datetime


class ChatMessageCreate(BaseModel):
    content: str


class PostFeedbackResponse(BaseModel):
    post: PostOut
    message: ContentChatMessageOut


class ReviewFeedbackResponse(BaseModel):
    review: ReviewOut
    message: ContentChatMessageOut


class GenerationResult(BaseModel):
    """What the generate endpoint returns: all three sets plus the request row,
    which carries how each manager did."""

    request: PostGenerationRequestOut
    posts: List[PostOut]
    reels: List[ReelOut]
    reviews: List[ReviewOut]


class HeroImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    slot: int
    file_path: str
    summary: str
    usage: int
    created_at: datetime


class ImageGenerationResult(BaseModel):
    """What the generate-images endpoint returns: the hero image pool (an
    internal detail, never shown in the frontend) plus the posts/reels,
    which pick up their match invisibly via PostImage/ReelImage.background_path
    the next time a final image is generated for them."""

    request: PostGenerationRequestOut
    hero_images: List[HeroImageOut]
    posts: List[PostOut]
    reels: List[ReelOut]


class PostImageOut(BaseModel):
    """One finished branded graphic for a post - the headline/logo/CTA/hero
    photo composited together. `background_path` names which hero photo it
    was built from, kept only as an internal record - the hero photo itself
    is never surfaced anywhere in the frontend on its own."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    file_path: str
    background_path: Optional[str] = None  # the hero photo this was composed from
    layout_variant: Optional[str] = None  # the VariantLibrary letter used
    created_at: datetime


class ReelImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reel_id: int
    file_path: str
    background_path: Optional[str] = None
    layout_variant: Optional[str] = None
    created_at: datetime


class PostImageChatMessageOut(BaseModel):
    id: int
    post_image_id: int
    role: str
    content: str
    candidate_image_path: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime


class ReelImageChatMessageOut(BaseModel):
    id: int
    reel_image_id: int
    role: str
    content: str
    candidate_image_path: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime
