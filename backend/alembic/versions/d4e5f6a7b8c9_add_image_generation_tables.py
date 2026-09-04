"""add company_assets, angle_images, angle_image_chat_messages

Revision ID: d4e5f6a7b8c9
Revises: c1a2f9d0e3b7
Create Date: 2026-07-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c1a2f9d0e3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'company_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('asset_type', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company_profiles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_assets_id'), 'company_assets', ['id'])
    op.create_index(op.f('ix_company_assets_company_id'), 'company_assets', ['company_id'])

    op.create_table(
        'angle_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('angle_id', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('header_text', sa.String(), nullable=False),
        sa.Column('additional_info', sa.Text(), nullable=True),
        sa.Column('reference_image_path', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['angle_id'], ['ad_angles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_angle_images_id'), 'angle_images', ['id'])
    op.create_index(op.f('ix_angle_images_angle_id'), 'angle_images', ['angle_id'])

    op.create_table(
        'angle_image_chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('angle_image_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['angle_image_id'], ['angle_images.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_angle_image_chat_messages_id'), 'angle_image_chat_messages', ['id']
    )
    op.create_index(
        op.f('ix_angle_image_chat_messages_angle_image_id'),
        'angle_image_chat_messages',
        ['angle_image_id'],
    )


def downgrade() -> None:
    op.drop_table('angle_image_chat_messages')
    op.drop_table('angle_images')
    op.drop_table('company_assets')
