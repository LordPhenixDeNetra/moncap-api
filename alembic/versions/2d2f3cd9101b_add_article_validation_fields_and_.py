"""add article validation fields and moderateur role usage

Revision ID: 2d2f3cd9101b
Revises: i4j5k6l7m8n9
Create Date: 2026-09-18 02:08:07.106757

"""

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


revision = "2d2f3cd9101b"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("validated_by_user_id", GUID(length=36), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("validation_motif", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_articles_validated_at"),
        "articles",
        ["validated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_articles_validated_by_user_id"),
        "articles",
        ["validated_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "articles",
        "users",
        ["validated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "user_roles",
        "role",
        existing_type=sa.VARCHAR(length=17),
        type_=sa.Enum(
            "admin",
            "comite_accueil",
            "comite_directoire",
            "coordinateur_commissariat",
            "coordinateur_regional",
            "militant",
            "moderateur",
            "user",
            name="app_role",
            native_enum=False,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_roles",
        "role",
        existing_type=sa.Enum(
            "admin",
            "comite_accueil",
            "comite_directoire",
            "coordinateur_commissariat",
            "coordinateur_regional",
            "militant",
            "moderateur",
            "user",
            name="app_role",
            native_enum=False,
        ),
        type_=sa.VARCHAR(length=17),
        existing_nullable=False,
    )

    op.drop_constraint(None, "articles", type_="foreignkey")
    op.drop_index(op.f("ix_articles_validated_by_user_id"), table_name="articles")
    op.drop_index(op.f("ix_articles_validated_at"), table_name="articles")
    op.drop_column("articles", "validation_motif")
    op.drop_column("articles", "validated_at")
    op.drop_column("articles", "validated_by_user_id")
