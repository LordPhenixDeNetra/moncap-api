"""Add pays table and diaspora fields on adhesion

Revision ID: 745c2fea7d42
Revises: ebdd4b6fc77d
Create Date: 2026-07-29 16:27:16.495046

"""

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


revision = '745c2fea7d42'
down_revision = 'ebdd4b6fc77d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('pays',
        sa.Column('id', GUID(length=36), nullable=False),
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('nom', sa.String(length=200), nullable=False),
        sa.Column('continent', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pays_code'), 'pays', ['code'], unique=True)
    op.create_index(op.f('ix_pays_continent'), 'pays', ['continent'], unique=False)
    op.create_index(op.f('ix_pays_nom'), 'pays', ['nom'], unique=True)

    op.add_column('adhesions', sa.Column('est_diaspora', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('adhesions', sa.Column('pays_domicile_id', GUID(length=36), nullable=True))
    op.add_column('adhesions', sa.Column('ville_domicile', sa.String(length=200), nullable=True))
    op.add_column('adhesions', sa.Column('pays_militantisme_id', GUID(length=36), nullable=True))
    op.add_column('adhesions', sa.Column('ville_militantisme', sa.String(length=200), nullable=True))

    op.alter_column('adhesions', 'region_domicile_id', existing_type=sa.UUID(), nullable=True)
    op.alter_column('adhesions', 'departement_domicile_id', existing_type=sa.UUID(), nullable=True)
    op.alter_column('adhesions', 'commune_domicile_id', existing_type=sa.UUID(), nullable=True)
    op.alter_column('adhesions', 'region_militantisme_id', existing_type=sa.UUID(), nullable=True)
    op.alter_column('adhesions', 'departement_militantisme_id', existing_type=sa.UUID(), nullable=True)

    op.create_index(op.f('ix_adhesions_est_diaspora'), 'adhesions', ['est_diaspora'], unique=False)
    op.create_index(op.f('ix_adhesions_pays_domicile_id'), 'adhesions', ['pays_domicile_id'], unique=False)
    op.create_index(op.f('ix_adhesions_pays_militantisme_id'), 'adhesions', ['pays_militantisme_id'], unique=False)

    op.create_foreign_key('fk_adhesions_pays_domicile', 'adhesions', 'pays', ['pays_domicile_id'], ['id'])
    op.create_foreign_key('fk_adhesions_pays_militantisme', 'adhesions', 'pays', ['pays_militantisme_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_adhesions_pays_militantisme', 'adhesions', type_='foreignkey')
    op.drop_constraint('fk_adhesions_pays_domicile', 'adhesions', type_='foreignkey')
    op.drop_index(op.f('ix_adhesions_pays_militantisme_id'), table_name='adhesions')
    op.drop_index(op.f('ix_adhesions_pays_domicile_id'), table_name='adhesions')
    op.drop_index(op.f('ix_adhesions_est_diaspora'), table_name='adhesions')
    op.alter_column('adhesions', 'departement_militantisme_id', existing_type=sa.UUID(), nullable=False)
    op.alter_column('adhesions', 'region_militantisme_id', existing_type=sa.UUID(), nullable=False)
    op.alter_column('adhesions', 'commune_domicile_id', existing_type=sa.UUID(), nullable=False)
    op.alter_column('adhesions', 'departement_domicile_id', existing_type=sa.UUID(), nullable=False)
    op.alter_column('adhesions', 'region_domicile_id', existing_type=sa.UUID(), nullable=False)
    op.drop_column('adhesions', 'ville_militantisme')
    op.drop_column('adhesions', 'pays_militantisme_id')
    op.drop_column('adhesions', 'ville_domicile')
    op.drop_column('adhesions', 'pays_domicile_id')
    op.drop_column('adhesions', 'est_diaspora')
    op.drop_index(op.f('ix_pays_nom'), table_name='pays')
    op.drop_index(op.f('ix_pays_continent'), table_name='pays')
    op.drop_index(op.f('ix_pays_code'), table_name='pays')
    op.drop_table('pays')
