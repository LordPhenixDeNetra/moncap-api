from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.settings import get_settings
from app.models.adhesion import Adhesion
from app.models.email_otp import EmailOtp
from app.services.email_otp import _hash
from app.models.geo import Commune, Departement, Region


async def _seed_geo(db_session):
    r1 = Region(id=uuid.uuid4(), nom="Region 1")
    r2 = Region(id=uuid.uuid4(), nom="Region 2")
    d1 = Departement(id=uuid.uuid4(), region_id=r1.id, nom="Dep 1")
    c1 = Commune(id=uuid.uuid4(), departement_id=d1.id, nom="Com 1")
    db_session.add_all([r1, r2, d1, c1])
    # Code OTP valide pour l'email du payload (cf. _payload["email_otp"])
    now = datetime.now(timezone.utc)
    db_session.add(EmailOtp(email="john@example.com", code_hash=_hash("john@example.com", "123456"),
                            expires_at=now + timedelta(minutes=10), sent_at=now, attempts=0))
    await db_session.commit()
    return r1, r2, d1, c1


def _files():
    return [
        ("photo_recto", ("photo-recto.jpg", b"fake-photo-recto", "image/jpeg")),
        ("photo_verso", ("photo-verso.jpg", b"fake-photo-verso", "image/jpeg")),
        ("cv", ("cv.pdf", b"fake-cv", "application/pdf")),
        ("diplome", ("diplome.pdf", b"fake-diplome", "application/pdf")),
    ]


def _files_legacy_recto():
    return [
        ("photo", ("photo.jpg", b"fake-photo", "image/jpeg")),
        ("photo_verso", ("photo-verso.jpg", b"fake-photo-verso", "image/jpeg")),
        ("cv", ("cv.pdf", b"fake-cv", "application/pdf")),
        ("diplome", ("diplome.pdf", b"fake-diplome", "application/pdf")),
    ]


def _payload(*, region_id, departement_id, commune_id, region2_id=None):
    return {
        "nom": "Doe",
        "prenom": "John",
        "date_naissance": str(date(1990, 1, 1)),
        "lieu_naissance": "Dakar",
        "profession": "Dev",
        "tel_mobile": "770000000",
        "email": "john@example.com",
        "email_otp": "123456",
        "cni": "CNI123",
        "region_domicile_id": str(region_id if region2_id is None else region2_id),
        "departement_domicile_id": str(departement_id),
        "commune_domicile_id": str(commune_id),
        "region_militantisme_id": str(region_id),
        "departement_militantisme_id": str(departement_id),
        "commune_militantisme_id": str(commune_id),
        "fonction_professionnelle": "Ingénieur",
        "engagement": "politique",
        "commissariat": "Com 1",
        "mode_paiement": "wave",
        "montant_adhesion": "25000",
        "certification": "true",
    }


async def test_post_adhesion_idempotency(client, db_session):
    r1, _, d1, c1 = await _seed_geo(db_session)

    headers = {"Idempotency-Key": "k1"}
    r = await client.post("/api/v1/adhesions", data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id), files=_files(), headers=headers)
    assert r.status_code == 200
    adhesion_id = r.json()["data"]["id"]

    r2 = await client.post("/api/v1/adhesions", data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id), files=_files(), headers=headers)
    assert r2.status_code == 200
    assert r2.json()["data"]["id"] == adhesion_id

    count = (await db_session.execute(select(func.count()).select_from(Adhesion))).scalar_one()
    assert int(count) == 1

    p = _payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id)
    p["prenom"] = "Jane"
    r3 = await client.post("/api/v1/adhesions", data=p, files=_files(), headers=headers)
    assert r3.status_code == 409


async def test_post_adhesion_legacy_photo_alias(client, db_session):
    r1, _, d1, c1 = await _seed_geo(db_session)

    r = await client.post(
        "/api/v1/adhesions",
        data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id),
        files=_files_legacy_recto(),
    )
    assert r.status_code == 200


async def test_post_adhesion_diplome_sans_recto_verso(client, db_session):
    r1, _, d1, c1 = await _seed_geo(db_session)

    r = await client.post(
        "/api/v1/adhesions",
        data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id),
        files=[
            ("cv", ("cv.pdf", b"fake-cv", "application/pdf")),
            ("diplome", ("diplome.pdf", b"fake-diplome", "application/pdf")),
        ],
    )
    assert r.status_code == 200

    a = (await db_session.execute(select(Adhesion))).scalar_one()
    assert a.diplome_url and "diplomes/" in a.diplome_url
    assert a.photo_recto_url is None and a.photo_verso_url is None


async def test_post_adhesion_sans_diplome_refuse(client, db_session):
    r1, _, d1, c1 = await _seed_geo(db_session)

    r = await client.post(
        "/api/v1/adhesions",
        data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id),
        files=[("cv", ("cv.pdf", b"fake-cv", "application/pdf"))],
    )
    assert r.status_code == 400
    assert "diplome" in r.text


async def test_post_adhesion_geo_coherence(client, db_session):
    r1, r2, d1, c1 = await _seed_geo(db_session)

    r = await client.post(
        "/api/v1/adhesions",
        data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id, region2_id=r2.id),
        files=_files(),
    )
    assert r.status_code == 400


async def test_post_adhesion_triggers_email_when_enabled(client, db_session, monkeypatch):
    r1, _, d1, c1 = await _seed_geo(db_session)

    os.environ["MAIL_ENABLED"] = "true"
    get_settings.cache_clear()

    calls: list[dict] = []

    def fake_send_email_best_effort(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.api.v1.routes.adhesions.send_email_best_effort", fake_send_email_best_effort)

    r = await client.post(
        "/api/v1/adhesions",
        data=_payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id),
        files=_files(),
    )
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["to"] == "john@example.com"


class _FakeMailer:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, **kwargs):
        self.sent.append(kwargs)


async def test_email_otp_flow(client, db_session, monkeypatch):
    r1, _, d1, c1 = await _seed_geo(db_session)
    await db_session.delete(await db_session.get(EmailOtp, "john@example.com"))
    await db_session.commit()

    mailer = _FakeMailer()
    monkeypatch.setattr("app.services.email_otp._build_mailer", lambda _settings: mailer)

    r = await client.post("/api/v1/adhesions/email-otp", json={"email": "John@Example.com"})
    assert r.status_code == 200
    assert mailer.sent[0]["to"] == "john@example.com"
    code = next(w for w in mailer.sent[0]["text"].split() if w.isdigit() and len(w) == 6)

    r = await client.post("/api/v1/adhesions/email-otp", json={"email": "john@example.com"})
    assert r.status_code == 429

    wrong = "000000" if code != "000000" else "111111"
    r = await client.post("/api/v1/adhesions/verify-email-otp", json={"email": "john@example.com", "otp": wrong})
    assert r.status_code == 400 and "OTP_INVALID" in r.text
    for _ in range(2):  # vérifiable plusieurs fois sans être consommé
        r = await client.post("/api/v1/adhesions/verify-email-otp", json={"email": "john@example.com", "otp": code})
        assert r.status_code == 200 and r.json() == {"data": {"valid": True}}

    p = _payload(region_id=r1.id, departement_id=d1.id, commune_id=c1.id)
    p["email_otp"] = wrong
    r = await client.post("/api/v1/adhesions", data=p, files=_files())
    assert r.status_code == 400 and "OTP_INVALID" in r.text

    p["email_otp"] = code
    r = await client.post("/api/v1/adhesions", data=p, files=_files())
    assert r.status_code == 200

    db_session.expire_all()
    assert await db_session.get(EmailOtp, "john@example.com") is None

    r = await client.post("/api/v1/adhesions/email-otp", json={"email": "john@example.com"})
    assert r.status_code == 409
