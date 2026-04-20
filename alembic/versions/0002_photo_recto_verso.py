from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_photo_recto_verso"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("photo_recto_url", sa.String(length=500), nullable=True))
    op.add_column("adhesions", sa.Column("photo_verso_url", sa.String(length=500), nullable=True))
    op.execute("UPDATE adhesions SET photo_recto_url = photo_url WHERE photo_recto_url IS NULL AND photo_url IS NOT NULL")


def downgrade() -> None:
    op.drop_column("adhesions", "photo_verso_url")
    op.drop_column("adhesions", "photo_recto_url")

