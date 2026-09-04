"""How many items a run produces per section, resolved and written.

Two levels, one table. `cg_section_defaults` holds house defaults as rows with a
null client_id and per client overrides as rows with one, so resolution is
coalesce(client row, house row, FALLBACK_ITEM_COUNTS). The hardcoded fallback is
the third level and exists so a deleted or missing row can never stop a run: a
generator asking how many reels always gets a number.

Everything here reads and writes only cg_section_defaults.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from sqlalchemy import delete, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.content_generation.run import SECTIONS_BY_CONTENT_TYPE
from app.models.content_generation.settings import (
    FALLBACK_ITEM_COUNTS,
    ContentSectionDefault,
)

#: The bounds the check constraint enforces, repeated so the API can reject a
#: bad number as a 422 naming the field instead of a 500 from the constraint.
MIN_ITEM_COUNT = 1
MAX_ITEM_COUNT = 50

#: Sections whose count is not the operator to choose, and why.
#:
#: `pages` comes from the sitemap in the brief: asking for six pages when the
#: sitemap lists nine would either drop three or invent three, and both are
#: worse than honouring the sitemap. `blogs` is on the blog form already as
#: `cluster_number`, and a settings row that silently disagreed with a field the
#: operator just filled in is a bug waiting to be reported.
DERIVED_SECTIONS = {
    "pages": "Taken from the sitemap in the brief.",
    "blogs": "Set per run on the blog form.",
}

#: What the settings UI offers, grouped the way the tabs are. Order is the
#: order they render in.
CONFIGURABLE_BY_CONTENT_TYPE: Dict[str, tuple] = {
    "social": ("posts", "reels", "stories", "reviews"),
    "logo": ("scratch", "revamp"),
    "ads": ("ads",),
}

SECTION_LABELS = {
    "pages": "Pages",
    "posts": "Posts",
    "reels": "Reels",
    "stories": "Stories",
    "reviews": "Reviews",
    "blogs": "Blogs",
    "scratch": "From scratch",
    "revamp": "Revamp",
    "ads": "Ads",
}


def _rows(db: Session, client_id: Optional[uuid.UUID]) -> Dict[str, Dict[str, int]]:
    """Both levels in one query, keyed 'house' and 'client'.

    One round trip rather than two, because resolution always needs both: a
    client row without the house row behind it cannot answer a section the
    client has not overridden.
    """
    stmt = select(ContentSectionDefault)
    if client_id is None:
        stmt = stmt.where(ContentSectionDefault.client_id.is_(None))
    else:
        stmt = stmt.where(
            or_(
                ContentSectionDefault.client_id.is_(None),
                ContentSectionDefault.client_id == client_id,
            )
        )

    out: Dict[str, Dict[str, int]] = {"house": {}, "client": {}}
    for row in db.execute(stmt).scalars():
        level = "house" if row.client_id is None else "client"
        out[level][row.section] = row.item_count
    return out


def resolve(db: Session, client_id: Optional[uuid.UUID] = None) -> Dict[str, int]:
    """Every section effective count for this client.

    Always returns a number for every section in FALLBACK_ITEM_COUNTS, so
    callers never branch on a missing key.
    """
    levels = _rows(db, client_id)
    return {
        section: levels["client"].get(section, levels["house"].get(section, fallback))
        for section, fallback in FALLBACK_ITEM_COUNTS.items()
    }


def resolve_for_content_type(
    db: Session, content_type: str, client_id: Optional[uuid.UUID] = None
) -> Dict[str, int]:
    """Just the sections one content type fans out into.

    This is what the orchestrator asks for: a website run has no business
    knowing how many reels a social run would make.
    """
    counts = resolve(db, client_id)
    sections = SECTIONS_BY_CONTENT_TYPE.get(content_type, ())
    return {section: counts[section] for section in sections if section in counts}


def describe(db: Session, client_id: Optional[uuid.UUID] = None) -> List[dict]:
    """The settings panel rows: what each section resolves to, and from where.

    `source` is what lets the UI show "8 (house default)" against an inherited
    row and offer Reset only on an overridden one, without a second call to
    work out which is which.
    """
    levels = _rows(db, client_id)
    out: List[dict] = []

    for content_type, sections in CONFIGURABLE_BY_CONTENT_TYPE.items():
        for section in sections:
            fallback = FALLBACK_ITEM_COUNTS[section]
            house = levels["house"].get(section, fallback)
            own = levels["client"].get(section)
            out.append(
                {
                    "content_type": content_type,
                    "section": section,
                    "label": SECTION_LABELS.get(section, section.title()),
                    "item_count": own if own is not None else house,
                    "house_count": house,
                    "source": "client" if own is not None else "house",
                    "editable": True,
                    "note": "",
                }
            )

    # The derived ones are listed too, greyed and with the reason, rather than
    # left out. Their absence from a panel that shows every other section reads
    # as an oversight and gets asked about; the reason answers it in place.
    for section, note in DERIVED_SECTIONS.items():
        content_type = "website" if section == "pages" else "blog"
        house = levels["house"].get(section, FALLBACK_ITEM_COUNTS[section])
        out.append(
            {
                "content_type": content_type,
                "section": section,
                "label": SECTION_LABELS.get(section, section.title()),
                "item_count": house,
                "house_count": house,
                "source": "derived",
                "editable": False,
                "note": note,
            }
        )

    return out


def put(
    db: Session,
    section: str,
    item_count: int,
    client_id: Optional[uuid.UUID] = None,
) -> int:
    """Set one section count. client_id null writes the house default.

    ON CONFLICT rather than select-then-insert, so two people saving the same
    section at once cannot produce two rows.

    The conflict target must be inferred from columns AND the index predicate,
    not named as a constraint. The two levels are enforced by two partial unique
    indexes, and Postgres accepts ON CONFLICT ON CONSTRAINT only for a real
    constraint, so naming an index there fails with UndefinedObject at execute
    time. Repeating each index predicate as `index_where` is what tells Postgres
    which of the two indexes this insert is arbitrating against; without it the
    house target would be ambiguous, since (section) alone is not unique across
    the whole table.
    """
    if section not in FALLBACK_ITEM_COUNTS:
        raise ValueError(f"unknown section {section!r}")
    if section in DERIVED_SECTIONS:
        raise ValueError(f"{section!r} is derived: {DERIVED_SECTIONS[section]}")
    if not MIN_ITEM_COUNT <= item_count <= MAX_ITEM_COUNT:
        raise ValueError(
            f"item_count must be between {MIN_ITEM_COUNT} and {MAX_ITEM_COUNT}"
        )

    table = ContentSectionDefault.__table__
    if client_id is None:
        target = dict(index_elements=["section"], index_where=text("client_id is null"))
    else:
        target = dict(
            index_elements=["client_id", "section"],
            index_where=text("client_id is not null"),
        )
    stmt = (
        pg_insert(table)
        .values(client_id=client_id, section=section, item_count=item_count)
        .on_conflict_do_update(set_={"item_count": item_count}, **target)
        .returning(table.c.item_count)
    )
    value = db.execute(stmt).scalar_one()
    db.commit()
    return value


def clear(db: Session, section: str, client_id: uuid.UUID) -> None:
    """Drop a client override so the section inherits the house default again.

    Only ever a client row. Deleting a house row is not offered: it would leave
    the section on FALLBACK_ITEM_COUNTS, which is a constant in Python that the
    settings panel cannot show or change, so the value would appear to be stuck.
    """
    db.execute(
        delete(ContentSectionDefault).where(
            ContentSectionDefault.client_id == client_id,
            ContentSectionDefault.section == section,
        )
    )
    db.commit()
