from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.rag.industries import INDUSTRIES

_VALID_INDUSTRIES = set(INDUSTRIES)


def _validate_industries(value: List[str]) -> List[str]:
    if len(value) != 1:
        raise ValueError("Exactly one industry must be selected")
    invalid = [v for v in value if v not in _VALID_INDUSTRIES]
    if invalid:
        raise ValueError(f"Invalid industries: {', '.join(invalid)}")
    return value


class AdAngleRequestCreate(BaseModel):
    company_name: str
    offers: List[str] = []
    service_name: str
    service_content: str
    industry: List[str]

    @field_validator("industry")
    @classmethod
    def check_industries(cls, value: List[str]) -> List[str]:
        return _validate_industries(value)


class AdAngleRequestUpdate(BaseModel):
    company_name: Optional[str] = None
    offers: Optional[List[str]] = None
    service_name: Optional[str] = None
    service_content: Optional[str] = None
    industry: Optional[List[str]] = None

    @field_validator("industry")
    @classmethod
    def check_industries(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        return _validate_industries(value)


class AdAngleRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    offers: List[str]
    service_name: str
    service_content: str
    industry: List[str]
    created_at: datetime
    updated_at: datetime


class AngleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    headline: str
    primary_text: str
    status: str
    order: int
    created_at: datetime
    updated_at: datetime


class AngleUpdate(BaseModel):
    headline: str
    primary_text: str


class ChatMessageOut(BaseModel):
    id: int
    angle_id: int
    role: str
    content: str
    headline: Optional[str] = None
    primary_text: Optional[str] = None
    created_at: datetime


class ChatMessageCreate(BaseModel):
    content: str


class FeedbackResponse(BaseModel):
    angle: AngleOut
    message: ChatMessageOut
