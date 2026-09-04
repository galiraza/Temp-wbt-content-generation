# -*- coding: utf-8 -*-
"""Rebuilds the content hub out of the six existing request tables.

The hub shows real content without any of the old tables changing, which is the
only reason it could be built beside a live app instead of migrating it.

Three properties worth relying on:

  READ ONLY ON THE SOURCE. Nothing here issues an INSERT, UPDATE or DELETE
  against any table that is not cg_*. Every source table is read with a single
  SELECT and grouped in memory. If this file were deleted the old app would not
  notice.

  A REBUILD, NOT AN UPSERT. v2 dropped the source_table and source_id columns
  that v1 keyed its upsert on, so there is no longer a key to match an existing
  row against, and inventing one would mean re-adding the columns. Instead
  `rebuild_all` deletes every cg_clients row and re-derives the lot, inside one
  transaction. Repeat calls therefore end in the same state, but the row ids
  change every time, so anything that stored a run_id or asset_id will not find
  it again. That is acceptable only while this is a backfill of content nobody
  has edited in the hub yet. Once approvals, restores or chat threads are being
  written here, this has to become a real incremental sync, because a rebuild
  would take cg_asset_chats with it through the cascade.

  LOSSY ON STATUS ONLY. Nine source statuses collapse onto the three the card
  shows, and logo history is grouped by slot. Everything else the request row
  carries is copied verbatim into `cg_runs.source`, so a run is always traceable
  back to the record it came from.

WHO A CLIENT IS. Command HQ, not us. cg_clients.client_id is HQ's own uuid and
there is no surrogate key, so a name with content but no HQ match has no valid
primary key and is skipped, counted in `skipped_unmatched`. In practice those are
the test rows (Heatable E2E, WBT Live Test, Acme HVAC), which is the outcome we
want anyway.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app import models
from app.services.client_export_service import list_clients

logger = logging.getLogger("app")

#: Company suffixes stripped before matching, so "Green Touch Services LTD" and
#: "Green Touch Services " collapse to one client.
_SUFFIXES = r"(ltd|limited|llp|plc|cic|co|company|services|service|group|uk)"


def match_key(name: Optional[str]) -> Optional[str]:
    """The key a free-text company name is matched to HQ's client list on.

    Live data has "Jk Cooling", "JK Cooling" and "JK Cooling Solutions" as three
    spellings of one client, and "Green Touch Services LTD" against
    "Green Touch Services " as two more. Lowercase, drop punctuation, drop
    trailing company suffixes, collapse whitespace.

    Deliberately not fuzzy. Edit distance would merge genuinely different
    clients, and a wrong merge silently shows one client another's content, so a
    near miss is left as a skip for a human to look at.
    """
    if not name or not name.strip():
        return None
    key = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    key = re.sub(r"\s+", " ", key).strip()
    # strip suffixes off the end, repeatedly: "acme cooling ltd" -> "acme cooling"
    while True:
        stripped = re.sub(r"\s+" + _SUFFIXES + r"$", "", key)
        if stripped == key:
            break
        key = stripped
    return key or None


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: Optional[str], *, fallback: str) -> str:
    """A URL segment for an asset title.

    Deliberately plain: lowercase, alphanumerics, single hyphens, trimmed to 60
    characters on a word boundary so a long page title does not produce an
    unreadable URL. `fallback` covers the rows with no usable title at all,
    which is every logo and image asset.
    """
    text_value = _SLUG_STRIP.sub("-", (value or "").lower()).strip("-")
    if not text_value:
        return fallback
    if len(text_value) > 60:
        text_value = text_value[:60].rsplit("-", 1)[0] or text_value[:60]
    return text_value.strip("-") or fallback


#: Source status -> one of cg_asset_status. "pending" means generated but not
#: signed off, which is exactly Needs review, and a failure is shown for review
#: too because the content that exists is usually worth editing.
_STATUS_MAP = {
    "approved": "approved",
    "passed": "approved",
    "complete": "approved",
    "generating": "generating",
    "pending": "review",
    "needs_review": "review",
    "unrefined": "review",
    "failed": "review",
    "failed_qc": "review",
}


def normalise_status(value: Optional[str]) -> str:
    return _STATUS_MAP.get((value or "").strip().lower(), "review")


#: The values cg_run_status accepts.
_RUN_STATUSES = ("pending", "generating", "complete", "partial", "failed")


def normalise_run_status(*values: Optional[str]) -> str:
    """Collapses a request row's status columns onto one cg_run_status.

    Several source tables carry two or three of them, because their phases fail
    independently: a post request can have every post written and its reviews
    dead. One run cannot be both, and `partial` is the honest answer, which is
    the whole reason that value is in the enum.
    """
    seen = [(v or "").strip().lower() for v in values]
    seen = [v for v in seen if v in _RUN_STATUSES]
    if not seen:
        return "complete"
    if len(set(seen)) == 1:
        return seen[0]
    if "generating" in seen:
        return "generating"
    # A mix of finished and unfinished phases. `partial` unless nothing at all
    # landed, in which case the run never really started.
    if all(v in ("pending", "failed") for v in seen):
        return "failed" if "failed" in seen else "pending"
    return "partial"


def _utc(value: Optional[datetime]) -> datetime:
    """Every source timestamp is a naive datetime.utcnow(), and the cg_* columns
    are timestamptz. Stamping the zone on explicitly means the copy does not
    depend on whatever TimeZone the pooler hands us."""
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _jsonable(value: Any) -> Any:
    """One source column, as jsonb wants it.

    The old tables keep lists and dicts as JSON inside Text columns (industries,
    hashtags, checks, image paths). Decoding them here means `source` holds real
    JSON arrays rather than strings that happen to look like them, so the GIN
    index on the column is usable.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("[", "{"):
            try:
                return json.loads(text)
            except ValueError:
                return value
        return value
    return str(value)


#: Columns left out of `source`: the id is copied in as source_id, and the two
#: timestamps belong to the run itself.
_SOURCE_SKIP = {"id", "created_at", "updated_at"}


def _source_of(row, table: str, client_name: str) -> dict:
    """The whole brief for one run, straight off the request row.

    Every column, not a chosen few. The point of the jsonb is that a run stays
    reproducible after HQ's record and our forms both move on, and a field left
    out now is a field nobody can get back later.

    `client_name` is HQ's spelling, because cg_runs.client_name is generated from
    this key and has to agree with cg_clients. The blog table has a free-text
    column of that name already, so its typed value moves to
    `source_client_name` rather than being lost to the overwrite. Every other
    table names it something else (business_name, company_name) and keeps it
    where it was.
    """
    source = {
        column.name: _jsonable(getattr(row, column.name, None))
        for column in row.__table__.columns
        if column.name not in _SOURCE_SKIP
    }
    if "client_name" in source:
        source["source_client_name"] = source["client_name"]
    source["client_name"] = client_name
    # v2 has no dedicated columns for these, so they live here or nowhere.
    source["source_table"] = table
    source["source_id"] = row.id
    return source


def _group(rows: list, attribute: str) -> Dict[Any, list]:
    """Items keyed by their parent id. One SELECT per item table and this, rather
    than touching the `request.items` relationship, which would lazy load once
    per request row: the pooler is remote and that is what made v1 take minutes."""
    out: Dict[Any, list] = {}
    for row in rows:
        out.setdefault(getattr(row, attribute), []).append(row)
    return out


class _Batch:
    """The rows to be written, held until every source table has been read.

    Ids are generated here rather than left to gen_random_uuid() so children can
    reference their parents without the insert having to come back with a
    RETURNING for each one. That is what lets the whole rebuild go out as four
    executemany statements.
    """

    def __init__(self) -> None:
        self.clients: Dict[uuid.UUID, dict] = {}
        self.runs: List[dict] = []
        self.assets: List[dict] = []
        self.versions: List[dict] = []
        self.asset_counts: Dict[str, int] = {
            "website": 0, "social": 0, "blog": 0, "logo": 0, "ads": 0,
        }
        #: client_id -> slugs already handed out, so the unique index is
        #: satisfied before the insert rather than failing on it.
        self._slugs: Dict[uuid.UUID, set] = {}

    def client(self, hq: dict) -> uuid.UUID:
        """Registers an HQ client as one that has content here."""
        client_id = uuid.UUID(str(hq["clientId"]))
        if client_id not in self.clients:
            organization = hq.get("organizationId")
            self.clients[client_id] = {
                "client_id": client_id,
                "client_name": (hq.get("name") or "").strip() or str(client_id),
                "client_organization": uuid.UUID(str(organization)) if organization else None,
            }
        return client_id

    def run(self, *, client_id, content_type, status, source, summary,
            period=None, created_at=None, sort_key=()) -> uuid.UUID:
        run_id = uuid.uuid4()
        created = _utc(created_at)
        self.runs.append({
            "run_id": run_id,
            "client_id": client_id,
            "content_type": content_type,
            # Filled in by _number_runs once every run is known, because the
            # number depends on the other runs for this client and type.
            "version": 0,
            "status": status,
            "source": source,
            "period": period,
            "summary": summary,
            "requested_by": None,
            "created_at": created,
            "updated_at": created,
            "_sort": (created, *sort_key),
        })
        return run_id

    def asset(self, *, run_id, client_id, content_type, section, type_, position,
              title, status, versions, created_at=None, updated_at=None) -> None:
        """One generated item and its history. `versions` is oldest first."""
        asset_id = uuid.uuid4()
        slug = self._slug(client_id, section, title, position)
        created = _utc(created_at)
        touched = _utc(updated_at or created_at)

        kept = [v for v in versions if (v.get("body") or "").strip() or v.get("file_path")]
        for number, version in enumerate(kept, start=1):
            self.versions.append({
                "asset_id": asset_id,
                "version": number,
                "body": version.get("body"),
                "file_path": version.get("file_path"),
                "created_at": _utc(version.get("created_at") or created_at),
            })

        self.assets.append({
            "asset_id": asset_id,
            "run_id": run_id,
            "client_id": client_id,
            "section": section,
            "type": type_,
            "position": position or 0,
            "title": title,
            "status": status,
            # An asset with nothing to show still has to satisfy active_version > 0.
            "active_version": max(1, len(kept)),
            "slug": slug,
            # Null means "showing the active version", which is where a backfilled
            # card should always open.
            # The source records no approval time, so the row's own last write is
            # the closest thing to when it was signed off.
            "approved_at": touched if status == "approved" else None,
            "created_at": created,
            "updated_at": touched,
        })
        self.asset_counts[content_type] += 1

    def _slug(self, client_id, section: str, title, position) -> str:
        """A slug unique per CLIENT, which is the only scope a URL guarantees.

        Not per (client, section), which is the obvious choice and is wrong: a
        logo asset's URL carries no section by design, so a slug unique only
        within one made /sg/logos/concept-1/image resolve to whichever of
        scratch or revamp happened to come first. JOL SOLAR has concept-1 under
        both, so this was not hypothetical.

        Collisions are common and expected: three website runs each produce a
        "Home Page". The second and later get a numeric suffix rather than a
        hash, because /sg/website-content/home-page-2 is still a URL someone can
        read aloud.
        """
        base = slugify(title, fallback=f"{section}-{(position or 0) + 1}")
        taken = self._slugs.setdefault(client_id, set())
        candidate, n = base, 1
        while candidate in taken:
            n += 1
            candidate = f"{base}-{n}"
        taken.add(candidate)
        return candidate


class _Clients:
    """HQ's client list, indexed by match key, plus the misses.

    Fetched once per rebuild and before anything is deleted, so an HQ outage
    fails the call with the hub still populated rather than emptying it.
    """

    def __init__(self) -> None:
        self.by_key: Dict[str, dict] = {}
        for client in list_clients():
            key = match_key(client.get("name"))
            if key and key not in self.by_key:
                self.by_key[key] = client
        self.unmatched: Dict[str, str] = {}
        self.nameless = 0

    def find(self, name: Optional[str]) -> Optional[dict]:
        key = match_key(name)
        if not key:
            # A request with no company name at all is not an unmatched client,
            # it is a row that never identified one.
            self.nameless += 1
            return None
        hit = self.by_key.get(key)
        if hit is None:
            self.unmatched.setdefault(key, (name or "").strip() or key)
        return hit


# --------------------------------------------------------------------------
# One reader per source module. Each takes a single pass over its tables.
# --------------------------------------------------------------------------


def _read_website(db: Session, batch: _Batch, hq: _Clients) -> None:
    requests = db.query(models.WebsiteContentRequest).all()
    sections = _group(db.query(models.WebsiteSection).all(), "request_id")

    for req in requests:
        client = hq.find(req.business_name)
        if client is None:
            continue
        client_id = batch.client(client)
        items = sorted(sections.get(req.id, []), key=lambda s: (s.position or 0, s.id))
        run_id = batch.run(
            client_id=client_id, content_type="website",
            status=normalise_run_status(req.status),
            source=_source_of(req, "website_content_requests", client["name"]),
            summary=f"Website content, {len(items)} page groups",
            created_at=req.created_at, sort_key=("website_content_requests", req.id),
        )
        for section in items:
            # The refiner sometimes trims a real fact, so the pre-refinement
            # draft is worth keeping as v1 wherever it survived and differs.
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="website",
                section="pages", type_="content", position=section.position,
                title=section.section_title, status=normalise_status(section.status),
                versions=[
                    {"body": section.draft} if section.draft != section.content else {},
                    {"body": section.content},
                ],
                created_at=section.created_at, updated_at=section.updated_at,
            )


def _read_social(db: Session, batch: _Batch, hq: _Clients) -> None:
    requests = db.query(models.PostGenerationRequest).all()
    posts = _group(db.query(models.Post).all(), "request_id")
    reels = _group(db.query(models.Reel).all(), "request_id")
    reviews = _group(db.query(models.Review).all(), "request_id")

    for req in requests:
        client = hq.find(req.company_name)
        if client is None:
            continue
        client_id = batch.client(client)
        req_posts = sorted(posts.get(req.id, []), key=lambda p: (p.post_number or 0, p.id))
        req_reels = sorted(reels.get(req.id, []), key=lambda r: (r.reel_number or 0, r.id))
        req_reviews = sorted(reviews.get(req.id, []), key=lambda v: (v.review_number or 0, v.id))

        run_id = batch.run(
            client_id=client_id, content_type="social",
            status=normalise_run_status(req.posts_status, req.reviews_status),
            source=_source_of(req, "post_generation_requests", client["name"]),
            summary=(f"Social content, {len(req_posts)} posts, "
                     f"{len(req_reels)} reels, {len(req_reviews)} reviews"),
            created_at=req.created_at, sort_key=("post_generation_requests", req.id),
        )
        for post in req_posts:
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="social",
                section="posts", type_="content", position=post.post_number,
                title=post.title, status=normalise_status(post.status),
                versions=[{"body": post.caption}],
                created_at=post.created_at, updated_at=post.updated_at,
            )
        for reel in req_reels:
            # A reel has no title in the source, only a theme, and its body is
            # the on-screen script rather than the caption.
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="social",
                section="reels", type_="video", position=reel.reel_number,
                title=reel.theme, status=normalise_status(reel.status),
                versions=[{"body": reel.reel_text or reel.caption}],
                created_at=reel.created_at, updated_at=reel.updated_at,
            )
        for review in req_reviews:
            # The customer's verbatim words are the asset. The company's response
            # to them stays in `source`, on the run.
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="social",
                section="reviews", type_="content", position=review.review_number,
                title=review.title or review.name, status=normalise_status(review.status),
                versions=[{"body": review.review}],
                created_at=review.created_at, updated_at=review.updated_at,
            )


def _read_blog(db: Session, batch: _Batch, hq: _Clients) -> None:
    requests = db.query(models.BlogGenerationRequest).all()
    blogs = _group(db.query(models.Blog).all(), "request_id")

    for req in requests:
        client = hq.find(req.client_name)
        if client is None:
            continue
        client_id = batch.client(client)
        items = sorted(blogs.get(req.id, []), key=lambda b: (b.blog_number or 0, b.id))
        run_id = batch.run(
            client_id=client_id, content_type="blog",
            status=normalise_run_status(req.content_status),
            source=_source_of(req, "blog_generation_requests", client["name"]),
            summary=f"Blog cluster, {len(items)} blogs",
            # Blogs are the only content type the UI groups by month, and the
            # request date is the only month the source records.
            period=_utc(req.created_at).strftime("%Y-%m"),
            created_at=req.created_at, sort_key=("blog_generation_requests", req.id),
        )
        for blog in items:
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="blog",
                section="blogs", type_="content", position=blog.blog_number,
                title=blog.title, status=normalise_status(blog.status),
                versions=[{"body": blog.content}],
                created_at=blog.created_at, updated_at=blog.updated_at,
            )


def _read_logo(db: Session, batch: _Batch, hq: _Clients) -> None:
    images = db.query(models.LogoImage).all()
    sources = (
        (models.LogoFromScratchRequest, "logo_from_scratch_requests", "scratch",
         "scratch_request_id", "Logo concepts from scratch"),
        (models.LogoFromPreviousRequest, "logo_from_previous_requests", "revamp",
         "previous_request_id", "Logo revamp"),
    )

    for model, table, section, foreign_key, label in sources:
        by_request = _group([i for i in images if getattr(i, foreign_key)], foreign_key)
        for req in db.query(model).all():
            client = hq.find(req.company_name)
            if client is None:
                continue
            client_id = batch.client(client)

            # One asset per slot, not per image row. A request has three concepts
            # and each is its own version history: approving a revision inserted
            # another logo_images row rather than overwriting, so those rows are
            # the only real version history anywhere in the old schema.
            slots: Dict[int, list] = {}
            for image in sorted(by_request.get(req.id, []), key=lambda i: (i.created_at, i.id)):
                slots.setdefault(image.slot or 1, []).append(image)

            run_id = batch.run(
                client_id=client_id, content_type="logo",
                status="complete" if slots else "pending",
                source=_source_of(req, table, client["name"]),
                summary=f"{label}, {len(slots)} concepts",
                created_at=req.created_at, sort_key=(table, req.id),
            )
            for slot in sorted(slots):
                versions = slots[slot]
                batch.asset(
                    run_id=run_id, client_id=client_id, content_type="logo",
                    section=section, type_="image", position=slot,
                    title=f"Concept {slot}",
                    # Logos carry no status column, and an image nobody has
                    # signed off is exactly Needs review.
                    status="review",
                    versions=[{"file_path": i.file_path, "created_at": i.created_at}
                              for i in versions],
                    created_at=versions[0].created_at, updated_at=versions[-1].created_at,
                )


def _read_ads(db: Session, batch: _Batch, hq: _Clients) -> None:
    requests = db.query(models.AdAngleRequest).all()
    angles = _group(db.query(models.AdAngle).all(), "request_id")

    for req in requests:
        client = hq.find(req.company_name)
        if client is None:
            continue
        client_id = batch.client(client)
        items = sorted(angles.get(req.id, []), key=lambda a: (a.order or 0, a.id))
        run_id = batch.run(
            client_id=client_id, content_type="ads",
            status="complete" if items else "pending",
            source=_source_of(req, "ad_angle_requests", client["name"]),
            summary=f"Ad angles for {req.service_name or 'campaign'}",
            created_at=req.created_at, sort_key=("ad_angle_requests", req.id),
        )
        for angle in items:
            batch.asset(
                run_id=run_id, client_id=client_id, content_type="ads",
                section="ads", type_="content", position=angle.order,
                title=angle.headline, status=normalise_status(angle.status),
                versions=[{"body": angle.primary_text}],
                created_at=angle.created_at, updated_at=angle.updated_at,
            )


# --------------------------------------------------------------------------
# The rebuild
# --------------------------------------------------------------------------


def _number_runs(runs: List[dict]) -> None:
    """Numbers runs v1, v2, v3 per client and content type, oldest first.

    Sorted on the source table and id as well as the date, so two requests made
    in the same second always number the same way and a repeat rebuild produces
    the same history. There is a unique constraint on (client_id, content_type,
    version), so a wrong number here is an insert failure, not a display bug.
    """
    counters: Dict[tuple, int] = {}
    for run in sorted(runs, key=lambda r: (str(r["client_id"]), r["content_type"], r["_sort"])):
        key = (run["client_id"], run["content_type"])
        counters[key] = counters.get(key, 0) + 1
        run["version"] = counters[key]


def _insertable(rows: List[dict]) -> List[dict]:
    """Strips the bookkeeping keys the batch carried for its own sorting."""
    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]


def rebuild_all(db: Session) -> dict:
    """Deletes every cg_* content row and re-derives the lot from the source.

    A rebuild rather than an upsert because v2 has no source_table or source_id
    columns to match an existing row on. The delete cascades from cg_clients
    through runs, assets, versions and chats, so calling this repeatedly is safe
    and ends in the same state, with new uuids each time. See the module
    docstring for why that is fine now and will not be later.

    Ordered so that a failure leaves the hub as it was: HQ's client list is
    fetched and every source table read before anything is deleted, and the
    delete and the four inserts share one transaction.
    """
    started = datetime.now(timezone.utc)
    hq = _Clients()
    batch = _Batch()

    _read_website(db, batch, hq)
    _read_social(db, batch, hq)
    _read_blog(db, batch, hq)
    _read_logo(db, batch, hq)
    _read_ads(db, batch, hq)
    _number_runs(batch.runs)

    db.execute(delete(models.ContentClient))
    for model, rows in (
        (models.ContentClient, list(batch.clients.values())),
        (models.ContentRun, _insertable(batch.runs)),
        (models.ContentAsset, batch.assets),
        (models.ContentAssetVersion, batch.versions),
    ):
        if rows:
            db.execute(insert(model), rows)
    db.commit()

    counts = dict(batch.asset_counts)
    counts.update({
        "clients": len(batch.clients),
        "runs": len(batch.runs),
        "assets": len(batch.assets),
        "versions": len(batch.versions),
        "skipped_unmatched": len(hq.unmatched),
    })
    logger.info(
        "content_hub_rebuild %s in %.1fs, skipped %s, unnamed requests %s",
        counts, (datetime.now(timezone.utc) - started).total_seconds(),
        sorted(hq.unmatched.values()), hq.nameless,
    )
    return counts


def sync_all(db: Session) -> dict:
    """The name the router calls. A full rebuild, not an incremental sync: see
    `rebuild_all`, which is what this does and what it is honestly called."""
    return rebuild_all(db)
