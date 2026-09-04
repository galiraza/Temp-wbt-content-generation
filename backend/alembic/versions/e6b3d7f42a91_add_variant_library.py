"""add variant_library

A global, shared design-layout library the final branded post/review images
are built from - replaces the single Google Doc the n8n workflow read at
generation time. Holds two independent variant systems keyed by `kind`
("post" vs "review"), each with its own A-Z letter scheme, since the source
doc turned out to define two structurally different design languages rather
than one flat set of 26.

Revision ID: e6b3d7f42a91
Revises: d2a4f8e91c30
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e6b3d7f42a91"
down_revision: Union[str, None] = "d2a4f8e91c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "variant_library",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("letter", sa.String(length=1), nullable=False),
        sa.Column("layout_block", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "letter", name="uq_variant_library_kind_letter"),
    )
    op.create_index(op.f("ix_variant_library_id"), "variant_library", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_variant_library_id"), table_name="variant_library")
    op.drop_table("variant_library")
