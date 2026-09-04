"""add blog generation tables

Revision ID: a7c3e91b4d20
Revises: b4f8c1a20e73
Create Date: 2026-08-25 14:10:00.000000

Three tables for the blog module, ported from the n8n "Blogs Content Generation
(V2)" workflow. Two differences from the n8n data tables are baked into the
schema on purpose:

  * revision_attempts is a column on `blogs`, not a single shared counter row.
    n8n kept it in one row of a separate table filtered `>= 0`, so concurrent
    runs corrupted each other's retry counts.
  * blogs are scoped to a request by FK, so an export cannot ship another
    client's blogs. The n8n export read the whole table with returnAll.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91b4d20'
down_revision: Union[str, None] = 'b4f8c1a20e73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blog_generation_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_name', sa.String(), nullable=False),
        sa.Column('website_url', sa.String(), nullable=False),
        sa.Column('cluster_theme_1', sa.Text(), nullable=False),
        sa.Column('cluster_theme_2', sa.Text(), nullable=True),
        sa.Column('cluster_theme_3', sa.Text(), nullable=True),
        sa.Column('cluster_number', sa.Integer(), nullable=True),
        sa.Column('blog_schema_raw', sa.Text(), nullable=False),
        sa.Column('scraped_markdown', sa.Text(), nullable=True),
        sa.Column('website_content', sa.Text(), nullable=True),
        sa.Column('metadata_status', sa.String(), nullable=False),
        sa.Column('content_status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_blog_generation_requests_id'),
        'blog_generation_requests',
        ['id'],
        unique=False,
    )

    op.create_table(
        'blogs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('blog_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('funnel_stage', sa.String(), nullable=True),
        sa.Column('service_areas', sa.Text(), nullable=True),
        sa.Column('keywords', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('gmb_post', sa.Text(), nullable=True),
        sa.Column('gmb_faq', sa.Text(), nullable=True),
        sa.Column('meta_title', sa.String(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('general_notes', sa.Text(), nullable=True),
        sa.Column('qc_score', sa.Integer(), nullable=True),
        sa.Column('qc_result', sa.String(), nullable=True),
        sa.Column('qc_word_count', sa.Integer(), nullable=True),
        sa.Column('qc_fixes', sa.Text(), nullable=True),
        sa.Column('qc_breakdown', sa.Text(), nullable=True),
        sa.Column('revision_attempts', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['blog_generation_requests.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_id', 'blog_number', name='uq_blogs_request_number'),
    )
    op.create_index(op.f('ix_blogs_id'), 'blogs', ['id'], unique=False)
    op.create_index(op.f('ix_blogs_request_id'), 'blogs', ['request_id'], unique=False)

    op.create_table(
        'blog_qc_rounds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('blog_id', sa.Integer(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('result', sa.String(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('fixes', sa.Text(), nullable=True),
        sa.Column('breakdown', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['blog_id'], ['blogs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blog_qc_rounds_id'), 'blog_qc_rounds', ['id'], unique=False)
    op.create_index(
        op.f('ix_blog_qc_rounds_blog_id'), 'blog_qc_rounds', ['blog_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_blog_qc_rounds_blog_id'), table_name='blog_qc_rounds')
    op.drop_index(op.f('ix_blog_qc_rounds_id'), table_name='blog_qc_rounds')
    op.drop_table('blog_qc_rounds')
    op.drop_index(op.f('ix_blogs_request_id'), table_name='blogs')
    op.drop_index(op.f('ix_blogs_id'), table_name='blogs')
    op.drop_table('blogs')
    op.drop_index(op.f('ix_blog_generation_requests_id'), table_name='blog_generation_requests')
    op.drop_table('blog_generation_requests')
