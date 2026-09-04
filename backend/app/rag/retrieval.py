"""Query-time retrieval: pulls relevant real client example ad angles from
Pinecone, filtered by industry and ranked by similarity to the requested
service content, to ground the LLM agent's prompts.
"""

from typing import List, Tuple

from app.rag.clients import embed_texts, get_pinecone_index


def retrieve_examples(
    industry: str, service_content: str, k: int = 3
) -> List[Tuple[str, str]]:
    """Returns up to k (headline, primary_text) example pairs for the given
    industry, ranked by similarity to service_content. Returns [] on any
    misconfiguration or if nothing matches — callers should treat retrieval as
    best-effort grounding, not a hard requirement.
    """
    try:
        index = get_pinecone_index()
        if index is None:
            return []
        query_embedding = embed_texts([f"{industry}\n{service_content}"])[0]
        result = index.query(
            vector=query_embedding,
            top_k=k,
            filter={"industry": {"$eq": industry}},
            include_metadata=True,
        )
        examples = []
        for match in result.get("matches", []):
            meta = match.get("metadata") or {}
            headline = meta.get("headline")
            primary_text = meta.get("primary_text")
            if headline and primary_text:
                examples.append((headline, primary_text))
        return examples
    except Exception:
        return []
