"""Plans a Meta ads run: one call for the set, one asset per angle.

Ad angles do not split, and this is the clearest case of the rule in
`planners/__init__.py`. Six angles are six different arguments for the same
service, and "different from the other five" is the specification, not a nice
to have. The prompt says so itself: its role line enforces that the angles are
"generated in one batch". Six independent agents each asked for an angle return
six variations on the most obvious one, and no reconcile pass fixes that,
because nothing is repeated. They are all just the same idea.

So the fan-out here is one task, and the set it returns becomes six asset rows.
That is what the hub needs regardless: each angle is separately reviewable,
restorable and approvable whether or not it was separately written.

The count IS honoured. `num_angles` was already a prompt variable, so honouring
the setting only needed a `count` parameter on `generate_ad_angles` to carry it.
That parameter exists rather than this planner reassigning the module constant,
which two concurrent runs would race on.

Images are not made here. `meta_ads.image_generation` is a separate package and
stays uncalled: the ad creative is built from an approved angle, by request.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.agents.meta_ads.ad_angles import ad_angle_agent
from app.services.content_run.tasks import Plan, Task

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def plan(source: Dict[str, Any], run_id: Any, counts: Dict[str, int]) -> Plan:
    """One task producing the whole set, fanned out into one asset per angle.

    Returns a Plan whose single task carries every angle, and a reconcile that
    is None: there is nothing to reconcile because the set was written together,
    which is the whole reason it was not split.
    """
    wanted = counts.get("ads") or ad_angle_agent.NUM_ANGLES

    company = str(source.get("company_name") or source.get("business_name") or "")
    service = str(source.get("service_name") or "")
    service_content = str(source.get("service_content") or "")
    if not service_content:
        return Plan(
            error="This run has no service content, and the angles are written "
            "from it. Fill in what the service involves and try again."
        )

    logger.info("ads_plan run_id=%s angles=%s", run_id, wanted)
    angles = ad_angle_agent.generate_ad_angles(
        company,
        _as_list(source.get("industry") or source.get("industries")),
        service,
        service_content,
        str(source.get("usps") or source.get("unique_selling_points") or ""),
        _as_list(source.get("offers")),
        count=wanted,
    )
    if not angles:
        return Plan(error="The angle writer returned nothing for this service.")

    tasks: List[Task] = []
    for position, (headline, primary_text) in enumerate(angles):
        body = f"# {headline}\n\n{primary_text}".strip()
        tasks.append(
            Task(
                key=f"ad:{position + 1}",
                section="ads",
                position=position,
                title=headline or f"Angle {position + 1}",
                # Already written. The task exists so the orchestrator persists,
                # slugs and statuses this angle the same way it does every other
                # asset, rather than this content type having its own write path.
                run=lambda body=body: body,
                payload={"headline": headline, "written": True},
            )
        )

    return Plan(tasks=tasks, prepared={"angles": len(angles)})
