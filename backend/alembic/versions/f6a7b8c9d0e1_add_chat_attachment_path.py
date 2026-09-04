"""add attachment_path to angle_image_chat_messages

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_attachment_path() -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        col['name'] == 'attachment_path'
        for col in inspector.get_columns('angle_image_chat_messages')
    )


def upgrade() -> None:
    # Guarded because the column exists in some databases that were never
    # stamped with this revision (it was applied out-of-band before this
    # migration landed). Without the check alembic crash-loops on startup.
    if _has_attachment_path():
        return

    op.add_column(
        'angle_image_chat_messages',
        sa.Column('attachment_path', sa.String(), nullable=True),
    )


def downgrade() -> None:
    if not _has_attachment_path():
        return

    op.drop_column('angle_image_chat_messages', 'attachment_path')
