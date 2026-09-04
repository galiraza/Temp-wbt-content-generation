"""add post_generation_items and their chat messages

Posts and reviews share one table: both carry the same three generated
columns (title, caption, hashtags) and the same lifecycle, and `kind`
separates the two tabs in the Jobs view.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-08-18 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'post_generation_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('caption', sa.Text(), nullable=False),
        sa.Column('hashtags', sa.Text(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('author', sa.String(), nullable=True),
        sa.Column('author_detail', sa.String(), nullable=True),
        sa.Column('image_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['request_id'], ['post_generation_requests.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_post_generation_items_id'), 'post_generation_items', ['id'], unique=False)
    op.create_index(
        op.f('ix_post_generation_items_request_id'), 'post_generation_items', ['request_id'], unique=False
    )

    op.create_table(
        'post_generation_item_chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['post_generation_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_post_generation_item_chat_messages_id'),
        'post_generation_item_chat_messages', ['id'], unique=False,
    )
    op.create_index(
        op.f('ix_post_generation_item_chat_messages_item_id'),
        'post_generation_item_chat_messages', ['item_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_post_generation_item_chat_messages_item_id'),
        table_name='post_generation_item_chat_messages',
    )
    op.drop_index(
        op.f('ix_post_generation_item_chat_messages_id'),
        table_name='post_generation_item_chat_messages',
    )
    op.drop_table('post_generation_item_chat_messages')
    op.drop_index(op.f('ix_post_generation_items_request_id'), table_name='post_generation_items')
    op.drop_index(op.f('ix_post_generation_items_id'), table_name='post_generation_items')
    op.drop_table('post_generation_items')
