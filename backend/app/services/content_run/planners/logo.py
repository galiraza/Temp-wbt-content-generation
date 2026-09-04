"""Plans a logo run: the creative direction, not the logo.

This is the content type the content-first rule changes most, and it changes it
for the better rather than awkwardly.

A logo is an image, so under the old shape a logo run went straight to
`generator_agent` and produced image assets with nothing to review beforehand.
Someone looking at three finished logos has no way to say "the direction is
wrong" except by rejecting all three and paying for three more.

So a logo run now produces the DIRECTION: the style keywords distilled from the
client's USPs, and the visual brief written from them. That is text, it is short,
and it is the thing worth arguing about. Once it is approved, `request_image`
makes the concepts from it.

This costs nothing structurally, because the split already existed in the
package: `usp_style_agent` and `creative_direction_agent` are text, and
`generator_agent` and `editor_agent` are images. The run calls the first two and
stops.

The variation count is therefore not used here. "How many logo variations" is a
question about the image step, so the setting is read by `request_image` rather
than by this planner: a direction does not come in fours.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.agents.logo.creative_direction_agent import generate_ai_creative_direction
from app.agents.logo.usp_style_agent import extract_usp_style_keywords
from app.services.content_run.tasks import Plan, Task

logger = logging.getLogger(__name__)

#: The two approaches a logo run can take, matching cg_section.
#:
#: `scratch` is a new mark, `revamp` is a rework of an existing one. They get
#: different directions because the constraint is different: a revamp has to
#: stay recognisable as the old logo, and a scratch has nothing to stay
#: faithful to.
APPROACHES = ("scratch", "revamp")

_REVAMP_NOTE = (
    "This is a revamp of an existing logo, not a new mark. The direction has "
    "to stay recognisable as the same business: keep whatever the current logo "
    "is known for and say what should change and what must not."
)


def plan(source: Dict[str, Any], run_id: Any, counts: Dict[str, int]) -> Plan:
    """One direction per requested approach. Usually one task, sometimes two.

    `counts` is not read. See the module docstring: the per section numbers for
    logo are variation counts, which belong to the image step.
    """
    company = str(
        source.get("company_name") or source.get("business_name") or source.get("client_name") or ""
    )
    if not company:
        return Plan(error="This run has no company name, and the direction is written for it.")

    industry = source.get("industry") or source.get("industries") or ""
    if isinstance(industry, list):
        industry = ", ".join(str(i) for i in industry)
    industry = str(industry)

    usps = str(source.get("usps") or source.get("unique_selling_points") or "")

    approaches = _approaches(source)
    if not approaches:
        return Plan(
            error="This run does not say whether the logo is from scratch or a "
            "revamp, and the two get different directions."
        )

    # One call, shared. The style keywords come from the USPs, which do not
    # change between a scratch and a revamp, so running it per approach would
    # pay twice for the same answer.
    keywords = ""
    if usps:
        try:
            keywords = extract_usp_style_keywords(usps)
        except Exception:
            logger.exception("logo_plan_keywords_failed run_id=%s", run_id)

    tasks: List[Task] = []
    for position, approach in enumerate(approaches):
        tasks.append(
            Task(
                key=f"logo:{approach}",
                section=approach,
                position=position,
                title=f"Creative direction, {'from scratch' if approach == 'scratch' else 'revamp'}",
                run=_runner(company, industry, keywords, approach),
                payload={"approach": approach, "style_keywords": keywords},
            )
        )

    logger.info("logo_plan run_id=%s approaches=%s", run_id, ",".join(approaches))
    return Plan(tasks=tasks, prepared={"style_keywords": keywords} if keywords else {})


def _approaches(source: Dict[str, Any]) -> List[str]:
    """Which of scratch and revamp this run wants.

    Accepts a list, a single value, or the older boolean-ish spellings the logo
    forms have used, because `source` is written by both the form and the sync
    and they do not agree. Defaults to scratch when nothing says otherwise:
    that is the common case and it is the one that needs no existing artwork.
    """
    raw = source.get("approach") or source.get("approaches") or source.get("logo_approach")
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    picked = [str(v).lower() for v in (raw or [])]

    wanted = [a for a in APPROACHES if a in picked]
    if wanted:
        return wanted

    for approach in APPROACHES:
        if source.get(f"logo_{approach}") or source.get(approach):
            wanted.append(approach)
    return wanted or ["scratch"]


def _runner(company: str, industry: str, keywords: str, approach: str):
    def run() -> str:
        direction = generate_ai_creative_direction(company, industry, keywords)
        parts = [f"# Creative direction: {company}"]
        if industry:
            parts.append(f"**Industry:** {industry}")
        if keywords:
            parts.append(f"**Style:** {keywords}")
        if approach == "revamp":
            parts.append(_REVAMP_NOTE)
        parts.append(direction)
        return "\n\n".join(part for part in parts if part and part.strip())

    return run
