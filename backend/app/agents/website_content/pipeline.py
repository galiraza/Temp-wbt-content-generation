"""THE PIPELINE - the whole website-content run, and how it flows.

This is the file to read to understand the module. Everything below is pure: it
takes a plain snapshot of the request, calls the agents, and returns what they
produced. No database writes happen here -- app.services.website_content_service
owns those, which is what lets the six sections run on separate threads without
sharing a SQLAlchemy Session (Sessions are not thread-safe).

A SNAPSHOT, not the ORM row, and that distinction is load-bearing. SQLAlchemy
expires every attribute on commit, so reading `request.business_name` off a
committed row silently emits a SELECT to reload it. With six worker threads
sharing one Session that becomes six concurrent queries on one connection, which
fails outright: "This session is provisioning a new connection; concurrent
operations are not permitted". It cost a whole run before RequestSnapshot
existed. Nothing below this line may touch an ORM object.


  INTAKE  (sequential: each step feeds the next)

    Fathom meeting 1..3 URLs
            |                            <-- 3 lookups TOGETHER
            v
    fathom.collect  ->  6 summary/transcript fields + a `note`
            |
            +-------------------+        <-- 2 calls TOGETHER
            |                   |
            v                   v
    extract_sitemap      classify_industries
    (services, areas,    (free-text "Other
     other pages,         Industries" -> the 5
     pricing, accred.)    approved namespaces)
            |                   |
            +---------+---------+
                      |
                      v
                  analyse()  ->  Meeting Insights JSON
                      |          (repaired once if it won't parse)
                      v
                 build_brief()  ->  the dict every page prompt reads


  CONTENT  (the six sections fan out)

                      brief
                        |
    +--------+--------+-+------+--------+--------+   <-- ThreadPoolExecutor(N)
    |        |        |        |        |        |
    v        v        v        v        v        v
  Home    About Us  Services  Areas   Other    Blogs
    |        |        |        |        |        |
    |  each one, independently:                  |  blogs first runs its own
    |                                            |  3 lead-in calls:
    |    write_page -> agent + 5 KB tools        |  industry -> service ->
    |         |                                  |  titles, + keyword lookup
    |         v                                  |
    |    refine_section:                         |
    |      critic -> refiner -> evaluator        |
    |      PASS or turn > 2 ? -> done            |
    |      else carry issues forward, again      |
    |         |                                  |
    v         v                                  v
  SectionOutcome per section -> the service writes it the moment it lands


Why the sections fan out rather than running in sequence:
  n8n fanned out too -- "Content Data" wired straight into six parallel Wait
  nodes -- but each Wait held its branch for a full minute first, purely to
  stagger the API calls. Six sections at up to seven model calls each is slow
  enough without six minutes of deliberate sleeping on top, so the waits are
  replaced by a concurrency cap, which is what they were approximating.

Why the blogs branch is inside the fan-out rather than before it:
  it reads only `complete_meeting_insights` and the brief, both of which exist
  before any section starts. n8n ran it on its own parallel branch for the same
  reason.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.agents.website_content import fathom
from app.agents.website_content.blog_agents import (
    BLOGS_SECTION_TITLE,
    BlogBrief,
    build_brief,
    write_blogs,
)
from app.agents.website_content.intake_agents import (
    analyse,
    classify_industries,
    extract_sitemap,
)
from app.agents.website_content.page_agents import PAGE_ORDER, PAGE_SPECS, write_page
from app.agents.website_content.parsers import SitemapData
from app.agents.website_content.refine import RefinementRound, refine_section
from app.agents.website_content.retry import with_retry as _with_retry

logger = logging.getLogger("app")

#: How many sections are written at once. Each is one agent call (up to 15k
#: output tokens, plus knowledge-base round trips) followed by up to six more
#: for its refinement loop, so this is the knob that trades wall-clock against
#: rate limits. Three matches MAX_CONCURRENT_BLOGS in the blog module, which is
#: tuned for the same Anthropic account.
MAX_CONCURRENT_SECTIONS = 3

#: Every section, in the order the Zapier node assembled them. `blogs` is not in
#: PAGE_ORDER because it is not a page agent -- it has its own lead-in chain.
SECTION_ORDER = PAGE_ORDER + ["blogs"]

SECTION_TITLES = {key: spec.section_title for key, spec in PAGE_SPECS.items()}
SECTION_TITLES["blogs"] = BLOGS_SECTION_TITLE


def _message_of(exc: Exception) -> str:
    """Prefer our own user-facing wording over a raw exception string."""
    return str(getattr(exc, "message", None) or exc)


@dataclass(frozen=True)
class RequestSnapshot:
    """A plain copy of the brief, safe to read from any thread.

    Built once on the thread that owns the Session (see `snapshot`), then handed
    to the pipeline. Frozen so it cannot be mistaken for something writable that
    the service will persist.
    """

    id: int
    business_name: str = ""
    phone_number: str = ""
    email: str = ""
    address: str = ""
    country: str = ""
    state_province_region: str = ""
    zip_postal_code: str = ""
    usps: str = ""
    sitemap_text: str = ""
    industries: tuple = ()
    other_industries: str = ""
    fathom_meeting_1_url: str = ""
    fathom_meeting_2_url: str = ""
    fathom_meeting_3_url: str = ""
    loom_1_summary: str = ""
    loom_1_transcript: str = ""
    loom_2_summary: str = ""
    loom_2_transcript: str = ""
    loom_3_summary: str = ""
    loom_3_transcript: str = ""


def snapshot(row) -> RequestSnapshot:
    """Copies a WebsiteContentRequest row into a thread-safe RequestSnapshot.

    MUST be called on the thread that owns the Session, before any fan-out.
    Every attribute is read here, once, while that is still safe to do.
    """
    return RequestSnapshot(
        id=row.id,
        business_name=row.business_name or "",
        phone_number=row.phone_number or "",
        email=row.email or "",
        address=row.address or "",
        country=row.country or "",
        state_province_region=row.state_province_region or "",
        zip_postal_code=row.zip_postal_code or "",
        usps=row.usps or "",
        sitemap_text=row.sitemap_text or "",
        industries=tuple(row.industries_list),
        other_industries=row.other_industries or "",
        fathom_meeting_1_url=row.fathom_meeting_1_url or "",
        fathom_meeting_2_url=row.fathom_meeting_2_url or "",
        fathom_meeting_3_url=row.fathom_meeting_3_url or "",
        loom_1_summary=row.loom_1_summary or "",
        loom_1_transcript=row.loom_1_transcript or "",
        loom_2_summary=row.loom_2_summary or "",
        loom_2_transcript=row.loom_2_transcript or "",
        loom_3_summary=row.loom_3_summary or "",
        loom_3_transcript=row.loom_3_transcript or "",
    )


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------


@dataclass
class IntakeOutcome:
    """Everything the intake phase produced, or why it couldn't."""

    brief: Dict[str, Any] = field(default_factory=dict)
    sitemap: Optional[SitemapData] = None
    meeting_insights: Optional[Dict[str, Any]] = None
    matched_industries: List[str] = field(default_factory=list)
    #: The kickoff-meeting warning, in the wording Command HQ already documents.
    note: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.brief) and self.meeting_insights is not None


def _joined(values: Optional[List[str]]) -> str:
    """Arrays reach the prompts as text.

    n8n's Set nodes typed these fields as `string` while assigning an array to
    them, so the expression engine stringified each one. The prompts were
    written against that, which is why the analyst's example output describes
    services it was handed as a list.
    """
    if not values:
        return ""
    return ", ".join(str(v) for v in values if str(v).strip())


def _as_text(value: Any) -> str:
    """The same stringification for the nested Meeting Insights objects.

    `sitemap`, `pricing` and `services` are all assigned straight out of the
    analyst's JSON into string-typed Set fields, so the prompts read them as
    JSON text rather than as structured data.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    import json

    return json.dumps(value, ensure_ascii=False)


def build_content_brief(
    request: RequestSnapshot,
    meetings: fathom.MeetingSet,
    sitemap: SitemapData,
    insights: Dict[str, Any],
    matched_industries: List[str],
) -> Dict[str, Any]:
    """The "Content Data" node: one dict every page prompt reads its fields from.

    Field names are the n8n Set node's own, because the prompts reference them
    by those names. Two are worth flagging:

      `accreditiations` keeps the workflow's spelling. It is a placeholder name
      in five prompts; correcting it here would leave those prompts unfilled.

      `industries` is the ticked list and the classified free-text list joined
      with ", ", exactly as the Set node built it:
          "{{ Form Data.industries }}, {{ Parse Json.matched_industries }}"
      The page agents parse this string to choose their knowledge-base tools.
    """
    sitemap_structure = insights.get("sitemap_structure") or {}

    industries = ", ".join(
        part
        for part in (_joined(list(request.industries)), _joined(matched_industries))
        if part
    )

    return {
        # --- straight from the form ---
        "business_name": request.business_name or "",
        "phone_number": request.phone_number or "",
        "email": request.email or "",
        "address": request.address or "",
        "country": request.country or "",
        "state_province_region": request.state_province_region or "",
        "zip_postal_code": request.zip_postal_code or "",
        "unique_selling_points": request.usps or "",
        # --- from the sitemap extractor ---
        "accreditiations": sitemap.accreditation or "",
        # --- from the analyst ---
        "sitemap": _as_text(sitemap_structure),
        "pricing": _as_text(insights.get("service_prices")),
        "services": _as_text(insights.get("services_offered")),
        "areas": _as_text(insights.get("areas_covered")),
        "other_pages": _as_text(sitemap_structure.get("other_pages")),
        "complete_meeting_insights": _as_text(insights),
        # --- the Other Page agent alone reads this, from Form Data ---
        "description_for_other_pages": _as_text(sitemap.other_pages_descriptions),
        "industries": industries,
    }


def run_intake(request: RequestSnapshot) -> IntakeOutcome:
    """Fathom -> sitemap + industries -> analyst -> the content brief.

    The sitemap extraction and the industry classification are independent, so
    they overlap. A failed sitemap extraction is fatal: every page prompt calls
    the sitemap the highest authority and forbids naming a service or area that
    is not on it, so writing without one means inventing the client's business.
    A failed industry classification is not -- see classify_industries.
    """
    meetings = fathom.collect(
        [request.fathom_meeting_1_url, request.fathom_meeting_2_url, request.fathom_meeting_3_url]
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        sitemap_future = pool.submit(_with_retry, extract_sitemap, request.sitemap_text)
        industries_future = pool.submit(classify_industries, request.other_industries)

        try:
            sitemap = sitemap_future.result()
        except Exception as exc:
            logger.exception("website_intake_sitemap_failed request_id=%s", request.id)
            # Wait for the other branch before returning, so its thread is not
            # left running against a request that has already failed.
            industries_future.result()
            return IntakeOutcome(note=meetings.note, error=_message_of(exc))

        matched_industries = industries_future.result()

    analyst_brief = {
        "business_name": request.business_name,
        "phone_number": request.phone_number,
        "email": request.email,
        "address": request.address,
        "country": request.country,
        "state_province_region": request.state_province_region,
        "zip_postal_code": request.zip_postal_code,
        "unique_selling_points": request.usps,
        "fathom_meeting1_summary": meetings.slot(1).summary,
        "fathom_meeting1_transcript": meetings.slot(1).transcript,
        "fathom_meeting2_summary": meetings.slot(2).summary,
        "fathom_meeting2_transcript": meetings.slot(2).transcript,
        "fathom_meeting3_summary": meetings.slot(3).summary,
        "fathom_meeting3_transcript": meetings.slot(3).transcript,
        "loom1_summary": request.loom_1_summary,
        "loom1_transcript": request.loom_1_transcript,
        "loom2_summary": request.loom_2_summary,
        "loom2_transcript": request.loom_2_transcript,
        "loom3_summary": request.loom_3_summary,
        "loom3_transcript": request.loom_3_transcript,
        "sitemap_text": request.sitemap_text,
        "pricing_info": sitemap.pricing_info or "",
        "services_offered": _joined(sitemap.services_offered),
        "areas_covered": _joined(sitemap.areas_covered),
    }

    try:
        insights = _with_retry(analyse, analyst_brief)
    except Exception as exc:
        logger.exception("website_intake_analyst_failed request_id=%s", request.id)
        return IntakeOutcome(sitemap=sitemap, note=meetings.note, error=_message_of(exc))

    brief = build_content_brief(request, meetings, sitemap, insights, matched_industries)
    logger.info(
        "website_intake_done request_id=%s services=%s areas=%s industries=%s",
        request.id,
        len(sitemap.services_offered),
        len(sitemap.areas_covered),
        brief["industries"],
    )
    return IntakeOutcome(
        brief=brief,
        sitemap=sitemap,
        meeting_insights=insights,
        matched_industries=matched_industries,
        note=meetings.note,
    )


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


@dataclass
class SectionOutcome:
    """One section's final state after writing and refinement.

    `status` is "unrefined" rather than "failed" when the refinement loop broke:
    the page is written and is worth having, which is a different thing from the
    writing agent having blown up. n8n had no equivalent -- a failure anywhere in
    the loop took the branch down and the section never reached the Merge node.
    """

    key: str
    section_title: str
    status: str  # passed | needs_review | unrefined | failed
    content: Optional[str] = None
    draft: Optional[str] = None
    rounds: List[RefinementRound] = field(default_factory=list)
    blog_brief: Optional[BlogBrief] = None
    error: Optional[str] = None

    @property
    def turns(self) -> int:
        return len(self.rounds)


def write_section(request: RequestSnapshot, key: str, brief: Dict[str, Any]) -> SectionOutcome:
    """Writes and refines ONE section. Never raises.

    The blogs section takes the same path as the five pages, with its three
    lead-in calls in front: its prompt produces markdown like theirs, and the
    workflow put it through an identical Critic/Refiner/Evaluator loop.
    """
    title = SECTION_TITLES[key]
    label = f"{key}-{request.id}"
    blog_brief: Optional[BlogBrief] = None
    draft: Optional[str] = None

    try:
        if key == "blogs":
            blog_brief = build_brief(brief.get("complete_meeting_insights", ""))
            draft = _with_retry(write_blogs, brief, blog_brief)
        else:
            draft = _with_retry(write_page, key, brief)
    except Exception as exc:
        logger.exception("website_section_failed request_id=%s key=%s", request.id, key)
        return SectionOutcome(
            key=key,
            section_title=title,
            status="failed",
            blog_brief=blog_brief,
            error=_message_of(exc),
        )

    result = refine_section(draft, label=label)

    if result.error is not None:
        status = "unrefined"
    elif result.passed:
        status = "passed"
    else:
        status = "needs_review"

    return SectionOutcome(
        key=key,
        section_title=title,
        status=status,
        content=result.content,
        draft=draft,
        rounds=result.rounds,
        blog_brief=blog_brief,
        error=result.error,
    )


def run_sections(
    request: RequestSnapshot,
    brief: Dict[str, Any],
    keys: Optional[List[str]] = None,
    on_result: Optional[Callable[[SectionOutcome], None]] = None,
) -> List[SectionOutcome]:
    """Writes every section, up to MAX_CONCURRENT_SECTIONS at a time.

    `on_result` is called with each outcome as it finishes, on THIS thread rather
    than the worker that produced it -- which is what lets the service persist
    using its own Session without sharing it across threads. A finished section
    is written the moment it lands, so the UI fills in as the run goes and a
    crash halfway through does not lose the sections already done.

    Ordered by completion, not submission: a slow Service Area section does not
    hold back persisting the Home Page. Order does not matter, because every
    outcome carries its own key.

    One section failing never affects another.
    """
    selected = keys or SECTION_ORDER
    outcomes: List[SectionOutcome] = []

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SECTIONS) as pool:
        futures = [pool.submit(write_section, request, key, brief) for key in selected]
        for future in as_completed(futures):
            outcome = future.result()  # write_section never raises
            outcomes.append(outcome)
            if on_result is not None:
                try:
                    on_result(outcome)
                except Exception:
                    # A persistence failure for one section must not abandon the
                    # rest of the run; the row keeps its "generating" status and
                    # the log carries the reason.
                    logger.exception(
                        "website_section_persist_failed request_id=%s key=%s",
                        request.id,
                        outcome.key,
                    )

    logger.info(
        "website_run_done request_id=%s passed=%s needs_review=%s unrefined=%s failed=%s",
        request.id,
        sum(1 for o in outcomes if o.status == "passed"),
        sum(1 for o in outcomes if o.status == "needs_review"),
        sum(1 for o in outcomes if o.status == "unrefined"),
        sum(1 for o in outcomes if o.status == "failed"),
    )
    return outcomes
