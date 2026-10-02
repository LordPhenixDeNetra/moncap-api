# -*- coding: utf-8 -*-
"""add diplome_url on adhesions (dernier diplôme ou attestation de réussite).

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-10-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "q7r8s9t0u1v2"
down_revision: Union[str, None] = "p6q7r8s9t0u1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("adhesions", sa.Column("diplome_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("adhesions", "diplome_url")
