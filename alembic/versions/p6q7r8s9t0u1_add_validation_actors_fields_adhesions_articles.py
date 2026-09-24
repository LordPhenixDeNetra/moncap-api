# -*- coding: utf-8 -*-
"""add validation actors audit fields on adhesions and articles.

Revision ID: p6q7r8s9t0u1
Revises: m4n5o6p7q8r9
Create Date: 2026-09-24 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


# revision identifiers, used by Alembic.
revision: str = "p6q7r8s9t0u1"
down_revision: Union[str, None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================
    # Adhésions — Acteurs de validation : rejet / complément
    # Rétrocompatibilité : toutes colonnes NULLABLE.
    # ==========================================================
    op.add_column(
        "adhesions",
        sa.Column("rejete_par_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "adhesions",
        sa.Column("rejete_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "adhesions",
        sa.Column(
            "en_complement_par_user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "adhesions",
        sa.Column("en_complement_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_adhesions_rejete_par_user_id", "adhesions", ["rejete_par_user_id"])
    op.create_index("ix_adhesions_rejete_at", "adhesions", ["rejete_at"])
    op.create_index("ix_adhesions_en_complement_par_user_id", "adhesions", ["en_complement_par_user_id"])
    op.create_index("ix_adhesions_en_complement_at", "adhesions", ["en_complement_at"])

    # ==========================================================
    # Articles — Modération : rejet + clôture
    # Rétrocompatibilité : toutes colonnes NULLABLE.
    # ==========================================================
    op.add_column(
        "articles",
        sa.Column("rejected_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("rejected_motif", sa.Text(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("closed_by_user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_articles_rejected_by_user_id", "articles", ["rejected_by_user_id"])
    op.create_index("ix_articles_rejected_at", "articles", ["rejected_at"])
    op.create_index("ix_articles_rejected_motif", "articles", ["rejected_motif"], mysql_length=255)
    op.create_index("ix_articles_closed_by_user_id", "articles", ["closed_by_user_id"])
    op.create_index("ix_articles_closed_at", "articles", ["closed_at"])


def downgrade() -> None:
    # Articles
    op.drop_index("ix_articles_closed_at", table_name="articles")
    op.drop_index("ix_articles_closed_by_user_id", table_name="articles")
    try:
        op.drop_index("ix_articles_rejected_motif", table_name="articles")
    except Exception:
        pass
    op.drop_index("ix_articles_rejected_at", table_name="articles")
    op.drop_index("ix_articles_rejected_by_user_id", table_name="articles")
    op.drop_column("articles", "closed_at")
    op.drop_column("articles", "closed_by_user_id")
    op.drop_column("articles", "rejected_motif")
    op.drop_column("articles", "rejected_at")
    op.drop_column("articles", "rejected_by_user_id")

    # Adhesions
    op.drop_index("ix_adhesions_en_complement_at", table_name="adhesions")
    op.drop_index("ix_adhesions_en_complement_par_user_id", table_name="adhesions")
    op.drop_index("ix_adhesions_rejete_at", table_name="adhesions")
    op.drop_index("ix_adhesions_rejete_par_user_id", table_name="adhesions")
    op.drop_column("adhesions", "en_complement_at")
    op.drop_column("adhesions", "en_complement_par_user_id")
    op.drop_column("adhesions", "rejete_at")
    op.drop_column("adhesions", "rejete_par_user_id")
