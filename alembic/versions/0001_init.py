from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_regions_nom", "regions", ["nom"], unique=True)

    op.create_table(
        "departements",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("region_id", GUID(), sa.ForeignKey("regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("region_id", "nom", name="uq_departement_region_nom"),
    )
    op.create_index("ix_departements_region_id", "departements", ["region_id"], unique=False)

    op.create_table(
        "communes",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("departement_id", GUID(), sa.ForeignKey("departements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("departement_id", "nom", name="uq_commune_departement_nom"),
    )
    op.create_index("ix_communes_departement_id", "communes", ["departement_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_roles",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "moderator", "user", name="app_role", native_enum=False),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "role", name="uq_user_role"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"], unique=False)
    op.create_index("ix_user_roles_role", "user_roles", ["role"], unique=False)

    op.create_table(
        "refresh_token_sessions",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip", sa.String(length=100), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )
    op.create_index("ix_refresh_token_sessions_user_id", "refresh_token_sessions", ["user_id"], unique=False)
    op.create_index("ix_refresh_token_sessions_token_hash", "refresh_token_sessions", ["token_hash"], unique=False)
    op.create_index("ix_refresh_token_sessions_expires_at", "refresh_token_sessions", ["expires_at"], unique=False)
    op.create_index("ix_refresh_token_sessions_revoked_at", "refresh_token_sessions", ["revoked_at"], unique=False)
    op.create_index("ix_refresh_token_sessions_rotated_at", "refresh_token_sessions", ["rotated_at"], unique=False)

    op.create_table(
        "adhesions",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("nom", sa.String(length=200), nullable=False),
        sa.Column("prenom", sa.String(length=200), nullable=False),
        sa.Column("date_naissance", sa.Date(), nullable=False),
        sa.Column("lieu_naissance", sa.String(length=200), nullable=False),
        sa.Column("profession", sa.String(length=200), nullable=False),
        sa.Column("tel_mobile", sa.String(length=50), nullable=False),
        sa.Column("tel_fixe", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("cni", sa.String(length=100), nullable=False),
        sa.Column("carte_electeur", sa.String(length=100), nullable=True),
        sa.Column("carte_pastef", sa.String(length=100), nullable=True),
        sa.Column("region_domicile_id", GUID(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("departement_domicile_id", GUID(), sa.ForeignKey("departements.id"), nullable=False),
        sa.Column("commune_domicile_id", GUID(), sa.ForeignKey("communes.id"), nullable=False),
        sa.Column("region_militantisme_id", GUID(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("departement_militantisme_id", GUID(), sa.ForeignKey("departements.id"), nullable=False),
        sa.Column("commune_militantisme_id", GUID(), sa.ForeignKey("communes.id"), nullable=True),
        sa.Column("fonction_professionnelle", sa.String(length=200), nullable=False),
        sa.Column(
            "engagement",
            sa.Enum(
                "politique",
                "syndicalisme",
                "societe_civile",
                "autre",
                name="engagement_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("commissariat", sa.String(length=200), nullable=False),
        sa.Column(
            "mode_paiement",
            sa.Enum(
                "wave",
                "orange_money",
                "free_money",
                "carte_bancaire",
                "prelevement_bancaire",
                "especes",
                name="payment_mode",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("montant_adhesion", sa.Integer(), server_default=sa.text("25000"), nullable=False),
        sa.Column("paiement_confirme", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reference_paiement", sa.String(length=200), nullable=True),
        sa.Column("cv_url", sa.String(length=500), nullable=True),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column(
            "statut",
            sa.Enum("en_attente", "validee", "rejetee", "complement", name="adhesion_status", native_enum=False),
            server_default=sa.text("'en_attente'"),
            nullable=False,
        ),
        sa.Column("motif_rejet", sa.String(length=500), nullable=True),
        sa.Column("certification", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_adhesions_email", "adhesions", ["email"], unique=False)
    op.create_index("ix_adhesions_cni", "adhesions", ["cni"], unique=False)
    op.create_index("ix_adhesions_created_at", "adhesions", ["created_at"], unique=False)
    op.create_index("ix_adhesions_commissariat", "adhesions", ["commissariat"], unique=False)
    op.create_index("ix_adhesions_statut", "adhesions", ["statut"], unique=False)
    op.create_index("uq_adhesions_idempotency_key", "adhesions", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_adhesions_idempotency_key", table_name="adhesions")
    op.drop_index("ix_adhesions_statut", table_name="adhesions")
    op.drop_index("ix_adhesions_commissariat", table_name="adhesions")
    op.drop_index("ix_adhesions_created_at", table_name="adhesions")
    op.drop_index("ix_adhesions_cni", table_name="adhesions")
    op.drop_index("ix_adhesions_email", table_name="adhesions")
    op.drop_table("adhesions")

    op.drop_index("ix_refresh_token_sessions_rotated_at", table_name="refresh_token_sessions")
    op.drop_index("ix_refresh_token_sessions_revoked_at", table_name="refresh_token_sessions")
    op.drop_index("ix_refresh_token_sessions_expires_at", table_name="refresh_token_sessions")
    op.drop_index("ix_refresh_token_sessions_token_hash", table_name="refresh_token_sessions")
    op.drop_index("ix_refresh_token_sessions_user_id", table_name="refresh_token_sessions")
    op.drop_table("refresh_token_sessions")

    op.drop_index("ix_user_roles_role", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_communes_departement_id", table_name="communes")
    op.drop_table("communes")

    op.drop_index("ix_departements_region_id", table_name="departements")
    op.drop_table("departements")

    op.drop_index("ix_regions_nom", table_name="regions")
    op.drop_table("regions")

