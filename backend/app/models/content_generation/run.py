"""Runs: one request, and a frozen snapshot of everything it was given.

The brief lives here as jsonb rather than as columns because its shape genuinely
differs by content type (a website run carries a sitemap, a logo run carries an
approach, a blog run carries a month), and because a run has to stay
reproducible after HQ's record changes underneath it. Copying the brief in at
request time is what makes the version history mean anything.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

#: The five content types, in the order the enum declares them.
CONTENT_TYPES = ("website", "social", "blog", "logo", "ads")

CONTENT_TYPE_LABELS = {
    "website": "Website Content",
    "social": "Social Media",
    "blog": "Blog",
    "logo": "Logo",
    "ads": "Meta Ads",
}

#: Which sections a content type may contain. Only `social` genuinely fans out,
#: because one social run produces posts, reels, stories and reviews together.
SECTIONS_BY_CONTENT_TYPE = {
    "website": ("pages",),
    "social": ("posts", "reels", "stories", "reviews"),
    "blog": ("blogs",),
    "logo": ("scratch", "revamp"),
    "ads": ("ads",),
}

#: Statuses a run can reach. `partial` exists because a run of twelve posts
#: where two failed is neither complete nor failed.
RUN_STATUSES = ("pending", "generating", "complete", "partial", "failed")

# create_type=False on every enum in this schema: the types are already in the
# database, applied by schema.sql, and SQLAlchemy attempting to CREATE TYPE or
# DROP TYPE around them would fail or, worse, succeed.
cg_content_type = ENUM(*CONTENT_TYPES, name="cg_content_type", create_type=False)
cg_run_status = ENUM(*RUN_STATUSES, name="cg_run_status", create_type=False)


class ContentRun(Base):
    """One generation request for one client and one content type.

    `version` is per (client_id, content_type), so re-requesting website content
    creates v2 with its own `source` beside v1 rather than overwriting it. The
    unique constraint is what stops two concurrent requests both claiming the
    same number.
    """

    __tablename__ = "cg_runs"
    __table_args__ = (
        UniqueConstraint("client_id", "content_type", "version", name="cg_runs_version_uq"),
        CheckConstraint(
            r"period is null or period ~ '^\d{4}-\d{2}$'", name="cg_runs_period_ck"
        ),
        Index("cg_runs_client_idx", "client_id", "content_type", text("version desc")),
        Index(
            "cg_runs_period_idx",
            "client_id",
            "period",
            postgresql_where=text("period is not null"),
        ),
        Index(
            "cg_runs_source_gin",
            "source",
            postgresql_using="gin",
            postgresql_ops={"source": "jsonb_path_ops"},
        ),
    )

    run_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cg_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )

    content_type = Column(cg_content_type, nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(cg_run_status, nullable=False, server_default=text("'pending'"))

    #: The whole brief: usps, sitemap, industries, meetings, logo approach.
    source = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Generated always as (source ->> 'client_name') stored, so it can be
    # filtered without touching jsonb. FetchedValue marks it read-only: Postgres
    # rejects any INSERT or UPDATE that names a generated column, so the ORM
    # must never include it, only read it back.
    client_name = Column(Text, server_default=FetchedValue())

    period = Column(Text, nullable=True)  # 'YYYY-MM', blog only
    summary = Column(Text, nullable=True)
    requested_by = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    client = relationship("ContentClient", back_populates="runs")
    assets = relationship(
        "ContentAsset",
        back_populates="run",
        order_by="ContentAsset.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
