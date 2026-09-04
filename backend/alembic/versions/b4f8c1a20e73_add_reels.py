"""add reels as an independent module: reels, chat board, images, image chat

Reels take four of the twelve slots in a month (2, 5, 9 and 11), so post_number
stops being a 1-8 sequence and becomes the real slot number, with the gaps being
the reels. One model call produces all twelve items and the manager routes each
one to its table by number.

Reels get their own four tables rather than sharing post_chat_messages and
post_images. That was a deliberate call: reel_id can then be NOT NULL, where the
shared tables need two nullable FKs and a CHECK constraint to say exactly one is
set. A reel also has no title, so it could not have shared a table with posts.

Existing posts rows are left numbered 1-8. They are valid as they stand, and
re-running generation replaces them with correctly numbered ones; renumbering old
rows would mean guessing which slot each was written for.

Revision ID: b4f8c1a20e73
Revises: a7c3e9b1d520
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4f8c1a20e73"
down_revision: Union[str, None] = "a7c3e9b1d520"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- reels --------------------------------------------------------------
    op.create_table(
        "reels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        # 2, 5, 9 or 11 — the slot in the 12-item month, not a 1-4 sequence.
        sa.Column("reel_number", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(), nullable=False),
        # The on-screen script. Text, not String: it is multi-line, one line per
        # text card for whoever edits the video.
        sa.Column("reel_text", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["post_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        # No title column: the prompt gives a reel only Reel Text and Reel
        # Caption, so a title would have to be invented.
    )
    op.create_index(op.f("ix_reels_id"), "reels", ["id"], unique=False)
    op.create_index(op.f("ix_reels_request_id"), "reels", ["request_id"], unique=False)

    # --- copy chat board ----------------------------------------------------
    op.create_table(
        "reel_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reel_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reel_id"], ["reels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reel_chat_messages_id"), "reel_chat_messages", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_reel_chat_messages_reel_id"), "reel_chat_messages", ["reel_id"], unique=False
    )

    # --- generated images, versioned by insert ------------------------------
    op.create_table(
        "reel_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reel_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("background_path", sa.String(), nullable=True),
        sa.Column("layout_variant", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reel_id"], ["reels.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reel_images_id"), "reel_images", ["id"], unique=False)
    op.create_index(
        op.f("ix_reel_images_reel_id"), "reel_images", ["reel_id"], unique=False
    )

    op.create_table(
        "reel_image_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reel_image_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachment_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["reel_image_id"], ["reel_images.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reel_image_chat_messages_id"),
        "reel_image_chat_messages",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reel_image_chat_messages_reel_image_id"),
        "reel_image_chat_messages",
        ["reel_image_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("reel_image_chat_messages")
    op.drop_table("reel_images")
    op.drop_table("reel_chat_messages")
    op.drop_table("reels")
