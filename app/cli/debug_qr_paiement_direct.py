"""Reproduit exactement le flux GET /qr-paiement-direct et log full stacktrace.
Usage (Alwaysdata SSH) :
    source venv/bin/activate
    python -m app.cli.debug_qr_paiement_direct
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
import traceback

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("debug_qr")


async def main():
    from datetime import date
    from app.core.settings import get_settings
    from app.db.session import AsyncSessionLocal
    from app.models.enums import AdhesionStatus
    from app.models.paiements import CotisationStatut, ParametrePaiementCode, StatutTransactionKopar, TypeTransactionKopar
    from app.repositories.adhesions import AdhesionRepository
    from app.repositories.paiements import CotisationMensuelleRepository, TransactionKoparRepository
    from app.services.kopar import KoparError
    from app.services.paiement_orchestrator import PaiementOrchestratorService
    from app.services.paiements import CotisationsService, ParametresPaiementService
    from fastapi import HTTPException

    adh_str = sys.argv[1] if len(sys.argv) > 1 else "627f0d86-9b80-479e-8994-df347dae6517"
    try:
        adh_uuid = uuid.UUID(adh_str)
    except Exception:
        print("usage: debug_qr_paiement_direct UUID_ADHESION")
        sys.exit(1)

    def _statut_est_payee(cotisation):
        s = getattr(cotisation, "statut", None)
        return (
            s == CotisationStatut.payee
            or (hasattr(s, "value") and s.value == "payee")
            or str(s) == "payee"
        )

    async def _calculer_paiement_adhesion_confirme(adhesion, db, montant_ref=None):
        flag_bd = bool(getattr(adhesion, "paiement_confirme", False))
        has_ref = getattr(adhesion, "reference_paiement", None) and len(str(getattr(adhesion, "reference_paiement", "") or "").strip()) > 0
        somme = 0
        try:
            tx_repo = TransactionKoparRepository(db)
            somme = await tx_repo.sommer_montants(
                statut=StatutTransactionKopar.success,
                type_transaction=TypeTransactionKopar.adhesion,
                adhesion_id=uuid.UUID(str(getattr(adhesion, "id"))),
            )
        except Exception:
            somme = 0
        if somme <= 0:
            return bool(flag_bd or has_ref)
        if not montant_ref or montant_ref <= 0:
            try:
                ps = ParametresPaiementService(db)
                montant_ref = await ps.get_montant(ParametrePaiementCode.adhesion_initiale, date.today())
            except Exception:
                montant_ref = getattr(adhesion, "montant_adhesion", None) or 1
        return int(somme) >= int(montant_ref)

    settings = get_settings()
    async with AsyncSessionLocal() as db:
        adhesion = await AdhesionRepository(db).get_by_id(adh_uuid)
        if adhesion is None:
            print("ADHESION INTROUVABLE")
            return
        print(f"ADHESION TROUVEE id={adhesion.id} nom={adhesion.nom} {adhesion.prenom} statut={adhesion.statut} paiement_confirme={adhesion.paiement_confirme}")
        today = date.today()
        try:
            annee_num = today.year
            mois_num = today.month
            svc_cot = CotisationsService(db)
            cc = await svc_cot.creer_cotisation(adhesion.id, annee_num, mois_num)
            print(f"CREER_COTISATION retour: {type(cc).__name__} repr={cc!r}")
            try:
                params_svc = ParametresPaiementService(db)
                montant_ref = await params_svc.get_montant(ParametrePaiementCode.cotisation_mensuelle, date(annee_num, mois_num, 1))
                if montant_ref and montant_ref > 0:
                    cc.montant = montant_ref
            except Exception as e:
                logger.exception("parametres get_montant exc %r", e)
                cc.montant = settings.default_cotisation_mensuelle_fcfa or 5
            print(f"COTISATION id={getattr(cc, 'id', None)} mois={getattr(cc, 'mois', None)} montant={getattr(cc, 'montant', None)} statut={getattr(cc, 'statut', None)}")
            await db.commit()
            if _statut_est_payee(cc):
                print("COTISATION DEJA PAYEE")
                return
            orchestrator = PaiementOrchestratorService(db)
            initie = await orchestrator.initier_paiement_cotisation(cc.id, force=False, service=None)
            print(f"INITIE OK token={getattr(initie, 'token', None)} payment_url={getattr(initie, 'payment_url', None)[:120] if getattr(initie, 'payment_url', None) else None}")
        except HTTPException as e:
            print(f"HTTPException status={e.status_code} detail={e.detail}")
        except KoparError as e:
            print(f"KoparError: {e} ; kopar_error_code={e.kopar_error_code}")
        except Exception as e:
            print("=== EXCEPTION INATTENDUE ===")
            traceback.print_exc()
            print(f"type exception = {type(e).__name__}; message = {e!r}")


if __name__ == "__main__":
    asyncio.run(main())
