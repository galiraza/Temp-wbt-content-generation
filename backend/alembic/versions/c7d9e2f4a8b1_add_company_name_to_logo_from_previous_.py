"""add company_name to logo_from_previous_requests

Revision ID: c7d9e2f4a8b1
Revises: a1b2c3d4e5f6
Create Date: 2026-08-06 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d9e2f4a8b1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('logo_from_previous_requests', sa.Column('company_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('logo_from_previous_requests', 'company_name')
