"""LangChain building blocks for the blog agents.

Everything here is a Runnable, so the agents read as LCEL chains:

    prompt | text_llm() | BlogOutputParser()

Same ChatAnthropic model as the post agents (Claude Sonnet 4.6), because the five
prompts came from n8n nodes that were tuned against Claude — rehosting them on
another model would change their output.

Deliberately simpler than app.agents.post_generation.client: no agent in this
workflow uses web search, and `pause_turn` only happens on a turn that called a
server-side tool. Without the search tool bound there is nothing to resume, so
that retry loop is not reproduced here.

Two pieces:
  text_llm()        messages -> str, joining the response's text blocks
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

#: One blog is ~1,500 words plus a GMB post, a GMB FAQ, meta fields and the
#: General Notes block. The structuring agent's output is longer still: it
#: reproduces a whole homepage as markdown.
_MAX_TOKENS = 16000
_TIMEOUT_SECONDS = 600

#: The service name every error carries, so a failure in this module is
#: attributable without reading a traceback.
_SERVICE = "Blog generation"

TModel = TypeVar("TModel", bound=BaseModel)


def chat_model() -> Runnable:
    """The model itself."""
    if not ANTHROPIC_API_KEY:
        raise ServiceNotConfiguredError(
            _SERVICE,
            internal="ANTHROPIC_API_KEY is unset",
        )
    return ChatAnthropic(
        model=ANTHROPIC_MODEL,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=_MAX_TOKENS,
        timeout=_TIMEOUT_SECONDS,
    )


def _text_of(message: AIMessage) -> str:
    """Joins the text blocks of a response.

    Joined with NO separator: a response can arrive split across several text
    blocks mid-sentence, and inserting newlines between them mangles the prose.
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


def text_llm(*, label: str = "blog-agent") -> Runnable:
    """A Runnable that takes a prompt value and returns the model's text.

    Sits where `| llm | StrOutputParser()` normally would. It exists so a
    refusal, an empty reply and a truncated reply are distinguishable: all three
    look like "no usable text" to a plain parser, but only truncation is worth
    logging as a probable cause of a short blog.
    """
    model = chat_model()

    def invoke(prompt_value) -> str:
        try:
            reply = model.invoke(prompt_value.to_messages())
        except Exception as exc:
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model didn't respond. Please try again in a moment.",
                internal=f"{label}: {type(exc).__name__}: {exc}",
            ) from exc

        stop_reason = (reply.response_metadata or {}).get("stop_reason")
        if stop_reason == "refusal":
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model declined this brief. Please review the wording and try again.",
                internal=f"{label}: refusal",
            )

        text = _text_of(reply)
        if not text:
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model returned nothing. Please try again.",
                internal=f"{label}: empty response, stop_reason={stop_reason}",
            )
        if stop_reason == "max_tokens":
            # Worth knowing about: a truncated blog loses its GMB Post and FAQ,
            # which the parser then reports as missing sections.
            logger.warning("anthropic_truncated label=%s", label)
        return text

    return RunnableLambda(invoke, name=f"anthropic:{label}")


def _is_connection_error(exc: BaseException) -> bool:
    """True when the call never reached the model, as opposed to coming back malformed.

    Walks the __cause__/__context__ chain: a DNS failure surfaces as
    anthropic.APIConnectionError wrapping httpx.ConnectError wrapping
    "[Errno 11002] getaddrinfo failed", and only the innermost link says why.
    """
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__
        if any(token in name for token in ("Connection", "Timeout", "Network", "DNS")):
            return True
        if "getaddrinfo" in str(current) or "Name or service not known" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def structured_llm(schema: Type[TModel], *, label: str = "blog-agent") -> Runnable:
    """A Runnable whose output is constrained to `schema`.

    Used by the QC audit and the metadata extractor, both of which returned JSON
    in a markdown fence that an n8n Code node stripped with a regex and then
    `JSON.parse`d. One malformed reply there aborted the whole workflow run.
    Validation happens inside LangChain instead, so the model is asked again on a
    mismatch rather than us parsing prose and guessing.
    """
    model = chat_model()

    def invoke(prompt_value) -> TModel:
        try:
            return model.with_structured_output(schema).invoke(prompt_value.to_messages())
        except Exception as exc:
            # A dropped connection and a schema mismatch are different problems
            # and need different wording. Reporting a DNS failure as "returned an
            # unreadable reply" sends the reader looking for a prompt bug — it
            # happened here when the machine's network changed mid-session.
            if _is_connection_error(exc):
                message = "Couldn't reach the writing model. Check your connection and try again."
            else:
                message = "The writing model returned an unreadable reply. Please try again."
            error = UpstreamServiceError(
                _SERVICE,
                message,
                internal=f"{label}: {type(exc).__name__}: {exc}",
            )
            # Marked retryable: a schema mismatch is a one-off bad reply, not a
            # standing condition. Asking again usually gets a valid one, and
            # without this flag the caller's retry helper treats every
            # UpstreamServiceError as permanent — which cost a fully written blog
            # in a live run when one audit came back with a junk `breakdown`.
            error.retryable = True
            raise error from exc

    return RunnableLambda(invoke, name=f"anthropic-structured:{label}")
