"""Shared Pinecone/OpenAI client accessors + embedding helper, used by both
retrieval (query-time) and ingestion (one-off indexing).
"""

from typing import List, Optional

from openai import OpenAI
from pinecone import Pinecone

from app.config import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

_pinecone_client: Optional[Pinecone] = None
_openai_client: Optional[OpenAI] = None


def get_index(index_name: Optional[str]):
    """Any Pinecone index by name, or None if Pinecone isn't configured.

    There is more than one index in play: the ad-angle examples live in
    PINECONE_INDEX_NAME, while website-content generation reads two of its own
    (see app.agents.website_content.knowledge_base). The client is shared -- it
    is per-API-key, not per-index.
    """
    global _pinecone_client
    if not PINECONE_API_KEY or not index_name:
        return None
    if _pinecone_client is None:
        _pinecone_client = Pinecone(api_key=PINECONE_API_KEY)
    return _pinecone_client.Index(index_name)


def get_pinecone_index():
    """The ad-angle example index."""
    return get_index(PINECONE_INDEX_NAME)


def get_openai_client() -> Optional[OpenAI]:
    global _openai_client
    if not OPENAI_API_KEY:
        return None
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def embed_texts(texts: List[str]) -> List[List[float]]:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot create embeddings.")
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]
