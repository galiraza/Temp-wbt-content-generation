"""drop reviews_url and fixed_rules from company_profiles

Revision ID: c1a2f9d0e3b7
Revises: b9467e593ded
Create Date: 2026-07-24 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2f9d0e3b7'
down_revision: Union[str, None] = 'b9467e593ded'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('company_profiles') as batch_op:
        batch_op.drop_column('reviews_url')
        batch_op.drop_column('fixed_rules')


def downgrade() -> None:
    with op.batch_alter_table('company_profiles') as batch_op:
        batch_op.add_column(sa.Column('reviews_url', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('fixed_rules', sa.Text(), nullable=True))

    with op.batch_alter_table('company_profiles') as batch_op:
        batch_op.alter_column('reviews_url', server_default=None)
