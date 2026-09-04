"""post module v2: split items into posts and reviews, add the workflow columns

Replaces the single post_generation_items table with two tables, because posts
and reviews carry different fields and every review-only column was sitting null
on the post rows. Adds the columns the ported n8n workflows actually need:
industry (the image mood step reads it), the review template image, the two
researched hashtag pools, the raw scraped markdown, and a status per manager
since the two now run in parallel and fail independently.

Data: the old generated items are dropped. They came from a different agent with
a different prompt and a different field set (kind/category/author), so carrying
them across would mean guessing which post theme each one was. Briefs in
post_generation_requests are preserved; re-run generation to repopulate.

Revision ID: a7c3e9b1d520
Revises: f1a2b3c4d5e6
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7c3e9b1d520"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- request: the new inputs and the split status -----------------------
    op.add_column("post_generation_requests", sa.Column("industry", sa.String(), nullable=True))
    op.add_column(
        "post_generation_requests", sa.Column("review_template_path", sa.String(), nullable=True)
    )
    op.add_column(
        "post_generation_requests", sa.Column("post_hashtag_pool", sa.Text(), nullable=True)
    )
    op.add_column(
        "post_generation_requests", sa.Column("review_hashtag_pool", sa.Text(), nullable=True)
    )
    op.add_column(
        "post_generation_requests",
        sa.Column("scraped_reviews_markdown", sa.Text(), nullable=True),
    )
    op.add_column(
        "post_generation_requests",
        sa.Column("posts_status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column(
        "post_generation_requests",
        sa.Column("reviews_status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column("post_generation_requests", sa.Column("error_message", sa.Text(), nullable=True))

    # Existing rows keep whatever they had reached, applied to both managers.
    op.execute(
        "UPDATE post_generation_requests "
        "SET posts_status = status, reviews_status = status "
        "WHERE status IN ('pending', 'generating', 'complete')"
    )
    op.drop_column("post_generation_requests", "status")

    # --- posts --------------------------------------------------------------
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("post_number", sa.Integer(), nullable=False),
        sa.Column("theme", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["post_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_posts_id"), "posts", ["id"], unique=False)
    op.create_index(op.f("ix_posts_request_id"), "posts", ["request_id"], unique=False)

    # --- reviews ------------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("review", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["post_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reviews_id"), "reviews", ["id"], unique=False)
    op.create_index(op.f("ix_reviews_request_id"), "reviews", ["request_id"], unique=False)

    # --- copy chat board, shared by both via two nullable FKs ---------------
    op.create_table(
        "post_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("review_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Exactly one parent, enforced in the database rather than trusted to the
        # application: a row with both or neither is unreachable from the UI and
        # would be invisible until someone went looking.
        sa.CheckConstraint(
            "(post_id IS NOT NULL AND review_id IS NULL) OR "
            "(post_id IS NULL AND review_id IS NOT NULL)",
            name="ck_post_chat_messages_one_parent",
        ),
    )
    op.create_index(op.f("ix_post_chat_messages_id"), "post_chat_messages", ["id"], unique=False)
    op.create_index(
        op.f("ix_post_chat_messages_post_id"), "post_chat_messages", ["post_id"], unique=False
    )
    op.create_index(
        op.f("ix_post_chat_messages_review_id"), "post_chat_messages", ["review_id"], unique=False
    )

    # --- generated images, versioned by insert ------------------------------
    op.create_table(
        "post_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("review_id", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("background_path", sa.String(), nullable=True),
        sa.Column("layout_variant", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(post_id IS NOT NULL AND review_id IS NULL) OR "
            "(post_id IS NULL AND review_id IS NOT NULL)",
            name="ck_post_images_one_parent",
        ),
    )
    op.create_index(op.f("ix_post_images_id"), "post_images", ["id"], unique=False)
    op.create_index(op.f("ix_post_images_post_id"), "post_images", ["post_id"], unique=False)
    op.create_index(op.f("ix_post_images_review_id"), "post_images", ["review_id"], unique=False)

    op.create_table(
        "post_image_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_image_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachment_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["post_image_id"], ["post_images.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_post_image_chat_messages_id"), "post_image_chat_messages", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_post_image_chat_messages_post_image_id"),
        "post_image_chat_messages",
        ["post_image_id"],
        unique=False,
    )

    # --- the old single-table design ---------------------------------------
    op.drop_index(
        op.f("ix_post_generation_item_chat_messages_item_id"),
        table_name="post_generation_item_chat_messages",
    )
    op.drop_index(
        op.f("ix_post_generation_item_chat_messages_id"),
        table_name="post_generation_item_chat_messages",
    )
    op.drop_table("post_generation_item_chat_messages")
    op.drop_index(op.f("ix_post_generation_items_request_id"), table_name="post_generation_items")
    op.drop_index(op.f("ix_post_generation_items_id"), table_name="post_generation_items")
    op.drop_table("post_generation_items")


def downgrade() -> None:
    op.create_table(
        "post_generation_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.Text(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("author_detail", sa.String(), nullable=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["post_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_post_generation_items_id"), "post_generation_items", ["id"])
    op.create_index(
        op.f("ix_post_generation_items_request_id"), "post_generation_items", ["request_id"]
    )
    op.create_table(
        "post_generation_item_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="content"),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["post_generation_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_post_generation_item_chat_messages_id"), "post_generation_item_chat_messages", ["id"]
    )
    op.create_index(
        op.f("ix_post_generation_item_chat_messages_item_id"),
        "post_generation_item_chat_messages",
        ["item_id"],
    )

    op.drop_table("post_image_chat_messages")
    op.drop_table("post_images")
    op.drop_table("post_chat_messages")
    op.drop_table("reviews")
    op.drop_table("posts")

    op.add_column(
        "post_generation_requests",
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
    )
    op.execute("UPDATE post_generation_requests SET status = posts_status")
    for column in (
        "error_message",
        "reviews_status",
        "posts_status",
        "scraped_reviews_markdown",
        "review_hashtag_pool",
        "post_hashtag_pool",
        "review_template_path",
        "industry",
    ):
        op.drop_column("post_generation_requests", column)
