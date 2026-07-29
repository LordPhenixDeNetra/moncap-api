"""Add niveau_etude, annees_experience, biographie to adhesions

Revision ID: a1b2c3d4e5f6
Revises: 745c2fea7d42
Create Date: 2026-07-29 17:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "745c2fea7d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("niveau_etude", sa.String(length=200), nullable=True))
    op.add_column("adhesions", sa.Column("annees_experience", sa.Integer(), nullable=True))
    op.add_column("adhesions", sa.Column("biographie", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    op.drop_column("adhesions", "biographie")
    op.drop_column("adhesions", "annees_experience")
    op.drop_column("adhesions", "niveau_etude")
