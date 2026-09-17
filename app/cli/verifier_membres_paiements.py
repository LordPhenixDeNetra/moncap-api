"""Vérification rapide données membres emails ramand@gmail.com, ousmane@gmail.com
(adhésion payée + cotisation du mois + transactions Kopar).
Usage:
    python -m app.cli.verifier_membres_paiements
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.adhesion import Adhesion
from app.models.paiements import TransactionKopar, CotisationMensuelle
from sqlalchemy import select, or_, func, and_


async def async_main():
    emails = ["ramand@gmail.com", "ousmane@gmail.com"]
    today = date.today()
    mois_courant = today.month
    annee_courant = today.year

    print("=" * 110)
    print(f"VERIFICATION DONNEES {emails} — {today}")
    print("=" * 110)

    async with AsyncSessionLocal() as db:
        placeholders = ", ".join(["lower(:e%d)" % i for i in range(len(emails))])
        binds = {f"e{i}": em for i, em in enumerate(emails)}
        where_clause = or_(
            func.lower(User.email).in_([e.lower() for e in emails]),
            func.lower(Adhesion.email).in_([e.lower() for e in emails]),
        )

        q_users = (
            select(
                User.id.label("user_id"),
                User.email.label("user_email"),
                User.nom.label("user_nom"),
                User.prenom.label("user_prenom"),
                User.adhesion_id.label("user_adhesion_id"),
                Adhesion.id.label("adhesion_id"),
                Adhesion.statut.label("adhesion_statut"),
                Adhesion.paiement_confirme.label("adhesion_paiement_confirme"),
                Adhesion.reference_paiement.label("adhesion_reference_paiement"),
                Adhesion.montant_adhesion.label("adhesion_montant"),
                Adhesion.created_at.label("adhesion_created_at"),
                Adhesion.nom.label("adhesion_nom"),
                Adhesion.prenom.label("adhesion_prenom"),
                Adhesion.email.label("adhesion_email"),
            )
            .select_from(User)
            .join(Adhesion, User.adhesion_id == Adhesion.id, isouter=True)
            .where(where_clause)
        )
        users_rows = (await db.execute(q_users)).mappings().all()
        if not users_rows:
            # Fallback search on adhesions email only
            arows = (await db.execute(
                select(
                    Adhesion.id.label("adhesion_id"),
                    Adhesion.email.label("adhesion_email"),
                    Adhesion.nom.label("adhesion_nom"),
                    Adhesion.prenom.label("adhesion_prenom"),
                    Adhesion.statut.label("adhesion_statut"),
                    Adhesion.paiement_confirme.label("adhesion_paiement_confirme"),
                    Adhesion.reference_paiement.label("adhesion_reference_paiement"),
                    Adhesion.montant_adhesion.label("adhesion_montant"),
                ).where(func.lower(Adhesion.email).in_([e.lower() for e in emails]))
            )).mappings().all()
            for r in arows:
                print(dict(r))
            return

        for u in users_rows:
            email = u["user_email"] or u["adhesion_email"]
            print("\n" + "#" * 100)
            print(f"MEMBRE email={email} user_id={u['user_id']} adhesion_id={u['adhesion_id']}")
            print(f"   USER  nom/prenom   : {u.get('user_nom')} {u.get('user_prenom')}")
            print(f"   ADH   nom/prenom   : {u.get('adhesion_nom')} {u.get('adhesion_prenom')} (email fiche: {u.get('adhesion_email')})")
            print(f"   ADH   statut       : {u['adhesion_statut']}")
            print(f"   ADH   paiement_confirme : {u['adhesion_paiement_confirme']}")
            print(f"   ADH   reference_paiement: {u['adhesion_reference_paiement']}")
            print(f"   ADH   montant adhesion   : {u['adhesion_montant']} FCFA")
            adhesion_id = u["adhesion_id"]
            if not adhesion_id:
                print("   (pas d'adhesion liee, skip)")
                continue

            # 2) Transactions Kopar
            stmt = (
                select(TransactionKopar)
                .where(or_(
                    TransactionKopar.adhesion_id == adhesion_id,
                    TransactionKopar.cotisation_id.in_(
                        select(CotisationMensuelle.id).where(CotisationMensuelle.adhesion_id == adhesion_id).scalar_subquery()
                    ),
                ))
                .order_by(TransactionKopar.created_at.desc())
            )
            txs = (await db.execute(stmt)).scalars().all()
            print(f"\n   TRANSACTIONS KOPAR ({len(txs)}) :")
            for t in txs:
                cf = t.custom_fields
                cfs = (cf if isinstance(cf, dict) else {})
                mois_tx = cfs.get("mois") if cfs else None
                annee_tx = cfs.get("annee") if cfs else None
                print(f"     - [{t.created_at}] id={str(t.id)[:10]}... type={t.type_transaction.value:12s} statut={t.statut.value:12s} "
                      f"montant={t.montant} {t.devise.value if hasattr(t.devise,'value') else t.devise} cmd_ref={t.command_ref} "
                      f"kopar_token={str(t.kopar_token)[:10]}... cotisation_mois/annee={mois_tx}/{annee_tx} "
                      f"webhook={t.last_webhook_received_at}")

            stmt = (
                select(CotisationMensuelle)
                .where(CotisationMensuelle.adhesion_id == adhesion_id)
                .order_by(CotisationMensuelle.annee.desc(), CotisationMensuelle.mois.desc())
            )
            cots = (await db.execute(stmt)).scalars().all()
            print(f"\n   COTISATIONS MENSUELLES ({len(cots)}) :")
            if not cots:
                print("     (aucune ligne)")
            for c in cots:
                flag_cur = " [MOIS COURANT]" if (c.annee == annee_courant and c.mois == mois_courant) else ""
                print(f"     - {c.annee}/{c.mois:02d} montant={c.montant} statut={c.statut.value:12s} "
                      f"ref={c.reference_paiement} date_paie={c.paiement_date}{flag_cur}")

            # 4) Somme TOTAL
            stmt = (
                select(TransactionKopar.type_transaction,
                       func.coalesce(func.sum(TransactionKopar.montant), 0).label("somme"),
                       func.count(TransactionKopar.id).label("n"))
                .where(and_(
                    or_(TransactionKopar.adhesion_id == adhesion_id,
                        TransactionKopar.cotisation_id.in_(
                            select(CotisationMensuelle.id).where(CotisationMensuelle.adhesion_id == adhesion_id).scalar_subquery()
                        )),
                    TransactionKopar.statut == "success",
                ))
                .group_by(TransactionKopar.type_transaction)
            )
            sums = (await db.execute(stmt)).mappings().all()
            print(f"\n   SOMME TRANSACTIONS SUCCESS :")
            s_adhesion = 0
            s_cotisation = 0
            for s in sums:
                ttype = s["type_transaction"].value if hasattr(s["type_transaction"], "value") else s["type_transaction"]
                print(f"     - type {ttype} : {s['somme']} FCFA ({s['n']} tx)")
                if ttype == "adhesion":
                    s_adhesion = float(s["somme"])
                if ttype == "cotisation":
                    s_cotisation = float(s["somme"])
            montant_adh = float(u["adhesion_montant"] or 0)
            print(f"\n   COMPARAISON montant_ref adhesion = {montant_adh} FCFA vs somme_tx_success_adhesion = {s_adhesion} :")
            print(f"     -> T1 calc dynamique paiementAdhesionConfirme = {bool(u['adhesion_paiement_confirme'] or u['adhesion_reference_paiement'] or s_adhesion >= montant_adh)}")

            cur_cot_stmt = select(CotisationMensuelle).where(and_(CotisationMensuelle.adhesion_id == adhesion_id, CotisationMensuelle.annee == annee_courant, CotisationMensuelle.mois == mois_courant))
            cc = (await db.execute(cur_cot_stmt)).scalar_one_or_none()
            if cc:
                print(f"\n   COTISATION MOIS COURANT {annee_courant}/{mois_courant:02d} : statut={cc.statut.value} montant={cc.montant} id={cc.id}")
                succ_stmt = (
                    select(func.coalesce(func.sum(TransactionKopar.montant), 0).label("somme_cot_success"),
                           func.count(TransactionKopar.id).label("n_cot_success"))
                    .where(and_(
                        TransactionKopar.statut == "success",
                        TransactionKopar.type_transaction == "cotisation",
                        TransactionKopar.cotisation_id == cc.id,
                    ))
                )
                succ = (await db.execute(succ_stmt)).mappings().first()
                print(f"     -> transactions success type=cotisation pour ce mois-ci : somme={succ['somme_cot_success']} n={succ['n_cot_success']}")
            else:
                print(f"\n   [WARNING] AUCUNE cotisation_mensuelle ligne pour {annee_courant}/{mois_courant:02d} adhesion_id={adhesion_id}.")

        print("\n" + "=" * 110)
        print("FIN VERIFICATION")
        print("=" * 110)


def main():
    try:
        asyncio.run(async_main())
    except Exception as e:
        print("ERREUR :", type(e).__name__, e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
