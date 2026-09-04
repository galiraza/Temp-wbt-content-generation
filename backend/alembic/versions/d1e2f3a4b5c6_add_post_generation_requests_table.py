"""add post_generation_requests table

Revision ID: d1e2f3a4b5c6
Revises: c7d9e2f4a8b1
Create Date: 2026-08-10 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c7d9e2f4a8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('post_generation_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_name', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('website_url', sa.String(), nullable=True),
    sa.Column('company_reviews_page_url', sa.String(), nullable=True),
    sa.Column('month', sa.String(), nullable=True),
    sa.Column('fixed_rules', sa.Text(), nullable=True),
    sa.Column('main_topic', sa.Text(), nullable=True),
    sa.Column('promotion', sa.Text(), nullable=True),
    sa.Column('additional_resources', sa.Text(), nullable=True),
    sa.Column('additional_notes', sa.Text(), nullable=True),
    sa.Column('areas_covered', sa.Text(), nullable=True),
    sa.Column('unique_selling_points', sa.Text(), nullable=True),
    sa.Column('post_image_paths', sa.Text(), nullable=True),
    sa.Column('post_reference_image_paths', sa.Text(), nullable=True),
    sa.Column('review_reference_image_path', sa.String(), nullable=True),
    sa.Column('logo_path', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_post_generation_requests_id'), 'post_generation_requests', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_post_generation_requests_id'), table_name='post_generation_requests')
    op.drop_table('post_generation_requests')
