"""Add nom prenom to users

Revision ID: ebdd4b6fc77d
Revises: 3317fc3810d3
Create Date: 2026-07-29 16:05:55.607100

"""

from alembic import op
import sqlalchemy as sa


revision = 'ebdd4b6fc77d'
down_revision = '3317fc3810d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('nom', sa.String(length=200), nullable=True))
    op.add_column('users', sa.Column('prenom', sa.String(length=200), nullable=True))
    op.execute("UPDATE users SET nom = '', prenom = '' WHERE nom IS NULL OR prenom IS NULL")
    op.alter_column('users', 'nom', nullable=False)
    op.alter_column('users', 'prenom', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'prenom')
    op.drop_column('users', 'nom')
