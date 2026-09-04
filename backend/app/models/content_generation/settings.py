from datetime import datetime

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.content_generation.asset import cg_section

#: What the generators produce today, and so what a run produces when nothing
#: has been configured. The database carries the same numbers as global rows;
#: these exist so a missing row can never stop a run.
FALLBACK_ITEM_COUNTS = {
    "pages": 6, "posts": 8, "reels": 4, "stories": 6, "reviews": 8,
    "blogs": 4, "scratch": 4, "revamp": 4, "ads": 6,
}


class ContentSectionDefault(Base):
    """How many items a run should produce for one section.

    Two levels in one table. A row with `client_id` null is the house default; a
    row with a client_id overrides it for that client. Resolution is
    coalesce(client row, global row, FALLBACK_ITEM_COUNTS), so a client who
    always wants eight reels is one row rather than a branch in the generator.

    There is no primary key column. The identity is (client_id, section), and
    Postgres treats nulls as distinct in a unique constraint, so the two levels
    need two partial unique indexes rather than one constraint covering both.
    """

    __tablename__ = "cg_section_defaults"
    __table_args__ = (
        CheckConstraint(
            "item_count between 1 and 50", name="cg_section_defaults_count_ck"
        ),
        Index(
            "cg_section_defaults_global_uq",
            "section",
            unique=True,
            postgresql_where=text("client_id is null"),
        ),
        Index(
            "cg_section_defaults_client_uq",
            "client_id",
            "section",
            unique=True,
            postgresql_where=text("client_id is not null"),
        ),
    )

    #: Null means the house default for this section.
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cg_clients.client_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=True,
    )
    section = Column(cg_section, primary_key=True, nullable=False)
    item_count = Column(Integer, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
