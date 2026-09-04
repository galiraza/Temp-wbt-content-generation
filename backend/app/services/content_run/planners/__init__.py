"""One planner per content type, and the rule for which ones split.

A planner turns a run's frozen `source` into a list of Tasks. The orchestrator
runs them identically for all five content types, so a planner is the only place
that knows what a reel or a service page is.

WHICH CONTENT TYPES SPLIT, AND WHY NOT ALL OF THEM

The instinct is to parallelise everything. It is wrong for half of these, and
the reason is the same reason the service pages needed a reconcile pass: some
sets of items are only good because they were written together.

  split       the items are independent of each other. A service page for
              guttering and one for flat roofs are about different things; blog
              three and blog four cover different topics from the plan. Writing
              them apart loses nothing but a little duplication, which the
              reconcile pass then picks up.

  keep whole  the items are DEFINED by contrast with each other. Six Meta ad
              angles are six different arguments for the same service; the set
              is the deliverable and "different from the other five" is the
              specification. Six independent agents each asked for "an angle"
              return six variations on the most obvious one, and no reconcile
              pass can fix that, because the problem is not a repeated sentence,
              it is six writers who all had the same best idea.

So `blog` fans out, one task per blog. `website`, `ads`, `logo` and `social`
each run their agents whole and then fan out into one asset row per item, which
is what the hub needs either way: every item is separately reviewable,
restorable and approvable whether or not it was separately written.

That is not a limitation waiting to be fixed. Splitting the ad angles would make
the run faster and the ads worse.

Website is the case that was actually built both ways and measured. Splitting it
per page needed the prompts narrowed, lost the cross-page uniqueness the bundled
prompts guarantee, and came out SLOWER, because refinement runs per task and 21
pages means 21 critic/refiner/evaluator loops instead of 5. See
`planners/website.py` for the numbers. It runs five concurrent page-group agents
instead, which is the concurrency the existing pipeline already used.

Social could benefit from splitting on the same test, since its twelve items are
only loosely defined by contrast, and `post_manager` already has
`single_post_chain` and `single_reel_chain`. It is left whole because those
chains regenerate an existing row rather than write from a brief, and reshaping
that is a change to the social generator rather than to this layer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.services.content_run.planners import ads, blog, logo, social, website
from app.services.content_run.tasks import Plan

#: content_type -> plan(source, run_id, counts) -> Plan
_PLANNERS: Dict[str, Callable[..., Plan]] = {
    "website": website.plan,
    "blog": blog.plan,
    "social": social.plan,
    "logo": logo.plan,
    "ads": ads.plan,
}


def plan_for(
    content_type: str, source: Dict[str, Any], run_id: Any, counts: Dict[str, int]
) -> Plan:
    """The plan for one run, or a Plan carrying the reason there isn't one.

    Returns a failed Plan rather than raising for an unknown content type: the
    orchestrator's contract is that a run always ends in a status, and a run
    that raised out of planning would leave a row stuck on `pending`.
    """
    planner = _PLANNERS.get(content_type)
    if planner is None:
        return Plan(error=f"No planner for content type {content_type!r}.")
    return planner(source, run_id, counts)
