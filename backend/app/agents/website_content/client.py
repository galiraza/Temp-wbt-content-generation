"""LangChain building blocks for the website-content agents.

Everything here is a Runnable, so the agents read as LCEL chains:

    prompt | text_llm() | StrOutputParser-equivalent

The n8n workflow wired a separate model node to every single agent, each with its
own max-tokens ceiling. Those ceilings are the one thing worth carrying over
verbatim, because they are what the prompts were tuned against -- the Service
Page node was raised to 15,000 precisely because it writes one full page per
service and was being truncated at 8,000. `max_tokens` below reproduces them.

Same ChatAnthropic model as the blog and post agents (Claude Sonnet 4.6): every
n8n node in this workflow ran on it, and rehosting a tuned prompt on another
model changes its output.

Four pieces:
  chat_model()      the raw ChatAnthropic, optionally with tools bound
  text_llm()        messages -> str, joining the response's text blocks
  structured_llm()  messages -> a validated Pydantic model
  search_llm()      messages -> str, on OpenAI's web-search model

`search_llm` exists for exactly one node. "Generate Titles" was the sole node in
the workflow not on Claude: it ran on `gpt-4o-search-preview` because its prompt
opens with "Always use web search in UK to gather the latest information". Moving
it to Claude would silently drop the search.
"""

import logging
from typing import Any, List, Optional, Type, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    OPENAI_API_KEY,
    WEBSITE_CONTENT_TITLE_MODEL,
)
from app.errors import ServiceNotConfiguredError, UpstreamServiceError

logger = logging.getLogger("app")

#: The per-node max-tokens ceilings from the workflow, keyed by the agent that
#: uses them. n8n's default (when `maxTokensToSample` was left unset) is 4,096,
#: which is why the small classification nodes are not listed here.
MAX_TOKENS = {
    "analyst": 10000,        # "Anthropic Chat Model", temperature 0.5
    "json_correction": 12000,  # "Anthropic Chat Model4"
    "sitemap": 4096,         # "Anthropic Chat Model5", n8n default
    "home_page": 8000,       # "Anthropic Chat Model6"
    "about_us": 8000,        # "Anthropic Chat Model7"
    "service_page": 15000,   # "Anthropic Chat Model8"
    "service_area": 15000,   # "Anthropic Chat Model9"
    "other_page": 15000,     # "Anthropic Chat Model10"
    "blogs": 15000,          # "Anthropic Chat Model11"
    "critic": 15000,         # "Anthropic Chat Model12" and its five clones
    "refiner": 15000,        # "Anthropic Chat Model32" and its five clones
    "evaluator": 15000,      # "Anthropic Chat Model33" and its five clones
    "classify": 4096,        # Get Industry / Get Service / Select Industry
}

#: The analyst node is the only one in the workflow with a temperature set.
#: Everything else runs on the provider default, so it is left unset rather than
#: pinned -- pinning it would be a change to behaviour the prompts were tuned on.
TEMPERATURE = {"analyst": 0.5, "critic": 0.3}

#: A page agent writes several full pages in one call and may make three or four
#: knowledge-base round trips first. n8n had no timeout at all on these.
_TIMEOUT_SECONDS = 900

_SERVICE = "Website content generation"

TModel = TypeVar("TModel", bound=BaseModel)


def chat_model(label: str, *, tools: Optional[List[Any]] = None) -> Runnable:
    """The model itself, at the ceiling the matching n8n node used."""
    if not ANTHROPIC_API_KEY:
        raise ServiceNotConfiguredError(_SERVICE, internal="ANTHROPIC_API_KEY is unset")

    kwargs = {
        "model": ANTHROPIC_MODEL,
        "api_key": ANTHROPIC_API_KEY,
        "max_tokens": MAX_TOKENS.get(label, 8000),
        "timeout": _TIMEOUT_SECONDS,
    }
    if label in TEMPERATURE:
        kwargs["temperature"] = TEMPERATURE[label]

    llm = ChatAnthropic(**kwargs)
    return llm.bind_tools(tools) if tools else llm


#: Appended to EVERY agent's messages, on both providers, by `guarded()` below.
#:
#: Stated separately from the page prompts because it is not a style preference,
#: it is a hard house rule that applies to every agent in the module, including
#: the ones that never write client-facing prose. The analyst's JSON is injected
#: verbatim into five page prompts, so an em dash there propagates into pages
#: that were themselves told not to use one.
#:
#: This exists because the rule was already stated in three separate prompts and
#: was still broken. A clean draft with zero em dashes went through the Critic,
#: Refiner and Evaluator and came out with four, and the Evaluator passed it. The
#: Refiner's own system prompt contained 24 em dashes at the time, which is very
#: likely why: it was shown the character two dozen times while being told never
#: to produce one. Those are now commas, and this is the belt to that braces.
DASH_GUARDRAIL = """HARD OUTPUT RULE, APPLIES TO EVERYTHING YOU WRITE, NO EXCEPTIONS.

Never use a dash as sentence punctuation. All three of these are banned in your
output, including inside JSON string values, headings, lists and quoted text:
  the em dash  —
  the en dash  –
  the double hyphen  --

Use a comma, a full stop, or rewrite the sentence. If you are tempted to reach
for "--" because you were told not to use an em dash, that is the same mistake.

A single hyphen inside a compound word or a numeric range is fine and always was:
purpose-built, Mon-Fri, 9-5.

This rule outranks any example above that uses one of these characters."""


def guarded(messages: List[Any]) -> List[Any]:
    """Inserts DASH_GUARDRAIL as a system message, for every agent.

    Its own SystemMessage rather than text merged into each prompt: it then
    applies to Anthropic and OpenAI alike, and reaches agents added later without
    anyone remembering to wire it up.

    Placed at the END of the leading run of system messages, which is the one
    position that both satisfies Anthropic and puts the rule last in the system
    block, where it outranks the older wording above it. It must NOT go at the
    end of the whole list: Anthropic takes `system` as a top-level parameter, so
    LangChain rejects a system message that appears after a human message with
    "Received multiple non-consecutive system messages" and the run fails with
    every section reporting that the model did not respond. Agents whose template
    has no system message at all (sitemap, analyst, the blog lead-ins) get it at
    index 0.
    """
    out = list(messages)
    end_of_system_block = 0
    while end_of_system_block < len(out) and isinstance(out[end_of_system_block], SystemMessage):
        end_of_system_block += 1
    out.insert(end_of_system_block, SystemMessage(content=DASH_GUARDRAIL))
    return out


def text_of(message: AIMessage) -> str:
    """Joins the text blocks of a response, ignoring tool-use blocks.

    Joined with NO separator: a reply can arrive split across several text blocks
    mid-sentence, and inserting newlines between them mangles the prose. Same
    reasoning as app.agents.blog_generation.client._text_of.
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


def _raise_upstream(label: str, exc: Exception) -> None:
    raise UpstreamServiceError(
        _SERVICE,
        "The writing model didn't respond. Please try again in a moment.",
        internal=f"{label}: {type(exc).__name__}: {exc}",
    ) from exc


def text_llm(*, label: str) -> Runnable:
    """A Runnable that takes a prompt value and returns the model's text.

    Sits where `| llm | StrOutputParser()` normally would. It exists so a
    refusal, an empty reply and a truncated reply are distinguishable: all three
    look like "no usable text" to a plain parser, but only truncation is worth
    logging as the probable cause of a short page.
    """
    model = chat_model(label)

    def invoke(prompt_value) -> str:
        try:
            reply = model.invoke(guarded(prompt_value.to_messages()))
        except Exception as exc:
            _raise_upstream(label, exc)

        stop_reason = (reply.response_metadata or {}).get("stop_reason")
        if stop_reason == "refusal":
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model declined this brief. Please review the wording and try again.",
                internal=f"{label}: refusal",
            )

        text = text_of(reply)
        if not text:
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model returned nothing. Please try again.",
                internal=f"{label}: empty response, stop_reason={stop_reason}",
            )
        if stop_reason == "max_tokens":
            # Worth knowing about: a truncated Service Area reply loses whole
            # area pages off the end, which reads as "the model skipped areas".
            logger.warning("website_content_truncated label=%s", label)
        return text

    return RunnableLambda(invoke, name=f"anthropic:{label}")


def is_connection_error(exc: BaseException) -> bool:
    """True when the call never reached the model, as opposed to coming back
    malformed.

    Walks the __cause__/__context__ chain: a DNS failure surfaces as
    anthropic.APIConnectionError wrapping httpx.ConnectError wrapping
    "[Errno 11002] getaddrinfo failed", and only the innermost link says why.
    """
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__
        if any(token in name for token in ("Connection", "Timeout", "Network", "DNS")):
            return True
        if "getaddrinfo" in str(current) or "Name or service not known" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def structured_llm(schema: Type[TModel], *, label: str) -> Runnable:
    """A Runnable whose output is constrained to `schema`.

    Used by the evaluator, which in n8n was a chainLlm with a Structured Output
    Parser attached. That parser regex-stripped a ```json fence and JSON.parse'd
    it; one malformed reply threw and killed the whole branch. Validation happens
    inside LangChain instead, so the model is asked again on a mismatch.
    """
    model = chat_model(label)

    def invoke(prompt_value) -> TModel:
        try:
            return model.with_structured_output(schema).invoke(guarded(prompt_value.to_messages()))
        except Exception as exc:
            # A dropped connection and a schema mismatch are different problems
            # and need different wording. Reporting a DNS failure as "returned an
            # unreadable reply" sends the reader looking for a prompt bug.
            if is_connection_error(exc):
                message = "Couldn't reach the writing model. Check your connection and try again."
            else:
                message = "The writing model returned an unreadable reply. Please try again."
            error = UpstreamServiceError(
                _SERVICE, message, internal=f"{label}: {type(exc).__name__}: {exc}"
            )
            # Marked retryable: a schema mismatch is one bad reply, not a standing
            # condition, and asking again usually gets a valid one. Without the
            # flag the caller's retry helper treats every UpstreamServiceError as
            # permanent -- which would throw away a page that is already written.
            error.retryable = True
            raise error from exc

    return RunnableLambda(invoke, name=f"anthropic-structured:{label}")


def search_llm(*, label: str = "generate-titles") -> Runnable:
    """The one OpenAI chain: blog titles, on a web-search model.

    `gpt-4o-search-preview` runs the search server-side and takes no temperature
    parameter, which is why nothing is passed here beyond the model name -- the
    same as the n8n node, which left its options empty.
    """
    if not OPENAI_API_KEY:
        raise ServiceNotConfiguredError(_SERVICE, internal="OPENAI_API_KEY is unset")

    model = ChatOpenAI(
        model=WEBSITE_CONTENT_TITLE_MODEL,
        api_key=OPENAI_API_KEY,
        timeout=_TIMEOUT_SECONDS,
    )

    def invoke(prompt_value) -> str:
        try:
            reply = model.invoke(guarded(prompt_value.to_messages()))
        except Exception as exc:
            # A retired model and a dropped connection both used to surface as
            # "the model didn't respond", which is actively misleading: it sends
            # whoever reads it to check the network when the real answer is that
            # OpenAI has deleted the model. That is not hypothetical -- it is
            # exactly how gpt-4o-search-preview's retirement first presented, as
            # an APIConnectionError with a healthy connection behind it.
            detail = str(exc)
            if "deprecated" in detail.lower() or "model_not_found" in detail:
                raise UpstreamServiceError(
                    _SERVICE,
                    f"The blog-title model ({WEBSITE_CONTENT_TITLE_MODEL}) is no longer "
                    "available from OpenAI. Set WEBSITE_CONTENT_TITLE_MODEL to a current "
                    "search-capable model.",
                    internal=f"{label}: {type(exc).__name__}: {detail}",
                ) from exc
            _raise_upstream(label, exc)

        text = text_of(reply)
        if not text:
            raise UpstreamServiceError(
                _SERVICE,
                "The title model returned nothing. Please try again.",
                internal=f"{label}: empty response",
            )
        return text

    return RunnableLambda(invoke, name=f"openai:{label}")
