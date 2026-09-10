"""Add paiements tables: parametres_paiement, cotisations_mensuelles, transactions_kopar

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-09-10 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


# revision identifiers, used by Alembic.
revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parametres_paiement",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("libelle", sa.String(length=300), nullable=False),
        sa.Column("montant_fcfa", sa.Integer(), nullable=True),
        sa.Column("valeur_texte", sa.String(length=500), nullable=True),
        sa.Column("devise", sa.String(length=10), server_default="XOF", nullable=False),
        sa.Column("date_effet", sa.Date(), nullable=False),
        sa.Column("date_fin_effet", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_parametres_paiement_code"),
        "parametres_paiement",
        ["code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parametres_paiement_date_effet"),
        "parametres_paiement",
        ["date_effet"],
        unique=False,
    )
    op.create_index(
        op.f("ix_parametres_paiement_date_fin_effet"),
        "parametres_paiement",
        ["date_fin_effet"],
        unique=False,
    )

    op.create_table(
        "cotisations_mensuelles",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("adhesion_id", GUID(length=36), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("montant", sa.Integer(), nullable=False),
        sa.Column("devise", sa.String(length=10), server_default="XOF", nullable=False),
        sa.Column(
            "statut",
            sa.String(length=50),
            server_default="en_attente",
            nullable=False,
        ),
        sa.Column("paiement_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode_paiement", sa.String(length=100), nullable=True),
        sa.Column("reference_paiement", sa.String(length=200), nullable=True),
        sa.Column(
            "paiement_manuel", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column("paiement_manuel_par_user_id", GUID(length=36), nullable=True),
        sa.Column("paiement_manuel_note", sa.String(length=500), nullable=True),
        sa.Column(
            "relance_envoyee_1", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column(
            "relance_envoyee_2", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["adhesion_id"], ["adhesions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["paiement_manuel_par_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "adhesion_id", "annee", "mois", name="uq_cotisation_adherent_annee_mois"
        ),
    )
    op.create_index(
        op.f("ix_cotisations_mensuelles_adhesion_id"),
        "cotisations_mensuelles",
        ["adhesion_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cotisations_mensuelles_annee"),
        "cotisations_mensuelles",
        ["annee"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cotisations_mensuelles_mois"),
        "cotisations_mensuelles",
        ["mois"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cotisations_mensuelles_statut"),
        "cotisations_mensuelles",
        ["statut"],
        unique=False,
    )

    op.create_table(
        "transactions_kopar",
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("kopar_token", sa.String(length=200), nullable=False),
        sa.Column("kopar_id", sa.String(length=200), nullable=True),
        sa.Column("type_transaction", sa.String(length=50), nullable=False),
        sa.Column("adhesion_id", GUID(length=36), nullable=True),
        sa.Column("cotisation_id", GUID(length=36), nullable=True),
        sa.Column("command_ref", sa.String(length=200), nullable=False),
        sa.Column("command_name", sa.String(length=300), nullable=False),
        sa.Column("montant", sa.Integer(), nullable=False),
        sa.Column("devise", sa.String(length=10), server_default="XOF", nullable=False),
        sa.Column(
            "statut", sa.String(length=50), server_default="new", nullable=False
        ),
        sa.Column("service", sa.String(length=100), nullable=True),
        sa.Column("customer_first_name", sa.String(length=200), nullable=True),
        sa.Column("customer_last_name", sa.String(length=200), nullable=True),
        sa.Column("customer_email", sa.String(length=320), nullable=True),
        sa.Column("customer_phone", sa.String(length=50), nullable=True),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("ipn_url", sa.String(length=500), nullable=True),
        sa.Column("success_url", sa.String(length=500), nullable=True),
        sa.Column("cancel_url", sa.String(length=500), nullable=True),
        sa.Column("custom_fields", sa.JSON(), nullable=True),
        sa.Column("raw_request", sa.JSON(), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("last_webhook_body", sa.JSON(), nullable=True),
        sa.Column(
            "last_webhook_received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "statut_checked_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["adhesion_id"], ["adhesions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["cotisation_id"], ["cotisations_mensuelles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kopar_token"),
    )
    op.create_index(
        op.f("ix_transactions_kopar_adhesion_id"),
        "transactions_kopar",
        ["adhesion_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_command_ref"),
        "transactions_kopar",
        ["command_ref"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_kopar_id"),
        "transactions_kopar",
        ["kopar_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_statut"),
        "transactions_kopar",
        ["statut"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_type_transaction"),
        "transactions_kopar",
        ["type_transaction"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_cotisation_id"),
        "transactions_kopar",
        ["cotisation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_transactions_kopar_cotisation_id"),
        table_name="transactions_kopar",
    )
    op.drop_index(
        op.f("ix_transactions_kopar_type_transaction"),
        table_name="transactions_kopar",
    )
    op.drop_index(
        op.f("ix_transactions_kopar_statut"), table_name="transactions_kopar"
    )
    op.drop_index(
        op.f("ix_transactions_kopar_kopar_id"), table_name="transactions_kopar"
    )
    op.drop_index(
        op.f("ix_transactions_kopar_command_ref"), table_name="transactions_kopar"
    )
    op.drop_index(
        op.f("ix_transactions_kopar_adhesion_id"), table_name="transactions_kopar"
    )
    op.drop_table("transactions_kopar")

    op.drop_index(
        op.f("ix_cotisations_mensuelles_statut"),
        table_name="cotisations_mensuelles",
    )
    op.drop_index(
        op.f("ix_cotisations_mensuelles_mois"), table_name="cotisations_mensuelles"
    )
    op.drop_index(
        op.f("ix_cotisations_mensuelles_annee"),
        table_name="cotisations_mensuelles",
    )
    op.drop_index(
        op.f("ix_cotisations_mensuelles_adhesion_id"),
        table_name="cotisations_mensuelles",
    )
    op.drop_table("cotisations_mensuelles")

    op.drop_index(
        op.f("ix_parametres_paiement_date_fin_effet"),
        table_name="parametres_paiement",
    )
    op.drop_index(
        op.f("ix_parametres_paiement_date_effet"),
        table_name="parametres_paiement",
    )
    op.drop_index(
        op.f("ix_parametres_paiement_code"), table_name="parametres_paiement"
    )
    op.drop_table("parametres_paiement")
