"""Clients, keyed on Command HQ's own uuid.

HQ owns the client list. This table exists only so runs and assets have
something to hang off, and so removing a client can clear its content in one
statement. That is also why there is no surrogate integer id: HQ's clientId IS
the primary key, and the free-text name matching the first cut relied on is
gone for good.
"""

from sqlalchemy import Column, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class ContentClient(Base):
    """One client, as HQ knows it.

    Never created through the API, so `client_id` carries no server default:
    a row with an invented key would silently detach content from the client it
    belongs to, and we would rather the insert fail.

    `updated_at` has no `onupdate`, here or on any table in this schema. A
    Postgres trigger (cg_touch_updated_at) already sets it, and duplicating
    that in Python would let a direct SQL edit and an ORM edit disagree.
    """

    __tablename__ = "cg_clients"

    client_id = Column(UUID(as_uuid=True), primary_key=True)
    client_name = Column(Text, nullable=False)
    client_organization = Column(UUID(as_uuid=True), nullable=True)

    #: When this client last had a run. Maintained by the cg_runs_touch_client
    #: trigger rather than by whoever inserts the run, so it cannot drift: the
    #: rebuild sync and any future generate path both update it without either
    #: having to remember to. Read-only from here.
    last_run_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # passive_deletes on every cascade in this schema: the ON DELETE CASCADE in
    # the DDL is the real mechanism, so the ORM should not load children just to
    # issue DELETEs the database is about to issue anyway.
    runs = relationship(
        "ContentRun",
        back_populates="client",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    assets = relationship(
        "ContentAsset",
        back_populates="client",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
