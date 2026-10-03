from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.cli import reconcile_kopar_pending_transactions as reconcile
from app.core.settings import get_settings
from app.models.adhesion import Adhesion
from app.models.enums import PaymentMode
from app.models.paiements import (
    CotisationMensuelle,
    CotisationStatut,
    StatutTransactionKopar,
    TransactionKopar,
    TypeTransactionKopar,
)
from app.services.kopar import KoparTransactionDetail
from app.services.paiement_orchestrator import PaiementOrchestratorService

ANCIEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _fake_kopar(monkeypatch, statuts: dict[str, StatutTransactionKopar | Exception]):
    """Remplace l'appel Kopar GET /transaction/{token} par des réponses prédéfinies."""

    class FakeClient:
        async def get_transaction_detail(self, token):
            r = statuts[token]
            if isinstance(r, Exception):
                raise r
            return KoparTransactionDetail(token=token, kopar_id=None, statut=r, montant=0, devise="XOF", service="wave", data={})

    monkeypatch.setattr(reconcile, "KoparClient", FakeClient)


async def _adhesion(db) -> Adhesion:
    a = Adhesion(
        nom="Doe", prenom="John", date_naissance=date(1990, 1, 1), lieu_naissance="Dakar",
        profession="Dev", tel_mobile="770000000", email=f"{uuid.uuid4().hex[:8]}@example.com",
        cni=uuid.uuid4().hex[:10], fonction_professionnelle="Ing", engagement=["politique"],
        commissariat="Com 1", mode_paiement=PaymentMode.kopar_pay,
    )
    db.add(a)
    await db.flush()
    return a


async def _tx_cotisation(db, adhesion, *, token, periode, annee, mois, avec_ancrage=True, statut=StatutTransactionKopar.new):
    cot_id = None
    if avec_ancrage:
        c = CotisationMensuelle(adhesion_id=adhesion.id, annee=annee, mois=mois, montant=1000, statut=CotisationStatut.en_attente)
        db.add(c)
        await db.flush()
        cot_id = c.id
    tx = TransactionKopar(
        kopar_token=token, type_transaction=TypeTransactionKopar.cotisation, adhesion_id=adhesion.id,
        cotisation_id=cot_id, periode_mois=periode, premiere_annee_couverte=annee, premier_mois_couverte=mois,
        command_ref=f"COT-{token}", command_name="Cotisation", montant=1000 * periode, statut=statut, created_at=ANCIEN,
    )
    db.add(tx)
    await db.commit()
    return tx


async def _mois_payes(db, adhesion_id) -> list[str]:
    db.expire_all()
    rows = (await db.execute(
        select(CotisationMensuelle).where(CotisationMensuelle.adhesion_id == adhesion_id, CotisationMensuelle.statut == CotisationStatut.payee)
    )).scalars().all()
    return sorted(f"{c.annee}-{c.mois:02d}" for c in rows)


async def test_rattrapage_trimestriel_marque_3_mois_et_envoie_email(app, db_session, monkeypatch):
    os.environ["MAIL_ENABLED"] = "true"
    get_settings.cache_clear()
    emails: list[dict] = []
    monkeypatch.setattr("app.services.paiement_orchestrator.send_email_best_effort", lambda **kw: emails.append(kw))

    a = await _adhesion(db_session)
    email = a.email
    tx = await _tx_cotisation(db_session, a, token="T3", periode=3, annee=2026, mois=11)
    _fake_kopar(monkeypatch, {"T3": StatutTransactionKopar.success})

    assert await reconcile._reconcile_one_tour(dry_run=False, older_minutes_override=0) == (1, 1, 0, 0)
    assert await _mois_payes(db_session, a.id) == ["2026-11", "2026-12", "2027-01"]
    await db_session.refresh(tx)
    assert tx.statut == StatutTransactionKopar.success
    assert len(emails) == 1 and emails[0]["to"] == email

    # Second passage : plus rien à faire, aucun email en double
    assert await reconcile._reconcile_one_tour(dry_run=False, older_minutes_override=0) == (0, 0, 0, 0)
    assert len(emails) == 1


async def test_rattrapage_annuel_sans_ligne_ancrage(app, db_session, monkeypatch):
    a = await _adhesion(db_session)
    await _tx_cotisation(db_session, a, token="T12", periode=12, annee=2026, mois=11, avec_ancrage=False)
    _fake_kopar(monkeypatch, {"T12": StatutTransactionKopar.success})

    assert await reconcile._reconcile_one_tour(dry_run=False, older_minutes_override=0) == (1, 1, 0, 0)
    mois = await _mois_payes(db_session, a.id)
    assert len(mois) == 12 and mois[0] == "2026-11" and mois[-1] == "2027-10"


async def test_une_erreur_ne_bloque_pas_les_autres(app, db_session, monkeypatch):
    a = await _adhesion(db_session)
    await _tx_cotisation(db_session, a, token="KO", periode=1, annee=2026, mois=10)
    await _tx_cotisation(db_session, a, token="OK6", periode=6, annee=2027, mois=1)
    _fake_kopar(monkeypatch, {"KO": RuntimeError("Kopar down"), "OK6": StatutTransactionKopar.success})

    assert await reconcile._reconcile_one_tour(dry_run=False, older_minutes_override=0) == (2, 1, 0, 1)
    assert await _mois_payes(db_session, a.id) == ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"]


async def test_dry_run_ne_modifie_rien(app, db_session, monkeypatch):
    a = await _adhesion(db_session)
    tx = await _tx_cotisation(db_session, a, token="DRY", periode=3, annee=2026, mois=10)
    _fake_kopar(monkeypatch, {"DRY": StatutTransactionKopar.success})

    assert await reconcile._reconcile_one_tour(dry_run=True, older_minutes_override=0) == (1, 1, 0, 0)
    assert await _mois_payes(db_session, a.id) == []
    await db_session.refresh(tx)
    assert tx.statut == StatutTransactionKopar.new


async def test_statut_final_protege(app, db_session):
    a = await _adhesion(db_session)
    tx = await _tx_cotisation(db_session, a, token="FIN", periode=1, annee=2026, mois=10)
    orch = PaiementOrchestratorService(db_session)

    # échec puis succès (ex: timeout Orange Money puis paiement abouti) : le succès l'emporte
    assert await orch.appliquer_statut_kopar(tx.id, StatutTransactionKopar.failed, body={}) == "statut_failed"
    action = await orch.appliquer_statut_kopar(tx.id, StatutTransactionKopar.success, body={})
    assert action == "cotisation_confirmee:2026-10"
    # webhooks en retard : ne rétrogradent pas un succès, et ne remarquent rien
    assert (await orch.appliquer_statut_kopar(tx.id, StatutTransactionKopar.pending, body={})).startswith("ignore_")
    assert (await orch.appliquer_statut_kopar(tx.id, StatutTransactionKopar.failed, body={})).startswith("ignore_")
    assert await orch.appliquer_statut_kopar(tx.id, StatutTransactionKopar.success, body={}) == "cotisation_deja_payee_ou_introuvable"
    await db_session.commit()
    await db_session.refresh(tx)
    assert tx.statut == StatutTransactionKopar.success
