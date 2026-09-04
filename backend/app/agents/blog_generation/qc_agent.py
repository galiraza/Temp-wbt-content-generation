"""Phase 2, the audit side: the Quality Check Agent.

    QC_CHAIN = prompt | llm | QcAudit

Constrained to the QcAudit schema instead of the n8n arrangement, where the agent
returned JSON inside a ```json fence and a Code node stripped the fence with a
regex before calling JSON.parse. That threw on any malformed reply and took the
whole run with it; here LangChain validates and re-asks.

The QC prompt takes the draft twice: once as the content to audit, and once under
a "## REVISION AGENT" heading. Its system message tells it that on a revision it
must check the previously flagged areas first, so the second slot is what
distinguishes round 1 from round N.
"""

import logging

from langchain_core.prompts import ChatPromptTemplate

from app.agents.blog_generation.blog_writer import brief_fields
from app.agents.blog_generation.client import structured_llm
from app.agents.blog_generation.parsers import QcAudit
from app.agents.blog_generation.prompts.qc_prompt import QC_SYSTEM_PROMPT, QC_USER_PROMPT

logger = logging.getLogger("app")

_QC_PROMPT = ChatPromptTemplate.from_messages(
    [("system", QC_SYSTEM_PROMPT), ("user", QC_USER_PROMPT)]
)

#: What goes in the "## REVISION AGENT" slot on the first round, where no
#: revision has happened yet. n8n put the first draft there via an $if on
#: `Revision Agent.isExecuted`, which made round 1 send the same text twice and
#: read as though a revision had already been applied.
_NO_REVISION_YET = "This is the first draft. No revision has been applied yet."


def qc_chain(blog_number: int, round_number: int):
    return _QC_PROMPT | structured_llm(
        QcAudit, label=f"blog-qc-{blog_number}-r{round_number}"
    )


def audit_blog(request, blog, *, content: str, round_number: int, is_revision: bool) -> QcAudit:
    """Scores one draft out of 10 across the prompt's eight weighted areas.

    `blog_number` on the reply is overwritten with the real one: it is the model's
    own echo of an input, and a wrong value there would mislabel a QC round row.
    """
    fields = brief_fields(request, blog)
    audit = qc_chain(blog.blog_number, round_number).invoke(
        {
            **fields,
            "blog_content": content,
            "revision_content": content if is_revision else _NO_REVISION_YET,
        }
    )
    audit.blog_number = blog.blog_number
    logger.info(
        "blog_qc blog_number=%s round=%s score=%s result=%s fixes=%s",
        blog.blog_number,
        round_number,
        audit.score,
        audit.result,
        len(audit.fixes_required),
    )
    return audit
