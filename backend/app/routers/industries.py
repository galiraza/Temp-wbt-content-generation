from typing import List

from fastapi import APIRouter

from app.rag import INDUSTRIES

router = APIRouter(prefix="/api/industries", tags=["industries"])


@router.get("", response_model=List[str])
def list_industries():
    return INDUSTRIES
