"""merge website content and post image heads

Two feature branches both migrated from b4f8c1a20e73 (add reels), leaving the
tree with two Alembic heads and `alembic upgrade head` refusing to run:

  b4f8c1a20e73 -> a7c3e91b4d20 -> b43f920701eb   blogs, then website content
  b4f8c1a20e73 -> d2a4f8e91c30 -> e6b3d7f42a91   hero images, then variants

Nothing to do at this revision: the two chains touch disjoint tables, so this
only rejoins them into a single head. Deliberately a merge revision rather than
re-pointing one chain onto the other -- re-pointing would leave any database
already stamped at one head believing the other chain had been applied, and it
would silently never create those tables.

Revision ID: 9fa3bfabd826
Revises: b43f920701eb, e6b3d7f42a91
Create Date: 2026-08-27 12:04:48.772236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fa3bfabd826'
down_revision: Union[str, None] = ('b43f920701eb', 'e6b3d7f42a91')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
