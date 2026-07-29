"""Add commissariat scientifique principal/secondaire fields

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a1
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("commissariat_scientifique_principal", sa.String(length=200), nullable=True))
    op.add_column("adhesions", sa.Column("commissariat_scientifique_secondaire", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("adhesions", "commissariat_scientifique_secondaire")
    op.drop_column("adhesions", "commissariat_scientifique_principal")

