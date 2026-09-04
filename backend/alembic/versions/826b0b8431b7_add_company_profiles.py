"""add company profiles

Revision ID: 826b0b8431b7
Revises: b08c26281334
Create Date: 2026-07-23 15:53:41.665524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '826b0b8431b7'
down_revision: Union[str, None] = 'b08c26281334'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('company_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_name', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('website_url', sa.String(), nullable=False),
    sa.Column('reviews_url', sa.String(), nullable=False),
    sa.Column('fixed_rules', sa.Text(), nullable=True),
    sa.Column('areas_covered', sa.Text(), nullable=False),
    sa.Column('usps', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_company_profiles_company_name'), 'company_profiles', ['company_name'], unique=True)
    op.create_index(op.f('ix_company_profiles_id'), 'company_profiles', ['id'], unique=False)

    # batch_alter_table: SQLite can't ALTER a table to add a FK constraint in
    # place, so this uses the copy-and-move strategy (a no-op on Postgres,
    # which supports ALTER natively).
    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index(op.f('ix_ad_angle_requests_company_id'), ['company_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_ad_angle_requests_company_id', 'company_profiles', ['company_id'], ['id']
        )
        batch_op.drop_column('usps')
        batch_op.drop_column('company_name')
        batch_op.alter_column('company_id', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('ad_angle_requests') as batch_op:
        batch_op.add_column(sa.Column('company_name', sa.VARCHAR(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('usps', sa.TEXT(), nullable=False, server_default=''))
        batch_op.drop_constraint('fk_ad_angle_requests_company_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_ad_angle_requests_company_id'))
        batch_op.drop_column('company_id')
        batch_op.alter_column('company_name', server_default=None)
        batch_op.alter_column('usps', server_default=None)

    op.drop_index(op.f('ix_company_profiles_id'), table_name='company_profiles')
    op.drop_index(op.f('ix_company_profiles_company_name'), table_name='company_profiles')
    op.drop_table('company_profiles')
