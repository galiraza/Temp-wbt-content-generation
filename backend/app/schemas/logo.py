from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LogoFromScratchCreate(BaseModel):
    company_name: str
    industry: str
    usps: Optional[str] = None
    fathom_url: Optional[str] = None
    suggestion: Optional[str] = None
    use_ai_suggestion: bool = False


class LogoFromScratchUpdate(BaseModel):
    """Optional brief edits sent with a "Run again". Every field is optional so
    the caller can change only what it wants; unset fields keep their value."""

    company_name: Optional[str] = None
    industry: Optional[str] = None
    usps: Optional[str] = None
    fathom_url: Optional[str] = None
    suggestion: Optional[str] = None


class LogoFromScratchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    industry: str
    usps: Optional[str] = None
    fathom_url: Optional[str] = None
    fathom_transcript: Optional[str] = None
    suggestion: Optional[str] = None
    use_ai_suggestion: bool
    created_at: datetime
    updated_at: datetime


class LogoFromPreviousOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: Optional[str] = None
    logo_path: str
    suggestion: Optional[str] = None
    use_ai_suggestion: bool
    fathom_url: Optional[str] = None
    fathom_transcript: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LogoImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scratch_request_id: Optional[int] = None
    previous_request_id: Optional[int] = None
    slot: int
    file_path: str
    created_at: datetime


class LogoImageChatMessageOut(BaseModel):
    id: int
    logo_image_id: int
    role: str
    content: str
    candidate_image_path: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime
