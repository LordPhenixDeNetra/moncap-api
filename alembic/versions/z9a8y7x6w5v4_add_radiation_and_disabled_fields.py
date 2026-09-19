"""Add radiation fields on adhesions + disabled fields on users

Revision ID: z9a8y7x6w5v4
Revises: 2d2f3cd9101b
Create Date: 2026-09-20 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


revision = "z9a8y7x6w5v4"
down_revision = "2d2f3cd9101b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === adhesions: colonnes radiation ===
    op.add_column(
        "adhesions",
        sa.Column("radie_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "adhesions",
        sa.Column("radie_par_user_id", GUID(length=36), nullable=True),
    )
    op.add_column(
        "adhesions",
        sa.Column(
            "radiation_reason_code",
            sa.Enum(
                "3_mois_impayes_consecutifs",
                "manuel_admin",
                name="disabled_reason",
                native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "adhesions",
        sa.Column("radiation_motif", sa.String(length=1000), nullable=True),
    )
    op.create_index(
        op.f("ix_adhesions_radie_at"),
        "adhesions",
        ["radie_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_adhesions_radie_par_user_id"),
        "adhesions",
        ["radie_par_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_adhesions_radiation_reason_code"),
        "adhesions",
        ["radiation_reason_code"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "adhesions",
        "users",
        ["radie_par_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # === users: colonnes désactivation ===
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "disabled_reason_code",
            sa.Enum(
                "3_mois_impayes_consecutifs",
                "manuel_admin",
                name="disabled_reason",
                native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("disabled_by_user_id", GUID(length=36), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("disabled_motif", sa.String(length=1000), nullable=True),
    )
    op.create_index(
        op.f("ix_users_is_active"),
        "users",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_users_disabled_at"),
        "users",
        ["disabled_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_users_disabled_reason_code"),
        "users",
        ["disabled_reason_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_users_disabled_by_user_id"),
        "users",
        ["disabled_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "users",
        "users",
        ["disabled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # === users ===
    op.drop_constraint(None, "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_disabled_by_user_id"), table_name="users")
    op.drop_index(op.f("ix_users_disabled_reason_code"), table_name="users")
    op.drop_index(op.f("ix_users_disabled_at"), table_name="users")
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_column("users", "disabled_motif")
    op.drop_column("users", "disabled_by_user_id")
    op.drop_column("users", "disabled_reason_code")
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "is_active")

    # === adhesions ===
    op.drop_constraint(None, "adhesions", type_="foreignkey")
    op.drop_index(op.f("ix_adhesions_radiation_reason_code"), table_name="adhesions")
    op.drop_index(op.f("ix_adhesions_radie_par_user_id"), table_name="adhesions")
    op.drop_index(op.f("ix_adhesions_radie_at"), table_name="adhesions")
    op.drop_column("adhesions", "radiation_motif")
    op.drop_column("adhesions", "radiation_reason_code")
    op.drop_column("adhesions", "radie_par_user_id")
    op.drop_column("adhesions", "radie_at")
