"""add_transaction_kopar_periode_fields

Ajoute le support des paiements multi-périodes sur transactions_kopar :
  - periode_mois INTEGER (1/3/6/12, NULL=1 rétro)
  - premiere_annee_couverte INTEGER
  - premier_mois_couverte INTEGER

Revision ID: m4n5o6p7q8r9
Revises: z9a8y7x6w5v4
Create Date: 2026-09-23 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "z9a8y7x6w5v4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Ajout 3 colonnes sur transactions_kopar ---
    op.add_column(
        "transactions_kopar",
        sa.Column(
            "periode_mois",
            sa.Integer(),
            nullable=True,
            comment="Période de paiement en mois (1/3/6/12). NULL = 1 mensuel retrocompatibilité.",
        ),
    )
    op.add_column(
        "transactions_kopar",
        sa.Column(
            "premiere_annee_couverte",
            sa.Integer(),
            nullable=True,
            comment="Année du premier mois couvert par la transaction multi-périodes.",
        ),
    )
    op.add_column(
        "transactions_kopar",
        sa.Column(
            "premier_mois_couverte",
            sa.Integer(),
            nullable=True,
            comment="Mois (1-12) du premier mois couvert par la transaction multi-périodes.",
        ),
    )

    # --- CHECK constraint : periode_mois ∈ {1, 3, 6, 12} (ou NULL qui sera backfillé) ---
    op.create_check_constraint(
        "ck_transactions_kopar_periode_mois_allowed",
        "transactions_kopar",
        "periode_mois IN (1, 3, 6, 12)",
    )

    # --- CHECK constraint : premiere_annee_couverte dans [1900, 2300] (parano) ---
    op.create_check_constraint(
        "ck_transactions_kopar_premiere_annee_couverte_range",
        "transactions_kopar",
        "premiere_annee_couverte IS NULL OR (premiere_annee_couverte BETWEEN 1900 AND 2300)",
    )

    # --- CHECK constraint : premier_mois_couverte ∈ [1,12] (ou NULL) ---
    op.create_check_constraint(
        "ck_transactions_kopar_premier_mois_couverte_range",
        "transactions_kopar",
        "premier_mois_couverte IS NULL OR (premier_mois_couverte BETWEEN 1 AND 12)",
    )

    # --- Index sur les 2 nouvelles colonnes utiles au filtrage/audit ---
    op.create_index(
        op.f("ix_transactions_kopar_periode_mois"),
        "transactions_kopar",
        ["periode_mois"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_premiere_annee_couverte"),
        "transactions_kopar",
        ["premiere_annee_couverte"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_kopar_premier_mois_couverte"),
        "transactions_kopar",
        ["premier_mois_couverte"],
        unique=False,
    )

    # --- BACKFILL : anciennes tx (periode_mois NULL) = 1 (mensuel) ---
    # Important pour la réconciliation qui utilisera periode_mois pour décider
    # combien de lignes mensuelles marquer payee (et rétro = 1 seule ligne).
    op.execute(
        sa.text(
            "UPDATE transactions_kopar SET periode_mois = 1 WHERE periode_mois IS NULL"
        )
    )


def downgrade() -> None:
    # --- Drop index PUIS constraints PUIS colonnes (ordre inverse upgrade) ---
    op.drop_index(
        op.f("ix_transactions_kopar_premier_mois_couverte"),
        table_name="transactions_kopar",
    )
    op.drop_index(
        op.f("ix_transactions_kopar_premiere_annee_couverte"),
        table_name="transactions_kopar",
    )
    op.drop_index(
        op.f("ix_transactions_kopar_periode_mois"),
        table_name="transactions_kopar",
    )

    op.drop_constraint(
        "ck_transactions_kopar_premier_mois_couverte_range",
        "transactions_kopar",
        type_="check",
    )
    op.drop_constraint(
        "ck_transactions_kopar_premiere_annee_couverte_range",
        "transactions_kopar",
        type_="check",
    )
    op.drop_constraint(
        "ck_transactions_kopar_periode_mois_allowed",
        "transactions_kopar",
        type_="check",
    )

    op.drop_column("transactions_kopar", "premier_mois_couverte")
    op.drop_column("transactions_kopar", "premiere_annee_couverte")
    op.drop_column("transactions_kopar", "periode_mois")
