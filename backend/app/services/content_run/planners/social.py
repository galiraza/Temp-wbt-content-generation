"""Plans a social run: one call for the month, one asset per item.

Social does not split today, for two reasons.

The soft one is the same as ads. A month of posts is a designed sequence: the
twelve slots in `post_manager.POST_SLOTS` and `REEL_SLOTS` are an intentional
progression through the month, and the prompt says so, "the month is designed to
move through all twelve slots". The items are less defined by contrast than six
ad angles are, so this is the content type that would most benefit from
splitting, but it is not free either.

The hard one is that the per item entry points that exist,
`post_manager.single_post_chain` and `single_reel_chain`, regenerate an existing
row rather than write a new one from the brief. Splitting the month means giving
them a brief-to-item path, which is a change to the social generator and not to
this layer. Left alone deliberately: it is the honest gap, and it is written
down rather than half done.

WHAT DID CHANGE, AND IT MATTERS

Reels come out of this run as `type='content'`, not `type='video'`. Today a reel
asset holds only the video. Under the content-first rule a reel run produces the
SCRIPT, which is content someone reviews and approves, and the video is made
afterwards from the approved script. That is the same shape as a logo concept and
an ad creative, and it is why the orchestrator will not write a video row at all.

Stories are not generated. `cg_section` has a `stories` value and nothing in
`app/agents/post_generation` produces one, so a run that claimed to make stories
would create empty cards. The section stays in the enum for when a generator
exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from app.agents.post_generation import post_manager, review_manager
from app.services.content_run.tasks import Plan, Task

logger = logging.getLogger(__name__)

#: Sections a social run can actually fill, and the order they are positioned in.
#: `stories` is absent on purpose. See the module docstring.
SUPPORTED_SECTIONS = ("posts", "reels", "reviews")


@dataclass(frozen=True)
class _SocialRequest:
    """Every field the social agents read off a request row.

    Taken from `post_manager._brief_fields` and `research_hashtags`, which are
    the two places that read the request, so this is the whole surface. Frozen
    because it crosses into worker threads.
    """

    id: int
    company_name: str = ""
    phone: str = ""
    email: str = ""
    website_url: str = ""
    month: str = ""
    main_topic: str = ""
    promotion: str = ""
    fixed_rules: str = ""
    areas_covered: str = ""
    additional_resources: str = ""
    additional_notes: str = ""
    unique_selling_points: str = ""
    company_reviews_page_url: str = ""


def _request_from(source: Dict[str, Any]) -> _SocialRequest:
    def field(*names: str) -> str:
        for name in names:
            value = source.get(name)
            if value:
                return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        return ""

    return _SocialRequest(
        id=0,
        company_name=field("company_name", "business_name", "client_name"),
        phone=field("phone", "phone_number"),
        email=field("email"),
        website_url=field("website_url"),
        month=field("month", "period"),
        main_topic=field("main_topic"),
        promotion=field("promotion"),
        fixed_rules=field("fixed_rules"),
        areas_covered=field("areas_covered", "areas"),
        additional_resources=field("additional_resources"),
        additional_notes=field("additional_notes"),
        unique_selling_points=field("unique_selling_points", "usps"),
        company_reviews_page_url=field("company_reviews_page_url"),
    )


def plan(source: Dict[str, Any], run_id: Any, counts: Dict[str, int]) -> Plan:
    """The month in one call, fanned out into one asset per item.

    `counts` can only trim, not extend. The slot structure is baked into the
    prompt as a designed twelve item sequence, and asking for more than that
    would need the prompt to define the extra slots; asking for fewer just drops
    the tail. Reviews are the same: the review prompt says "generate exactly 8
    posts, one per selected review".

    This is a real limit on the settings feature and it is enforced here rather
    than hidden: a setting that quietly did nothing is worse than one that
    trims.
    """
    request = _request_from(source)
    if not request.company_name:
        return Plan(error="This run has no company name, and every post uses it.")
    if not request.main_topic:
        return Plan(
            error="This run has no main topic, so there is nothing for the "
            "month of content to be about."
        )

    items: List[Tuple[str, int, str, str]] = []  # section, position, title, body
    prepared: Dict[str, Any] = {}

    try:
        posts, reels, hashtag_pool = post_manager.generate_posts(request)
        prepared["hashtag_pool"] = hashtag_pool
    except Exception as exc:  # noqa: BLE001
        logger.exception("social_plan_posts_failed run_id=%s", run_id)
        return Plan(error=f"The post writer failed: {exc}")

    items += _items("posts", posts, counts.get("posts"))
    items += _items("reels", reels, counts.get("reels"))

    # Reviews are a separate generator and a separate call, so a failure there
    # costs the reviews and not the month. Twelve good posts with no reviews is
    # a partial run someone can work with.
    try:
        # Returns (reviews, hashtag_pool, scraped). Its own pool, from its own
        # web search: the review writer researches the client's reviews page,
        # which the post writer does not, so the two pools are not the same
        # thing and reusing one for the other would be wrong.
        reviews, review_pool, _scraped = review_manager.generate_reviews(request)
        items += _items("reviews", reviews, counts.get("reviews"))
        if review_pool:
            prepared["review_hashtag_pool"] = review_pool
    except Exception:
        logger.exception("social_plan_reviews_failed run_id=%s", run_id)

    if not items:
        return Plan(error="The social writers returned nothing for this brief.")

    tasks = [
        Task(
            key=f"{section}:{position + 1}",
            section=section,
            position=position,
            title=title,
            # Already written, like the ad angles. The task exists so the
            # orchestrator persists every content type through one path.
            run=lambda body=body: body,
            payload={"written": True},
        )
        for section, position, title, body in items
    ]
    logger.info(
        "social_plan run_id=%s posts=%s reels=%s reviews=%s",
        run_id,
        sum(1 for i in items if i[0] == "posts"),
        sum(1 for i in items if i[0] == "reels"),
        sum(1 for i in items if i[0] == "reviews"),
    )
    return Plan(tasks=tasks, prepared=prepared)


def _items(section: str, raw: Any, wanted: Any) -> List[Tuple[str, int, str, str]]:
    """Normalises one generator's output into (section, position, title, body).

    The three generators return lists of dicts with different keys, so the body
    is assembled from whichever of the known content keys are present rather
    than from a fixed one. A dict with no recognised content key is dropped: it
    is a parse failure, and an asset with an empty body is a blank card.
    """
    rows = list(raw or [])
    if isinstance(wanted, int) and wanted > 0:
        rows = rows[:wanted]

    out: List[Tuple[str, int, str, str]] = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            body = str(row or "").strip()
            title = f"{section[:-1].title()} {position + 1}"
        else:
            body = _body_of(row)
            title = str(
                row.get("title")
                or row.get("headline")
                or row.get("hook")
                or f"{section[:-1].title()} {position + 1}"
            )
        if body:
            out.append((section, position, title[:200], body))
    return out


#: The content keys the three generators use, in the order they read best when
#: more than one is present.
_BODY_KEYS = (
    "hook",
    "headline",
    "caption",
    "content",
    "primary_text",
    "body",
    "script",
    "text",
    "hashtags",
)


def _body_of(row: Dict[str, Any]) -> str:
    parts = []
    for key in _BODY_KEYS:
        value = row.get(key)
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        value = str(value or "").strip()
        if value and value not in parts:
            parts.append(value)
    return "\n\n".join(parts).strip()
