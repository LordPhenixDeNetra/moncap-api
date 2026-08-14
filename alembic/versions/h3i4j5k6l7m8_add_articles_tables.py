"""Add articles, attachments, likes, comments tables

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-08-14 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


# revision identifiers, used by Alembic.
revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("commissariat", sa.String(length=255), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("author_id", GUID(length=36), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("likes_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_articles_author_id"), "articles", ["author_id"])
    op.create_index(op.f("ix_articles_commissariat"), "articles", ["commissariat"])
    op.create_index(op.f("ix_articles_status"), "articles", ["status"])
    op.create_index(op.f("ix_articles_published_at"), "articles", ["published_at"])
    op.create_index(op.f("ix_articles_deleted_at"), "articles", ["deleted_at"])
    op.create_index("ix_articles_status_published", "articles", ["status", "published_at"])

    op.create_table(
        "article_attachments",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("article_id", GUID(length=36), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("order", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_attachments_article_id"), "article_attachments", ["article_id"])

    op.create_table(
        "article_likes",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("article_id", GUID(length=36), nullable=False),
        sa.Column("user_id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "user_id", name="uq_article_like_user"),
    )
    op.create_index(op.f("ix_article_likes_article_id"), "article_likes", ["article_id"])
    op.create_index(op.f("ix_article_likes_user_id"), "article_likes", ["user_id"])

    op.create_table(
        "article_comments",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("article_id", GUID(length=36), nullable=False),
        sa.Column("author_id", GUID(length=36), nullable=False),
        sa.Column("parent_id", GUID(length=36), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["article_comments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_comments_article_id"), "article_comments", ["article_id"])
    op.create_index(op.f("ix_article_comments_author_id"), "article_comments", ["author_id"])
    op.create_index(op.f("ix_article_comments_parent_id"), "article_comments", ["parent_id"])
    op.create_index(op.f("ix_article_comments_deleted_at"), "article_comments", ["deleted_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_article_comments_deleted_at"), table_name="article_comments")
    op.drop_index(op.f("ix_article_comments_parent_id"), table_name="article_comments")
    op.drop_index(op.f("ix_article_comments_author_id"), table_name="article_comments")
    op.drop_index(op.f("ix_article_comments_article_id"), table_name="article_comments")
    op.drop_table("article_comments")

    op.drop_index(op.f("ix_article_likes_user_id"), table_name="article_likes")
    op.drop_index(op.f("ix_article_likes_article_id"), table_name="article_likes")
    op.drop_table("article_likes")

    op.drop_index(op.f("ix_article_attachments_article_id"), table_name="article_attachments")
    op.drop_table("article_attachments")

    op.drop_index("ix_articles_status_published", table_name="articles")
    op.drop_index(op.f("ix_articles_deleted_at"), table_name="articles")
    op.drop_index(op.f("ix_articles_published_at"), table_name="articles")
    op.drop_index(op.f("ix_articles_status"), table_name="articles")
    op.drop_index(op.f("ix_articles_commissariat"), table_name="articles")
    op.drop_index(op.f("ix_articles_author_id"), table_name="articles")
    op.drop_table("articles")
