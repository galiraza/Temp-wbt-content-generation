"""Assets and their version history.

One shape for every kind of generated item, because the UI renders them all
through the same card and queries them as one set. What differs between a reel
and a page group is the section it sits in and the body text, not its columns,
so there is no content_type here: that lives on the run.

Version history is the reason this is two tables. The first cut of the schema
kept only the current text, which meant a regeneration destroyed the thing the
client had already read, and no amount of column-adding fixes that.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import relationship

from app.database import Base

#: Every section across every content type, in one enum. See
#: SECTIONS_BY_CONTENT_TYPE in run.py for which belongs to which.
SECTIONS = (
    "pages",
    "posts",
    "reels",
    "stories",
    "reviews",
    "blogs",
    "scratch",
    "revamp",
    "ads",
)

ASSET_TYPES = ("content", "image", "video")
ASSET_STATUSES = ("generating", "review", "approved")

cg_section = ENUM(*SECTIONS, name="cg_section", create_type=False)
cg_asset_type = ENUM(*ASSET_TYPES, name="cg_asset_type", create_type=False)
cg_asset_status = ENUM(*ASSET_STATUSES, name="cg_asset_status", create_type=False)


class ContentAsset(Base):
    """One generated item: a page group, a post, a reel, a blog, a logo, an ad.

    `client_id` is denormalised off the run so the client-scoped queries the UI
    makes on every tab switch do not need a join.

    There is no `display_version`. Which version a card happens to be showing
    is UI state, and this table is shared with no per-user scoping, so storing
    it would mean one person previewing an older version changed what everyone
    else saw. Preview belongs in React, and a reload then falls back to the
    active version, which is the behaviour you want anyway.
    """

    __tablename__ = "cg_assets"
    __table_args__ = (
        CheckConstraint("active_version > 0", name="cg_assets_active_ck"),
        Index("cg_assets_run_idx", "run_id", "section", "type", "position"),
        Index("cg_assets_client_idx", "client_id", "section"),
        Index(
            "cg_assets_review_idx",
            "client_id",
            postgresql_where=text("status <> 'approved'"),
        ),
        Index(
            "cg_assets_slug_uq",
            "client_id",
            "slug",
            unique=True,
            postgresql_where=text("slug is not null"),
        ),
    )

    asset_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cg_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cg_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    )

    section = Column(cg_section, nullable=False)
    type = Column(cg_asset_type, nullable=False, server_default=text("'content'"))
    position = Column(Integer, nullable=False, server_default=text("0"))
    title = Column(Text, nullable=True)
    status = Column(cg_asset_status, nullable=False, server_default=text("'review'"))

    active_version = Column(Integer, nullable=False, server_default=text("1"))

    #: The URL segment, unique per CLIENT. Wider than (client, section) on
    #: purpose: a logo URL carries no section, so a section-scoped slug would
    #: let /sg/logos/concept-1/image resolve to the wrong asset.
    slug = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    run = relationship("ContentRun", back_populates="assets")
    client = relationship("ContentClient", back_populates="assets")
    versions = relationship(
        "ContentAssetVersion",
        back_populates="asset",
        order_by="ContentAssetVersion.version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ContentAssetVersion(Base):
    """One state of an asset's content, kept forever.

    Keyed on (asset_id, version) rather than a surrogate id, because the version
    number is the identity: `cg_assets.active_version` names a row here, and the
    chat thread hangs off the same pair. A surrogate would let two rows claim
    version 3 of the same asset.

    The brief is not repeated here. It belongs to the run, and copying it per
    version would let the two drift.
    """

    __tablename__ = "cg_asset_versions"

    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cg_assets.asset_id", ondelete="CASCADE"),
        primary_key=True,
    )
    version = Column(Integer, primary_key=True)

    body = Column(Text, nullable=True)
    #: Set for image and video assets, where the content is a Storage path.
    file_path = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    asset = relationship("ContentAsset", back_populates="versions")
    chats = relationship(
        "ContentAssetChat",
        back_populates="asset_version",
        order_by="ContentAssetChat.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
