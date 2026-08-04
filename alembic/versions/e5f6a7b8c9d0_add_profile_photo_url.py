"""Add profile photo URL to adhesions

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("profile_photo_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("adhesions", "profile_photo_url")

