from __future__ import annotations

from html import escape

from app.models.enums import DisabledReason

_REASON_LABELS: dict[str, str] = {
    DisabledReason.AUTOMATIQUE_3_MOIS.value: "3 mois impayés consécutifs",
    DisabledReason.MANUEL_ADMIN.value: "Décision administrative",
}


def _reason_label(rc: object | None) -> str:
    if rc is None:
        return ""
    s = rc.value if hasattr(rc, "value") else str(rc)
    return _REASON_LABELS.get(s, s)


def _adherent_fullname(adhesion) -> str:
    parts = [getattr(adhesion, "prenom", None), getattr(adhesion, "nom", None)]
    return " ".join(x for x in parts if x) or "Chère adhérente, Cher adhérent"


def _recipient_email(adhesion, user) -> str | None:
    candidates = [
        getattr(user, "email", None) if user is not None else None,
        getattr(adhesion, "email", None),
    ]
    for c in candidates:
        if c and c:
            return c
    return None


def resolve_recipient_email(*, adhesion, user):
    return _recipient_email(adhesion=adhesion, user=user)


def _format_mois_labels(mois_concernes) -> list[str]:
    # mois_concernes: Iterable[(annee:int, mois:int)] ou liste d'objets avec .annee/.mois
    out: list[str] = []
    for m in mois_concernes or []:
        a = 0
        mo = 0
        if isinstance(m, tuple) and len(m) == 2:
            a, mo = int(m[0]), int(m[1])
        else:
            a = int(getattr(m, "annee", 0))
            mo = int(getattr(m, "mois", 0))
        if not (a and mo):
            continue
        mois_noms = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
        ]
        nom = mois_noms[mo - 1] if 1 <= mo <= 12 else f"Mois {mo}"
        out.append(f"{nom} {a}")
    return out


def build_radiation_notification(
    *,
    adhesion,
    user,
    motif: str,
    reason_code,
    mois_concernes,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    """Email notifiant le membre que son adhésion a été radiée / son compte désactivé."""
    intro = f"Bonjour {_adherent_fullname(adhesion)},"
    subject = "[MONCAP] Radiation de votre adhésion et désactivation de votre compte"

    mois_labels = _format_mois_labels(mois_concernes)
    raison_label = _reason_label(reason_code)

    text_lines = [
        intro,
        "",
        "Nous vous informons par la présente de la radiation de votre adhésion et de la désactivation de votre compte sur l'espace MONCAP.",
        "",
    ]
    if raison_label:
        text_lines.append(f"Motif de la radiation : {raison_label}")
    if mois_labels:
        text_lines.append(f"Mois impayés concernés : {', '.join(mois_labels)}")
    if motif:
        text_lines.append(f"Détails : {motif}")
    text_lines += [
        "",
        "Vous ne pouvez plus vous connecter à votre espace membre ni accéder aux fonctionnalités réservées.",
        "",
    ]
    if base_url:
        text_lines.append(
            "Pour toute demande de réactivation, contactez l'administration via le site ou rendez-vous au commissariat le plus proche."
        )
        text_lines.append(f"Site MONCAP : {base_url}")
    else:
        text_lines.append(
            "Pour toute demande de réactivation, contactez l'administration ou rendez-vous au commissariat le plus proche."
        )
    text_lines += [
        "",
        "Bien à vous,",
        "L'équipe MONCAP.",
    ]
    text = "\n".join(text_lines) + "\n"

    mois_html = ""
    if mois_labels:
        mois_html = f"<li><strong>Mois impayés concernés</strong> : {escape(', '.join(mois_labels))}</li>"
    raison_html = (
        f"<li><strong>Motif de la radiation</strong> : {escape(raison_label)}</li>"
        if raison_label
        else ""
    )
    motif_html = f"<li><strong>Détails</strong> : {escape(motif)}</li>" if motif else ""
    contact_html = (
        f'<p>Pour toute demande de réactivation, contactez l\'administration via <a href="{base_url}">le site MONCAP</a> ou rendez-vous au commissariat le plus proche.</p>'
        if base_url
        else "<p>Pour toute demande de réactivation, contactez l'administration ou rendez-vous au commissariat le plus proche.</p>"
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>Nous vous informons par la présente de la radiation de votre adhésion et de la désactivation de votre compte sur l'espace MONCAP.</p>
        <ul>
          {raison_html}
          {mois_html}
          {motif_html}
        </ul>
        <p>Vous ne pouvez plus vous connecter à votre espace membre ni accéder aux fonctionnalités réservées.</p>
        {contact_html}
        <p>Bien à vous,<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_reactivation_notification(
    *,
    adhesion,
    user,
    motif_reactivation: str,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    """Email notifiant le membre que son adhésion a été réhabilitée / son compte réactivé."""
    intro = f"Bonjour {_adherent_fullname(adhesion)},"
    subject = "[MONCAP] Réactivation de votre compte et réhabilitation de votre adhésion"

    text_lines = [
        intro,
        "",
        "Bonne nouvelle : votre compte a été réactivé et votre adhésion a été réhabilitée au sein du mouvement MONCAP.",
        "",
    ]
    if motif_reactivation:
        text_lines.append(f"Motif indiqué par l'administration : {motif_reactivation}")
    text_lines.append(
        "Vous pouvez à nouveau vous connecter à votre espace membre avec vos identifiants habituels."
    )
    if base_url:
        text_lines += [
            "",
            f"Se connecter : {base_url}/connexion",
        ]
    text_lines += [
        "",
        "Important : les cotisations mensuelles impayées restent dues. Pensez à régulariser votre situation pour éviter une nouvelle radiation.",
        "",
        "Merci de votre engagement.",
        "L'équipe MONCAP.",
    ]
    text = "\n".join(text_lines) + "\n"

    motif_html = (
        f"<li><strong>Motif indiqué par l'administration</strong> : {escape(motif_reactivation)}</li>"
        if motif_reactivation
        else ""
    )
    login_html = (
        f'<p>Se connecter : <a href="{base_url}/connexion">{base_url}/connexion</a></p>'
        if base_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>Bonne nouvelle : votre compte a été réactivé et votre adhésion a été réhabilitée au sein du mouvement MONCAP.</p>
        <ul>
          {motif_html}
        </ul>
        <p>Vous pouvez à nouveau vous connecter à votre espace membre avec vos identifiants habituels.</p>
        {login_html}
        <p><strong>Important :</strong> les cotisations mensuelles impayées restent dues. Pensez à régulariser votre situation pour éviter une nouvelle radiation.</p>
        <p>Merci de votre engagement.<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html
