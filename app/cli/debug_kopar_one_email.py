"""Debug ciblé 1 email : Affiche l'état des paiements + appelle Kopar GET /transaction/{token}
pour TOUTES transactions Kopar (meme success/failed)."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from app.core.settings import get_settings
from app.db.session import AsyncSessionLocal
from app.models.paiements import TransactionKopar, StatutTransactionKopar, TypeTransactionKopar
from app.services.kopar import KoparClient
from sqlalchemy import select, or_


EMAIL = sys.argv[1] if len(sys.argv) > 1 else "ramand@gmail.com"


async def main():
    today = date.today()
    s = get_settings()
    print(f"DEBUG KOPAR pour email={EMAIL}")
    print(f"Backend base (from .env backend_public_base_url): {getattr(s, 'backend_public_base_url', 'NOT SET')}")
    async with AsyncSessionLocal() as db:
        # 1) Recupere adhésion via email users / adhesions
        from app.models.user import User
        from app.models.adhesion import Adhesion
        from sqlalchemy import or_
        from sqlalchemy import func

        row_u = (await db.execute(
            select(User.id, User.email, User.nom, User.prenom, User.adhesion_id)
            .where(func.lower(User.email) == EMAIL.lower())
        )).fetchone()
        adhesion_id = None
        if row_u:
            print(f"USER: {row_u}")
            adhesion_id = row_u.adhesion_id
        if not adhesion_id:
            row_a = (await db.execute(
                select(Adhesion.id, Adhesion.email, Adhesion.nom, Adhesion.prenom, Adhesion.statut, Adhesion.paiement_confirme, Adhesion.reference_paiement, Adhesion.montant_adhesion)
                .where(func.lower(Adhesion.email) == EMAIL.lower())
            )).fetchone()
            if row_a:
                print(f"ADHESION(email): {dict(row_a._mapping)}")
                adhesion_id = row_a.id
            else:
                print("Pas trouvé adhesion ni user avec email", EMAIL)
                return
        print(f"adhesion_id = {adhesion_id}")
        adhesion = await db.get(Adhesion, adhesion_id)
        if adhesion:
            print(f"ADH statut={adhesion.statut} confirme={adhesion.paiement_confirme} ref={adhesion.reference_paiement} montant={adhesion.montant_adhesion}")

        # 2) TOUTES transactions_kopar liees a cette adhesion + toutes cotisations mensuelles
        from app.models.paiements import CotisationMensuelle
        cots = (await db.execute(
            select(CotisationMensuelle).where(CotisationMensuelle.adhesion_id == adhesion_id)
            .order_by(CotisationMensuelle.annee.desc(), CotisationMensuelle.mois.desc())
        )).scalars().all()
        print(f"\nCOTISATIONS ({len(cots)}) :")
        for c in cots:
            flag_cur = " [MOIS COURANT]" if (c.annee == today.year and c.mois == today.month) else ""
            print(f"  - {c.annee}/{c.mois:02d} montant={c.montant} statut={c.statut} "
                  f"date={c.paiement_date} ref={c.reference_paiement} id={c.id}{flag_cur}")

        # 3) Transactions Kopar ALL (any statut)
        txs = (await db.execute(
            select(TransactionKopar)
            .where(or_(
                TransactionKopar.adhesion_id == adhesion_id,
                TransactionKopar.cotisation_id.in_([c.id for c in cots])
            ))
            .order_by(TransactionKopar.created_at.desc())
        )).scalars().all()
        print(f"\nTRANSACTIONS KOPAR TOUS STATUTS ({len(txs)}) :")
        client = KoparClient()
        for t in txs:
            print(f"\n  [{t.created_at}] id={t.id} type={t.type_transaction} statut={t.statut} "
                  f"montant={t.montant}{t.devise} ref={t.command_ref} kopar_token={t.kopar_token}")
            token = str(t.kopar_token or "").strip()
            # APPEL KOPAR VERITE
            if token:
                try:
                    ks = await client.get_transaction_detail(token)
                    print(f"       Kopar verif statut : {ks.statut.value}  montant={ks.montant}{ks.devise} service={ks.service}")
                    d = ks.data or {}
                    inner = d.get("data") if isinstance(d.get("data"), dict) else d
                    for k in ["status", "errorCode", "code", "refunded", "success", "message", "createdAt", "updatedAt", "paidAt", "expireAt"]:
                        if k in inner:
                            print(f"          {k}: {inner.get(k)}")
                except Exception as e:
                    print(f"       Kopar verif ERREUR: {type(e).__name__}: {e!r}")


if __name__ == "__main__":
    asyncio.run(main())
