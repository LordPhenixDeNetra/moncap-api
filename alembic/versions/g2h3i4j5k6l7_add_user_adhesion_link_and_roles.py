"""Add user.adhesion_id FK + AppRole new values

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-08-14 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


# revision identifiers, used by Alembic.
revision = "g2h3i4j5k6l7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("adhesion_id", GUID(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_users_adhesion_id"),
        "users",
        ["adhesion_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_users_adhesion_id_adhesions",
        "users",
        "adhesions",
        ["adhesion_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_users_adhesion_id_adhesions",
        "users",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_users_adhesion_id"), table_name="users")
    op.drop_column("users", "adhesion_id")
