"""add angle headline and primary_text

Revision ID: b9467e593ded
Revises: 826b0b8431b7
Create Date: 2026-07-23 16:42:35.272171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9467e593ded'
down_revision: Union[str, None] = '826b0b8431b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER a table to add NOT NULL columns or drop
    # a column in place, so this uses the copy-and-move strategy (a no-op on Postgres,
    # which supports ALTER natively). server_default lets existing rows populate the
    # new NOT NULL columns; primary_text backfills from the old `text` column's data
    # via a data migration step, then the defaults are dropped.
    with op.batch_alter_table('ad_angles') as batch_op:
        batch_op.add_column(sa.Column('headline', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(
            sa.Column('primary_text', sa.Text(), nullable=False, server_default='')
        )

    # Backfill primary_text from the old `text` column before dropping it.
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE ad_angles SET primary_text = text"))

    with op.batch_alter_table('ad_angles') as batch_op:
        batch_op.drop_column('text')
        batch_op.alter_column('headline', server_default=None)
        batch_op.alter_column('primary_text', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('ad_angles') as batch_op:
        batch_op.add_column(sa.Column('text', sa.TEXT(), nullable=False, server_default=''))

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE ad_angles SET text = primary_text"))

    with op.batch_alter_table('ad_angles') as batch_op:
        batch_op.alter_column('text', server_default=None)
        batch_op.drop_column('primary_text')
        batch_op.drop_column('headline')
