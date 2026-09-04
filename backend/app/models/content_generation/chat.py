"""The refinement conversation, threaded per VERSION rather than per asset.

Per asset would be the obvious choice and it is the wrong one. Every message is
about a specific piece of text, so a thread that outlives the version it
discusses reads as a conversation about content nobody can see any more. Keying
on (asset_id, version) means restoring an older version brings back its own
thread, and deleting a version takes its messages with it.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ContentAssetChat(Base):
    """One instruction against one version.

    There is no role column. Every row here is something a person typed, so
    there is no second speaker to distinguish it from, and an enum with one
    reachable value earns nothing.

    `asset_id` and `version` are a single composite foreign key into
    cg_asset_versions, not two independent ones. Pointing them separately at
    cg_assets and at nothing would allow a message on a version that was never
    written.
    """

    __tablename__ = "cg_asset_chats"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_id", "version"],
            ["cg_asset_versions.asset_id", "cg_asset_versions.version"],
            ondelete="CASCADE",
            name="cg_asset_chats_version_fk",
        ),
        Index("cg_asset_chats_thread_idx", "asset_id", "version", "created_at"),
    )

    message_id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)

    body = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # Named `asset_version`, not `version`, because that name is taken by the
    # column this relationship is half keyed on.
    asset_version = relationship("ContentAssetVersion", back_populates="chats")
