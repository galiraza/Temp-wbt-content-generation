"""LangChain building blocks for the post/review agents.

Everything here is a Runnable, so the agents read as LCEL chains:

    prompt | text_llm() | PostListParser()

Uses ChatAnthropic, the same way the ad-angle and logo agents use ChatOpenAI —
one LLM abstraction across the codebase. The model is Claude Sonnet 5 (the n8n
workflows these prompts came from ran on Claude Sonnet 4.6); they were tuned
against Claude, so rehosting them on another provider would change their output.

Three pieces:
  chat_model()      the raw ChatAnthropic, optionally with web search bound
  text_llm()        messages -> str, with the retry-on-pause and text-block
                    joining that a bare `| llm | StrOutputParser()` cannot do
  structured_llm()  messages -> a validated Pydantic model
"""

import logging
from typing import Type, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

_MAX_TOKENS = 16000
# The content agent writes eight full posts in one call, which is a long output.
_TIMEOUT_SECONDS = 600
# One web search per agent is what the prompts ask for. The cap stops a
# misbehaving turn running up a search bill.
_MAX_WEB_SEARCHES = 4
# A turn using a server-side tool can come back as pause_turn, meaning "not
# finished, send this back to me". This bounds how many times we will.
_MAX_RESUMES = 4

# Anthropic's hosted search tool. Declared as a raw dict because it runs on
# Anthropic's servers: there is no function to implement and no tool loop to run,
# results arrive as content blocks in the same response.
_WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": _MAX_WEB_SEARCHES,
}

TModel = TypeVar("TModel", bound=BaseModel)


def chat_model(*, web_search: bool = False) -> Runnable:
    """The model itself. Bind the search tool when the prompt asks for research."""
    if not ANTHROPIC_API_KEY:
        raise ServiceNotConfiguredError(
            "Post generation",
            internal="ANTHROPIC_API_KEY is unset",
        )
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=_MAX_TOKENS,
        timeout=_TIMEOUT_SECONDS,
    )
    return llm.bind_tools([_WEB_SEARCH_TOOL]) if web_search else llm


def _text_of(message: AIMessage) -> str:
    """Joins the text blocks of a response, ignoring tool-use and search-result
    blocks.

    A web-search turn interleaves those with the prose, so reading content[0]
    would return an empty string about half the time. The blocks are joined with
    NO separator: search citations split a single sentence across several text
    blocks, and inserting newlines between them mangles the prose.

    This is why the chains use text_llm() rather than a plain StrOutputParser.
    """
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts).strip()


def text_llm(*, web_search: bool = False, label: str = "post-agent") -> Runnable:
    """A Runnable that takes a prompt value and returns the model's text.

    Sits where `| llm | StrOutputParser()` normally would, and adds the two things
    that pairing cannot do: resuming a `pause_turn` (which a server-side search
    can return mid-thought) and joining citation-split text blocks correctly.
    """
    model = chat_model(web_search=web_search)

    def invoke(prompt_value) -> str:
        messages = prompt_value.to_messages()
        stop_reason = None
        try:
            for attempt in range(_MAX_RESUMES + 1):
                reply = model.invoke(messages)
                stop_reason = (reply.response_metadata or {}).get("stop_reason")
                if stop_reason != "pause_turn":
                    break
                # Hand the paused turn straight back so the model can carry on.
                messages = messages + [reply]
                logger.info("anthropic_pause_turn label=%s attempt=%s", label, attempt + 1)
            else:
                logger.warning("anthropic_pause_turn_exhausted label=%s", label)
        except Exception as exc:
            raise UpstreamServiceError(
                "Post generation",
                "The writing model didn't respond. Please try again in a moment.",
                internal=f"{label}: {type(exc).__name__}: {exc}",
            ) from exc

        if stop_reason == "refusal":
            raise UpstreamServiceError(
                "Post generation",
                "The writing model declined this brief. Please review the wording and try again.",
                internal=f"{label}: refusal",
            )

        text = _text_of(reply)
        if not text:
            raise UpstreamServiceError(
                "Post generation",
                "The writing model returned nothing. Please try again.",
                internal=f"{label}: empty response, stop_reason={stop_reason}",
            )
        if stop_reason == "max_tokens":
            # Worth knowing about: a truncated batch parses into fewer than 8
            # items and the manager will pad it.
            logger.warning("anthropic_truncated label=%s", label)
        return text

    return RunnableLambda(invoke, name=f"anthropic:{label}")


def structured_llm(schema: Type[TModel], *, label: str = "post-agent") -> Runnable:
    """A Runnable whose output is constrained to `schema`.

    Used by the copy chat, where "which fields am I changing" has to be
    unambiguous. Validation happens inside LangChain, so the model is asked again
    on a mismatch rather than us parsing prose and guessing.
    """
    model = chat_model()

    def invoke(prompt_value) -> TModel:
        try:
            return model.with_structured_output(schema).invoke(prompt_value.to_messages())
        except Exception as exc:
            raise UpstreamServiceError(
                "Post generation",
                "The writing model returned an unreadable reply. Please try again.",
                internal=f"{label}: {type(exc).__name__}: {exc}",
            ) from exc

    return RunnableLambda(invoke, name=f"anthropic-structured:{label}")
