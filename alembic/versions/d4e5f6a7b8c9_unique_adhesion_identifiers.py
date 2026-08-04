"""Unique constraints for adhesion identifiers

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE adhesions SET email = lower(trim(email)) WHERE email IS NOT NULL")
    op.execute("UPDATE adhesions SET cni = trim(cni) WHERE cni IS NOT NULL")
    op.execute("UPDATE adhesions SET carte_electeur = nullif(trim(carte_electeur), '') WHERE carte_electeur IS NOT NULL")

    op.create_unique_constraint("uq_adhesions_email", "adhesions", ["email"])
    op.create_unique_constraint("uq_adhesions_cni", "adhesions", ["cni"])
    op.create_unique_constraint("uq_adhesions_carte_electeur", "adhesions", ["carte_electeur"])


def downgrade() -> None:
    op.drop_constraint("uq_adhesions_carte_electeur", "adhesions", type_="unique")
    op.drop_constraint("uq_adhesions_cni", "adhesions", type_="unique")
    op.drop_constraint("uq_adhesions_email", "adhesions", type_="unique")

