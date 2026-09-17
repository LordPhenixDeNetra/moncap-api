"""Vérification rapide données membres emails ramand@gmail.com, ousmane@gmail.com
(adhésion payée + cotisation du mois + transactions Kopar).
Usage:
    python -m app.cli.verifier_membres_paiements
"""
from __future__ import annotations

import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def main():
    db_url = os.environ.get("DATABASE_URL") or "postgresql+psycopg2://thior:Passer123@postgresql-thior.alwaysdata.net:5432/thior_moncap"
    # strip leading postgresql+psycopg2:// → → postgresql:// for psycopg2
    db_url_plain = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    emails = ["ramand@gmail.com", "ousmane@gmail.com"]
    today = date.today()
    mois_courant = today.month
    annee_courant = today.year

    print("=" * 110)
    print(f"VERIFICATION DONNEES {emails} — {today}")
    print("=" * 110)

    with psycopg2.connect(db_url_plain) as conn:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1) users + adhesions (join users.user_id=adhesions.user_id)
            placeholders = ", ".join(["%s"] * len(emails))
            q_users = f"""
            SELECT u.id AS user_id, u.email, u.nom AS user_nom, u.prenom AS user_prenom, u.adhesion_id AS user_adhesion_id,
                   a.id AS adhesion_id, a.statut AS adhesion_statut,
                   a.paiement_confirme AS adhesion_paiement_confirme,
                   a.reference_paiement AS adhesion_reference_paiement,
                   a.montant_adhesion AS adhesion_montant, a.created_at AS adhesion_created_at,
                   a.nom AS adhesion_nom, a.prenom AS adhesion_prenom, a.email AS adhesion_email
            FROM users u
            LEFT JOIN adhesions a ON u.adhesion_id = a.id
            WHERE LOWER(u.email) IN ({placeholders})
               OR LOWER(a.email) IN ({placeholders})
            """
            cur.execute(q_users, emails + emails)
            users_rows = cur.fetchall()

            if not users_rows:
                print("AUCUN UTILISATEUR / ADHESION TROUVE pour ces emails.")
                print("Recherche élargie dans adhesions.email...")
                cur.execute(f"""
                SELECT id AS adhesion_id, email, nom, prenom, statut, paiement_confirme, reference_paiement, montant_adhesion
                FROM adhesions WHERE LOWER(email) IN ({placeholders})
                """, emails)
                adh_only = cur.fetchall()
                for r in adh_only:
                    print(dict(r))
                return

            for u in users_rows:
                print("\n" + "#" * 100)
                print(f"MEMBRE email={u['email']} user_id={u['user_id']} adhesion_id={u['adhesion_id']}")
                print(f"   USER  nom/prenom   : {u.get('user_nom')} {u.get('user_prenom')}")
                print(f"   ADH   nom/prenom   : {u.get('adhesion_nom')} {u.get('adhesion_prenom')} (email fiche: {u.get('adhesion_email')})")
                print(f"   ADH   statut       : {u['adhesion_statut']}")
                print(f"   ADH   paiement_confirme : {u['adhesion_paiement_confirme']}")
                print(f"   ADH   reference_paiement: {u['adhesion_reference_paiement']}")
                print(f"   ADH   montant adhesion   : {u['adhesion_montant']} FCFA")
                adhesion_id = u["adhesion_id"]

                # 2) Transactions Kopar (adhesion + cotisation) — TOUTES
                if adhesion_id:
                    cur.execute("""
                    SELECT id, kopar_token, type_transaction, statut, montant, devise, adhesion_id, cotisation_id,
                           command_ref, service, created_at, updated_at, last_webhook_received_at,
                           custom_fields
                    FROM transactions_kopar
                    WHERE adhesion_id = %s OR EXISTS (
                        SELECT 1 FROM cotisations_mensuelles cm
                        WHERE cm.adhesion_id = %s AND cm.id = transactions_kopar.cotisation_id
                    )
                    ORDER BY created_at DESC
                    """, (adhesion_id, adhesion_id))
                    txs = cur.fetchall()
                    print(f"\n   TRANSACTIONS KOPAR ({len(txs)}) :")
                    for t in txs:
                        cf = t["custom_fields"]
                        cfs = (cf if isinstance(cf, dict) else {})
                        mois_tx = cfs.get("mois") if cfs else None
                        annee_tx = cfs.get("annee") if cfs else None
                        print(f"     - [{t['created_at']}] id={str(t['id'])[:10]}... type={t['type_transaction']:12s} statut={t['statut']:12s} "
                              f"montant={t['montant']} {t['devise']} cmd_ref={t['command_ref']} "
                              f"kopar_token={str(t['kopar_token'])[:10]}... cotisation_mois/annee={mois_tx}/{annee_tx} "
                              f"webhook={t['last_webhook_received_at']}")

                    # 3) Cotisations mensuelles
                    cur.execute("""
                    SELECT id, adhesion_id, annee, mois, montant, statut, paiement_date, mode_paiement, reference_paiement, created_at, updated_at
                    FROM cotisations_mensuelles WHERE adhesion_id = %s
                    ORDER BY annee DESC, mois DESC
                    """, (adhesion_id,))
                    cots = cur.fetchall()
                    print(f"\n   COTISATIONS MENSUELLES ({len(cots)}) :")
                    if not cots:
                        print("     (aucune ligne)")
                    for c in cots:
                        flag_cur = " [MOIS COURANT]" if c["annee"] == annee_courant and c["mois"] == mois_courant else ""
                        print(f"     - {c['annee']}/{c['mois']:02d} montant={c['montant']} statut={c['statut']:12s} "
                              f"ref={c['reference_paiement']} date_paie={c['paiement_date']}{flag_cur}")

                    # 4) Somme TOTAL transactions success adhesion_type + cotisation_type
                    cur.execute("""
                    SELECT type_transaction, COALESCE(SUM(montant),0) AS somme, COUNT(*) AS n
                    FROM transactions_kopar
                    WHERE (adhesion_id = %s OR EXISTS (SELECT 1 FROM cotisations_mensuelles cm WHERE cm.adhesion_id=%s AND cm.id=transactions_kopar.cotisation_id))
                      AND statut = 'success'
                    GROUP BY type_transaction
                    """, (adhesion_id, adhesion_id))
                    sums = cur.fetchall()
                    print(f"\n   SOMME TRANSACTIONS SUCCESS :")
                    s_adhesion = 0
                    s_cotisation = 0
                    for s in sums:
                        print(f"     - type {s['type_transaction']} : {s['somme']} FCFA ({s['n']} tx)")
                        if s["type_transaction"] == "adhesion":
                            s_adhesion = s["somme"]
                        if s["type_transaction"] == "cotisation":
                            s_cotisation = s["somme"]
                    print(f"\n   COMPARAISON montant_ref adhesion = {u['adhesion_montant']} FCFA vs somme_tx_success_adhesion = {s_adhesion} :")
                    print(f"     -> T1 dynamique calc 'paiementAdhesionConfirme' = {bool(u['adhesion_paiement_confirme'] or u['adhesion_reference_paiement'] or s_adhesion >= (u['adhesion_montant'] or 0))}")
                    cur.execute("""
                    SELECT id, annee, mois, statut, montant FROM cotisations_mensuelles
                    WHERE adhesion_id = %s AND annee = %s AND mois = %s
                    """, (adhesion_id, annee_courant, mois_courant))
                    cc = cur.fetchone()
                    if cc:
                        print(f"\n   COTISATION MOIS COURANT {annee_courant}/{mois_courant:02d} : statut={cc['statut']} montant={cc['montant']} id={cc['id']}")
                        cur.execute("""
                        SELECT COALESCE(SUM(montant),0) AS somme_cot_success, COUNT(*) AS n_cot_success
                        FROM transactions_kopar WHERE statut = 'success' AND type_transaction='cotisation'
                          AND (cotisation_id = %s OR EXISTS (SELECT 1 FROM cotisations_mensuelles cm2 WHERE cm2.adhesion_id=%s AND cm2.id=transactions_kopar.cotisation_id AND cm2.annee=%s AND cm2.mois=%s))
                        """, (cc["id"], adhesion_id, annee_courant, mois_courant))
                        succ = cur.fetchone()
                        print(f"     -> transactions success type=cotisation pour ce mois-ci : somme={succ['somme_cot_success']} n={succ['n_cot_success']}")
                    else:
                        print(f"\n   ⚠️ AUCUNE cotisation_mensuelle ligne pour {annee_courant}/{mois_courant:02d} adhesion_id={adhesion_id}. (attendue creation via endpoint qr-paiement-direct ou cron 1er du mois).")

            print("\n" + "=" * 110)
            print("FIN VERIFICATION")
            print("=" * 110)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERREUR :", type(e).__name__, e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
