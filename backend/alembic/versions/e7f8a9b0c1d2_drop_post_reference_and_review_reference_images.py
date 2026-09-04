"""drop post_reference_image_paths and review_reference_image_path

Post generation no longer takes reference images: posts and reviews are
generated as text only (title, caption, hashtags), and an image is generated
per item on demand from the approved copy, so there is nothing to replicate
a reference layout from.

Note: any Storage objects these columns pointed at are NOT deleted by this
migration and are orphaned once it runs.

Revision ID: e7f8a9b0c1d2
Revises: d1e2f3a4b5c6
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('post_generation_requests') as batch_op:
        batch_op.drop_column('post_reference_image_paths')
        batch_op.drop_column('review_reference_image_path')


def downgrade() -> None:
    with op.batch_alter_table('post_generation_requests') as batch_op:
        batch_op.add_column(sa.Column('post_reference_image_paths', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('review_reference_image_path', sa.String(), nullable=True))
