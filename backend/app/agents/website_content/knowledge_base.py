"""The knowledge-base tools the page agents call.

n8n gave each page agent five `vectorStorePinecone` nodes in `retrieve-as-tool`
mode, so the AGENT decided which industry knowledge base to query and with what
text -- that routing is written into the system prompts ("Call ALL relevant
tools", with a full industry-to-tool mapping). Reproducing it means real tools
the model chooses between, not a fixed retrieval we run for it. A pre-baked
lookup would quietly discard the multi-category rule the prompts spend forty
lines on.

Each tool is a thin wrapper over one Pinecone namespace:

    query text -> text-embedding-3-small -> namespace, topK 3 -> joined chunks

topK, the namespaces and the index names are the n8n nodes' own settings. The
tool DESCRIPTIONS are lifted verbatim into prompts/knowledge_base_prompts.py,
because the description is the only thing telling the model when to call each
one -- rewording it is rewording the prompt.

Two indexes, matching the workflow: the five website namespaces live in
WEBSITE_CONTENT_PINECONE_INDEX, and the blogs agent reads its own single
namespace in BLOGS_PINECONE_INDEX.

Retrieval is best-effort, exactly as it is for ad angles: a Pinecone or embedding
failure returns a short "no examples" string to the model rather than raising.
A page written without style examples is worth far more than a failed run, and
the agent is told to write from the brief regardless.
"""

import logging
from typing import Any, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.website_content.prompts.knowledge_base_prompts import (
    BLOGS_KB_TOOL_DESCRIPTION,
    KB_TOOL_DESCRIPTIONS,
)
from app.config import (
    BLOGS_PINECONE_INDEX,
    BLOGS_PINECONE_NAMESPACE,
    WEBSITE_CONTENT_PINECONE_INDEX,
)
from app.rag.clients import embed_texts, get_index

logger = logging.getLogger("app")

#: The n8n nodes' topK. Raising it would change how much example prose lands in
#: the context window, which is part of what the prompts were tuned against.
TOP_K = 3

#: Anthropic tool names must match ^[a-zA-Z0-9_-]{1,64}$, so the human name the
#: system prompts use ("Energy and Heating Systems Knowledge Base") becomes the
#: underscored form -- the same substitution n8n makes on a node name.
_NAMESPACE_TOOL_NAMES = {
    "energy_heating_systems": "Energy_and_Heating_Systems_Knowledge_Base",
    "construction_property_services": "Construction_and_Property_Services_Knowledge_Base",
    "home_improvement_interiors": "Home_Improvement_and_Interiors_Knowledge_Base",
    "electrical_security_systems": "Electrical_and_Security_Systems_Knowledge_Base",
    "health_aesthetics": "Health_and_Aesthetics_Knowledge_Base",
}

_BLOGS_TOOL_NAME = "Blogs_Knowledge_Base"

#: What the model is told when retrieval could not run. Deliberately plain: the
#: agent should carry on from the brief, not report a tool failure in the page.
_NO_EXAMPLES = (
    "No examples were available from this knowledge base. "
    "Write from the brief, following the tone and structure rules in your instructions."
)


class _KnowledgeBaseQuery(BaseModel):
    """The single argument every knowledge-base tool takes.

    Described in the words the tool descriptions themselves use ("Query with the
    specific service type"), so the model reads one consistent instruction.
    """

    query: str = Field(
        description=(
            "The specific service type to look up, e.g. "
            '"homepage content for boiler services" or "solar panel website content".'
        )
    )


def _retrieve(index_name: str, namespace: str, query: str) -> str:
    """One namespace lookup, joined into the text the model reads back."""
    try:
        index = get_index(index_name)
        if index is None:
            logger.warning("website_kb_unconfigured namespace=%s", namespace)
            return _NO_EXAMPLES

        vector = embed_texts([query])[0]
        result = index.query(
            vector=vector,
            top_k=TOP_K,
            namespace=namespace,
            include_metadata=True,
        )
    except Exception:
        # Best-effort by design: see the module docstring. Logged with a
        # traceback so a misconfigured index is still diagnosable.
        logger.exception("website_kb_failed namespace=%s", namespace)
        return _NO_EXAMPLES

    chunks: List[str] = []
    for match in result.get("matches", []) or []:
        metadata: Dict[str, Any] = match.get("metadata") or {}
        # n8n's Pinecone node stores the chunk under `text`; older ingests in
        # this project used `pageContent`. Read either rather than returning
        # blank chunks that look like an empty knowledge base.
        content = metadata.get("text") or metadata.get("pageContent") or ""
        content = str(content).strip()
        if content:
            chunks.append(content)

    if not chunks:
        logger.info("website_kb_empty namespace=%s query=%.80s", namespace, query)
        return _NO_EXAMPLES

    return "\n\n---\n\n".join(chunks)


def _make_tool(name: str, description: str, index_name: str, namespace: str) -> StructuredTool:
    def run(query: str) -> str:
        logger.info("website_kb_query namespace=%s query=%.80s", namespace, query)
        return _retrieve(index_name, namespace, query)

    return StructuredTool.from_function(
        func=run,
        name=name,
        description=description,
        args_schema=_KnowledgeBaseQuery,
    )


def page_tools(page_key: str) -> List[StructuredTool]:
    """The five industry knowledge bases, as the given page agent saw them.

    `page_key` is one of home | about_us | service | service_area | other. Each
    page got its own five nodes in n8n, whose descriptions differ in their worked
    examples ("homepage content for boiler services" vs "about us page content
    for boiler services"), so the descriptions are looked up per page rather than
    shared.
    """
    descriptions = KB_TOOL_DESCRIPTIONS[page_key]
    return [
        _make_tool(
            _NAMESPACE_TOOL_NAMES[namespace],
            description,
            WEBSITE_CONTENT_PINECONE_INDEX,
            namespace,
        )
        for namespace, description in descriptions.items()
    ]


def blogs_tools() -> List[StructuredTool]:
    """The blogs agent's single knowledge base, on its own index."""
    return [
        _make_tool(
            _BLOGS_TOOL_NAME,
            BLOGS_KB_TOOL_DESCRIPTION,
            BLOGS_PINECONE_INDEX,
            BLOGS_PINECONE_NAMESPACE,
        )
    ]
