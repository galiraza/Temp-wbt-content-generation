"""The five page agents, and the tool loop they run in.

n8n's `@n8n/n8n-nodes-langchain.agent` node is a tool-calling agent: it hands the
model the system message, the user brief and the bound tools, then loops --
model replies with tool calls, tools run, results go back as tool messages, model
replies again -- until the model answers with text instead of a tool call. That
loop is `run_tool_agent` below. There is no LangGraph or AgentExecutor here for
the same reason app.agents.meta_ads has none: one small explicit loop is easier
to reason about than a framework's, and this one has to be readable next to the
n8n node it replaces.

Each page is one agent call:

  Home Page       one page,  8k ceiling
  About Us Page   one page,  8k ceiling
  Service Page    one page PER SERVICE on the sitemap,   15k ceiling
  Service Area    one page PER AREA on the sitemap,      15k ceiling
  Other Page      one page PER "other page" on the sitemap, 15k ceiling

The last three write several pages in a single reply, separated by "---", which
is what their prompts ask for. `write_page` keeps that behaviour: the section is
stored whole, exactly as n8n stored it, and the frontend renders it as one
markdown block.

`write_single_page` is the other way in, for the three bundled agents. It
narrows one of them to a single page so the content hub can run each page as its
own concurrent task, and hands it the siblings' opening lines to replace the
uniqueness signal the bundled reply got for free from seeing them all at once.
It appends a directive rather than editing the prompts, so the bundled path
above stays byte identical. See prompts/single_page.py for why that matters.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool

from app.agents.website_content.client import chat_model, guarded, text_of
from app.agents.website_content.knowledge_base import page_tools
from app.agents.website_content.prompts.direct_response import DIRECT_RESPONSE_DOCTRINE
from app.agents.website_content.prompts.single_page import (
    DIRECTIVE_BY_PAGE,
    LIST_VARIABLE_BY_PAGE,
    format_siblings,
)
from app.agents.website_content.prompts.about_us_prompt import (
    ABOUT_US_SYSTEM_PROMPT,
    ABOUT_US_USER_PROMPT,
)
from app.agents.website_content.prompts.home_page_prompt import (
    HOME_PAGE_SYSTEM_PROMPT,
    HOME_PAGE_USER_PROMPT,
)
from app.agents.website_content.prompts.other_page_prompt import (
    OTHER_PAGE_SYSTEM_PROMPT,
    OTHER_PAGE_USER_PROMPT,
)
from app.agents.website_content.prompts.service_area_prompt import (
    SERVICE_AREA_SYSTEM_PROMPT,
    SERVICE_AREA_USER_PROMPT,
)
from app.agents.website_content.prompts.service_page_prompt import (
    SERVICE_PAGE_SYSTEM_PROMPT,
    SERVICE_PAGE_USER_PROMPT,
)
from app.errors import UpstreamServiceError

logger = logging.getLogger("app")

_SERVICE = "Website content generation"

#: How many times the agent may call tools before it must answer.
#:
#: The prompts ask for at most one call per industry category, and there are five
#: categories, so five rounds covers the worst honest case with room to spare.
#: n8n's own default is 10 iterations; the lower number here is a backstop
#: against a model that keeps re-querying instead of writing, which costs a
#: 15k-token page call every round.
MAX_TOOL_ROUNDS = 6

#: Whether the page agents may query the industry knowledge bases.
#:
#: OFF, deliberately. The knowledge bases hold our own existing client website
#: copy, and the tool descriptions tell the model to "extract the tone,
#: structure, headings, and content style from the returned examples". That
#: corpus is the text-heavy, company-first writing the 28 Aug 2026 review
#: rejected, so retrieval actively pulls each page back toward the style we are
#: trying to leave. The direct-response instructions in the prompts and the
#: retrieved examples were giving the model two contradictory briefs, and the
#: examples were winning because they are concrete.
#:
#: Turning this back on is a one-line change, and worth doing once the indexes
#: are re-ingested from pages actually written in the new style. Until then the
#: prompts are the only style authority.
USE_KNOWLEDGE_BASE = False


@dataclass(frozen=True)
class PageSpec:
    """One of the five page agents: which prompts, tools and ceiling it uses.

    `key` is both the client.MAX_TOKENS key and the knowledge_base.page_tools
    key, which is why the two dicts share their spellings.
    """

    key: str
    section_title: str
    system_prompt: str
    user_prompt: str


#: `section_title` is the exact string the n8n Set node wrote, because it is what
#: Command HQ's callback contract documents and what the frontend keys its
#: display order off. Note "Services Page" and "Other Pages" are plural while
#: the rest are not -- that is the workflow's own inconsistency, kept.
PAGE_SPECS: Dict[str, PageSpec] = {
    "home": PageSpec("home_page", "Home Page", HOME_PAGE_SYSTEM_PROMPT, HOME_PAGE_USER_PROMPT),
    "about_us": PageSpec(
        "about_us", "About Us Page", ABOUT_US_SYSTEM_PROMPT, ABOUT_US_USER_PROMPT
    ),
    "service": PageSpec(
        "service_page", "Services Page", SERVICE_PAGE_SYSTEM_PROMPT, SERVICE_PAGE_USER_PROMPT
    ),
    "service_area": PageSpec(
        "service_area", "Service Area Page", SERVICE_AREA_SYSTEM_PROMPT, SERVICE_AREA_USER_PROMPT
    ),
    "other": PageSpec(
        "other_page", "Other Pages", OTHER_PAGE_SYSTEM_PROMPT, OTHER_PAGE_USER_PROMPT
    ),
}

#: The order the six sections are produced and displayed in, matching the
#: `sections[]` array the Zapier node built.
PAGE_ORDER = ["home", "about_us", "service", "service_area", "other"]


def run_tool_agent(
    messages: List[BaseMessage],
    tools: List[StructuredTool],
    *,
    label: str,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> str:
    """The agent loop: call tools until the model answers with text.

    Returns the model's final text. Tool failures come back to the model as tool
    messages rather than exceptions, because knowledge-base retrieval is
    best-effort and the agent is told to write from the brief regardless -- a
    dead Pinecone index must not cost a page.
    """
    by_name = {tool.name: tool for tool in tools}
    model = chat_model(label, tools=tools)
    # The page agents build their own message list rather than going through
    # client.text_llm, so the shared guardrail has to be applied here too.
    history: List[BaseMessage] = guarded(messages)

    for round_number in range(max_rounds + 1):
        try:
            reply: AIMessage = model.invoke(history)
        except Exception as exc:
            raise UpstreamServiceError(
                _SERVICE,
                "The writing model didn't respond. Please try again in a moment.",
                internal=f"{label}: {type(exc).__name__}: {exc}",
            ) from exc

        calls = getattr(reply, "tool_calls", None) or []
        if not calls:
            text = text_of(reply)
            stop_reason = (reply.response_metadata or {}).get("stop_reason")
            if stop_reason == "refusal":
                raise UpstreamServiceError(
                    _SERVICE,
                    "The writing model declined this brief. Please review the wording and try again.",
                    internal=f"{label}: refusal",
                )
            if not text:
                raise UpstreamServiceError(
                    _SERVICE,
                    "The writing model returned nothing. Please try again.",
                    internal=f"{label}: empty response, stop_reason={stop_reason}",
                )
            if stop_reason == "max_tokens":
                logger.warning("website_content_truncated label=%s", label)
            return text

        if round_number >= max_rounds:
            # Out of rounds with the model still asking for tools. Drop the
            # tools and ask once more for the page, rather than returning
            # nothing: the brief alone is enough to write from.
            logger.warning(
                "website_tool_rounds_exhausted label=%s rounds=%s", label, round_number
            )
            history.append(reply)
            for call in calls:
                history.append(
                    ToolMessage(
                        tool_call_id=call["id"],
                        content=(
                            "No further knowledge-base lookups are available. "
                            "Write the page now, from the brief."
                        ),
                    )
                )
            final = chat_model(label).invoke(history)
            text = text_of(final)
            if not text:
                raise UpstreamServiceError(
                    _SERVICE,
                    "The writing model returned nothing. Please try again.",
                    internal=f"{label}: empty response after tool rounds exhausted",
                )
            return text

        history.append(reply)
        for call in calls:
            tool = by_name.get(call["name"])
            if tool is None:
                # The model invented a tool name. Say so plainly and let it
                # correct itself, the same as any tool-calling runtime would.
                content = f"No tool named {call['name']} is available."
                logger.warning("website_tool_unknown label=%s name=%s", label, call["name"])
            else:
                try:
                    content = tool.invoke(call["args"])
                except Exception:
                    logger.exception("website_tool_failed label=%s name=%s", label, call["name"])
                    content = (
                        "That knowledge base could not be reached. "
                        "Write from the brief instead."
                    )
            history.append(ToolMessage(tool_call_id=call["id"], content=str(content)))

    # Unreachable: the loop returns from inside. Here so a future edit to the
    # range cannot fall through and return None.
    raise UpstreamServiceError(
        _SERVICE,
        "The writing model didn't finish. Please try again.",
        internal=f"{label}: tool loop ended without a reply",
    )


#: The system-prompt section that routes the model to the knowledge-base tools.
#: Runs from its own heading to the next top-level one.
_KB_SECTION = re.compile(r"\n## KNOWLEDGE BASE TOOL SELECTION.*?(?=\n## )", re.S)

#: Numbered steps in a user prompt's INSTRUCTIONS list that tell the model to
#: query the knowledge bases. Removed with the tools, then the list is renumbered.
_KB_STEP = re.compile(r"^\d+\.\s.*knowledge base.*$", re.I)


def _without_knowledge_base(system_prompt: str, user_prompt: str) -> tuple:
    """Strips every instruction to call the knowledge-base tools.

    Done here rather than by editing the prompt files so that USE_KNOWLEDGE_BASE
    stays a genuine one-line switch. Leaving the instructions in place while the
    tools are unbound is the worst of both: the model is told at length to call
    five tools it cannot see, and spends the first part of its reply saying so.
    """
    system_prompt = _KB_SECTION.sub("", system_prompt)
    # Other Page's YOUR ROLE tells the model to follow "the exact style and tone
    # demonstrated in the knowledge base", which sits outside the section above.
    # Any stray line pointing at the retrieved examples has to go with it.
    system_prompt = "\n".join(
        line for line in system_prompt.split("\n") if "knowledge base" not in line.lower()
    )

    kept = [line for line in user_prompt.split("\n") if not _KB_STEP.match(line)]
    step = 0
    renumbered = []
    for line in kept:
        match = re.match(r"^\d+\.\s(.*)$", line)
        if match:
            step += 1
            renumbered.append("%d. %s" % (step, match.group(1)))
        else:
            renumbered.append(line)
    return system_prompt, "\n".join(renumbered)


def write_page(page: str, brief: Dict[str, Any]) -> str:
    """Writes one section. `page` is a key of PAGE_SPECS."""
    return _write(page, brief)


def write_single_page(
    page: str,
    brief: Dict[str, Any],
    subject: str,
    siblings: Optional[List[str]] = None,
) -> str:
    """Writes ONE page from an agent that normally bundles several.

    Only `service` and `service_area` bundle, so only those two have a
    directive. Any other key falls through to the ordinary path, because
    narrowing an agent that already writes one page is a no-op that would only
    add an instruction contradicting nothing.

    `subject` is the one service or area to write. `siblings` are the opening
    lines already produced for the other pages of the same kind, which is the
    uniqueness signal the bundled reply used to get for free by having them all
    in front of it. See prompts/single_page.py.
    """
    directive = DIRECTIVE_BY_PAGE.get(page)
    if directive is None:
        return _write(page, brief)

    return _write(
        page,
        {
            **brief,
            # The bundled prompt reads this variable as the list to iterate.
            # Narrowing it to the one subject is as necessary as the directive:
            # see LIST_VARIABLE_BY_PAGE.
            LIST_VARIABLE_BY_PAGE[page]: subject,
            "single_subject": subject,
            "sibling_openings": format_siblings(siblings or []),
        },
        extra_system=directive,
    )


def _write(
    page: str, brief: Dict[str, Any], extra_system: str = ""
) -> str:
    """The shared body of both entry points above."""
    spec = PAGE_SPECS[page]
    system_prompt, user_prompt = spec.system_prompt, spec.user_prompt
    if not USE_KNOWLEDGE_BASE:
        system_prompt, user_prompt = _without_knowledge_base(system_prompt, user_prompt)

    # Appended last, so it is the closest instruction to the brief and wins any
    # contradiction with the older n8n wording above it. The single-page
    # directive goes after even that, because it has to override the doctrine's
    # own cross-page wording too.
    system_prompt += DIRECT_RESPONSE_DOCTRINE + extra_system

    template = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("user", user_prompt)]
    )
    fields = {key: brief.get(key, "") for key in template.input_variables}
    messages = template.invoke(fields).to_messages()
    tools = page_tools(page) if USE_KNOWLEDGE_BASE else []
    return run_tool_agent(messages, tools, label=spec.key)
