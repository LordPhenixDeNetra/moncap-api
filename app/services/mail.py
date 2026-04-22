from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.settings import Settings, get_settings


@dataclass(frozen=True)
class SmtpMailer:
    host: str
    port: int
    username: str | None
    password: str | None
    use_tls: bool
    use_ssl: bool
    mail_from: str
    mail_from_name: str

    def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        msg = EmailMessage()
        if self.mail_from_name:
            msg["From"] = f"{self.mail_from_name} <{self.mail_from}>"
        else:
            msg["From"] = self.mail_from
        msg["To"] = to
        msg["Subject"] = subject

        msg.set_content(text or "")
        if html:
            msg.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        if self.use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=20)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=20)

        try:
            if not self.use_ssl:
                server.ehlo()
                if self.use_tls:
                    server.starttls(context=context)
                    server.ehlo()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass


def _build_mailer(settings: Settings) -> SmtpMailer | None:
    if not settings.mail_enabled:
        return None
    if not settings.smtp_host or not settings.mail_from:
        return None
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        use_ssl=settings.smtp_use_ssl,
        mail_from=settings.mail_from,
        mail_from_name=settings.mail_from_name,
    )


def send_email_best_effort(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    settings: Settings | None = None,
) -> None:
    s = settings or get_settings()
    mailer = _build_mailer(s)
    if not mailer:
        return
    try:
        mailer.send(to=to, subject=subject, text=text, html=html)
    except Exception:
        return

