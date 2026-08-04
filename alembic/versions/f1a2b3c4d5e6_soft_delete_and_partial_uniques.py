"""Soft delete adhesions + partial unique indexes

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_adhesions_deleted_at"), "adhesions", ["deleted_at"], unique=False)

    op.execute("UPDATE adhesions SET email = lower(trim(email)) WHERE email IS NOT NULL")
    op.execute("UPDATE adhesions SET cni = trim(cni) WHERE cni IS NOT NULL")
    op.execute("UPDATE adhesions SET carte_electeur = nullif(trim(carte_electeur), '') WHERE carte_electeur IS NOT NULL")

    op.drop_constraint("uq_adhesions_email", "adhesions", type_="unique")
    op.drop_constraint("uq_adhesions_cni", "adhesions", type_="unique")
    op.drop_constraint("uq_adhesions_carte_electeur", "adhesions", type_="unique")

    op.create_index(
        "ux_adhesions_email_active",
        "adhesions",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ux_adhesions_cni_active",
        "adhesions",
        ["cni"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ux_adhesions_carte_electeur_active",
        "adhesions",
        ["carte_electeur"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND carte_electeur IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_adhesions_carte_electeur_active", table_name="adhesions")
    op.drop_index("ux_adhesions_cni_active", table_name="adhesions")
    op.drop_index("ux_adhesions_email_active", table_name="adhesions")

    op.create_unique_constraint("uq_adhesions_email", "adhesions", ["email"])
    op.create_unique_constraint("uq_adhesions_cni", "adhesions", ["cni"])
    op.create_unique_constraint("uq_adhesions_carte_electeur", "adhesions", ["carte_electeur"])

    op.drop_index(op.f("ix_adhesions_deleted_at"), table_name="adhesions")
    op.drop_column("adhesions", "deleted_at")

