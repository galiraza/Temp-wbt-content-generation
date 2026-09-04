from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AngleImageCreate(BaseModel):
    header_text: str
    additional_info: Optional[str] = None


class AngleImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    angle_id: int
    file_path: str
    header_text: str
    additional_info: Optional[str] = None
    reference_image_path: Optional[str] = None
    logo_path: Optional[str] = None
    company_image_paths: List[str] = []
    created_at: datetime


class AngleImageChatMessageOut(BaseModel):
    id: int
    angle_image_id: int
    role: str
    content: str
    candidate_image_path: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime
