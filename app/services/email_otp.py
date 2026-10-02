from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.models.email_otp import EmailOtp
from app.services.mail import _build_mailer

OTP_TTL = timedelta(minutes=10)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_ATTEMPTS = 5


def _hash(email: str, code: str) -> str:
    key = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(key, f"{email}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite (tests) renvoie des datetimes naïfs
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "field": "email_otp", "message": message})


def _build_otp_mail(code: str) -> tuple[str, str, str]:
    minutes = int(OTP_TTL.total_seconds() // 60)
    subject = "MONCAP — Code de vérification de votre email"
    text = (
        "Bonjour,\n\n"
        f"Votre code de vérification est : {code}\n"
        f"Il est valable {minutes} minutes.\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
    )
    html = f"""
    <html>
      <body>
        <p>Bonjour,</p>
        <p>Votre code de vérification est :</p>
        <p style="font-size:24px;font-weight:bold;letter-spacing:4px">{code}</p>
        <p>Il est valable {minutes} minutes.</p>
        <p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


async def send_email_otp(session: AsyncSession, email: str) -> None:
    now = datetime.now(timezone.utc)
    row = await session.get(EmailOtp, email)
    if row and now - _aware(row.sent_at) < OTP_RESEND_COOLDOWN:
        raise HTTPException(
            status_code=429,
            detail={"code": "OTP_COOLDOWN", "field": "email", "message": "Patientez une minute avant de redemander un code"},
        )

    mailer = _build_mailer(get_settings())
    if not mailer:
        raise HTTPException(status_code=503, detail={"code": "MAIL_UNAVAILABLE", "message": "Envoi d'email indisponible"})

    code = f"{secrets.randbelow(1_000_000):06d}"
    subject, text, html = _build_otp_mail(code)
    try:
        await asyncio.to_thread(mailer.send, to=email, subject=subject, text=text, html=html)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={"code": "MAIL_SEND_FAILED", "field": "email", "message": "Impossible d'envoyer le code à cette adresse"},
        )

    if row is None:
        row = EmailOtp(email=email)
        session.add(row)
    row.code_hash = _hash(email, code)
    row.expires_at = now + OTP_TTL
    row.sent_at = now
    row.attempts = 0
    await session.commit()


async def verify_email_otp(session: AsyncSession, email: str, code: str) -> None:
    """Vérifie le code. En cas de succès, la ligne est supprimée mais NON commitée :
    la suppression part avec le commit de l'adhésion (le code reste valable si la création échoue)."""
    row = await session.get(EmailOtp, email)
    if row is None:
        raise _error(400, "OTP_NOT_FOUND", "Aucun code demandé pour cet email")
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        raise _error(400, "OTP_EXPIRED", "Code expiré, demandez-en un nouveau")
    if row.attempts >= OTP_MAX_ATTEMPTS:
        raise _error(429, "OTP_TOO_MANY_ATTEMPTS", "Trop d'essais, demandez un nouveau code")
    if not hmac.compare_digest(row.code_hash, _hash(email, (code or "").strip())):
        row.attempts += 1
        await session.commit()
        raise _error(400, "OTP_INVALID", "Code de vérification incorrect")
    await session.delete(row)
