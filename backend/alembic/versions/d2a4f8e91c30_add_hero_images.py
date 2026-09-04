"""add hero_images, plus hero_image_id on posts/reels and images_status on
post_generation_requests

Hero images are a pool of 12 AI-generated candidate background photos,
generated once per request (see hero_image_agent.py) and matched to
individual posts/reels by the content-matching agent (content_matching_agent.py),
which reads `usage` to avoid overusing the same photo. Scoped per-request,
not shared across a client's history - each new month gets its own fresh
set of 12 with usage starting at 0, the direct equivalent of the n8n
workflow's run_key (company+month) grouping, since a request already IS
that same company+month unit.

hero_image_id on Post/Reel is nullable and ON DELETE SET NULL: content
generation and hero-image generation are separate steps triggered by
separate endpoints, so a post can exist with no match yet, and a post's own
generated copy must never disappear because of an image cleanup.

images_status mirrors posts_status/reviews_status - hero-image generation is
a third, independent step with its own status, since it makes its own image
generation calls and doesn't require post/review content to already exist
(it reads post titles as creative anchors, but degrades gracefully with none).

Revision ID: d2a4f8e91c30
Revises: b4f8c1a20e73
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d2a4f8e91c30"
down_revision: Union[str, None] = "b4f8c1a20e73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hero_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        # 1-12, matching the slot in hero_image_prompt.py's output array.
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["post_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_hero_images_id"), "hero_images", ["id"], unique=False)
    op.create_index(
        op.f("ix_hero_images_request_id"), "hero_images", ["request_id"], unique=False
    )

    op.add_column("posts", sa.Column("hero_image_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_posts_hero_image_id", "posts", "hero_images", ["hero_image_id"], ["id"],
        ondelete="SET NULL",
    )

    op.add_column("reels", sa.Column("hero_image_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_reels_hero_image_id", "reels", "hero_images", ["hero_image_id"], ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "post_generation_requests",
        sa.Column("images_status", sa.String(), nullable=False, server_default="pending"),
    )


def downgrade() -> None:
    op.drop_column("post_generation_requests", "images_status")
    op.drop_constraint("fk_reels_hero_image_id", "reels", type_="foreignkey")
    op.drop_column("reels", "hero_image_id")
    op.drop_constraint("fk_posts_hero_image_id", "posts", type_="foreignkey")
    op.drop_column("posts", "hero_image_id")
    op.drop_index(op.f("ix_hero_images_request_id"), table_name="hero_images")
    op.drop_index(op.f("ix_hero_images_id"), table_name="hero_images")
    op.drop_table("hero_images")
