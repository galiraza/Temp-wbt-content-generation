from typing import List

from fastapi import APIRouter

from app.schemas.client_export import ClientPrefill
from app.services.client_export_service import get_client_prefill, list_clients

router = APIRouter(prefix="/api/client-export", tags=["client-export"])


@router.get("/list")
def get_client_list() -> List[dict]:
    return list_clients()


@router.get("/{client_id}/prefill", response_model=ClientPrefill)
def get_prefill(client_id: str) -> ClientPrefill:
    return get_client_prefill(client_id)
