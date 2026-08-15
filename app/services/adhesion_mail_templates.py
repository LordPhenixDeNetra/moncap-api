from __future__ import annotations

from html import escape

from app.models.adhesion import Adhesion
from app.models.enums import AdhesionStatus


def _format_full_name(adhesion: Adhesion) -> str:
    return " ".join([x for x in [adhesion.prenom, adhesion.nom] if x]).strip()


def _maybe_tracking_link(*, base_url: str | None, adhesion: Adhesion) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/") + f"/suivi?email={escape(adhesion.email)}"


def build_adhesion_created(*, adhesion: Adhesion, base_url: str | None = None) -> tuple[str, str, str]:
    full_name = _format_full_name(adhesion)
    subject = "MONCAP — Demande d’adhésion reçue"
    link = _maybe_tracking_link(base_url=base_url, adhesion=adhesion)

    text_lines = [
        f"Bonjour {full_name}," if full_name else "Bonjour,",
        "",
        "Nous avons bien reçu votre demande d’adhésion.",
        f"Référence: {adhesion.id}",
        f"Statut: {adhesion.statut.value if hasattr(adhesion.statut, 'value') else adhesion.statut}",
    ]
    if link:
        text_lines += ["", f"Suivi: {link}"]
    text = "\n".join(text_lines) + "\n"

    html = f"""
    <html>
      <body>
        <p>{escape(f"Bonjour {full_name}," if full_name else "Bonjour,")}</p>
        <p>Nous avons bien reçu votre demande d’adhésion.</p>
        <ul>
          <li><strong>Référence</strong>: {escape(str(adhesion.id))}</li>
          <li><strong>Statut</strong>: {escape(adhesion.statut.value if hasattr(adhesion.statut, "value") else str(adhesion.statut))}</li>
        </ul>
        {f'<p>Suivi: <a href="{link}">{link}</a></p>' if link else ''}
        <p>Merci.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_adhesion_status_changed(
    *,
    adhesion: Adhesion,
    old_status: AdhesionStatus | None,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    full_name = _format_full_name(adhesion)
    new_status = adhesion.statut
    subject = "MONCAP — Mise à jour de votre demande d’adhésion"
    link = _maybe_tracking_link(base_url=base_url, adhesion=adhesion)

    status_label = new_status.value if hasattr(new_status, "value") else str(new_status)
    old_label = old_status.value if (old_status is not None and hasattr(old_status, "value")) else (str(old_status) if old_status else None)

    text_lines = [
        f"Bonjour {full_name}," if full_name else "Bonjour,",
        "",
        "Le statut de votre demande d’adhésion a été mis à jour.",
        f"Référence: {adhesion.id}",
        f"Nouveau statut: {status_label}",
    ]
    if old_label:
        text_lines.append(f"Ancien statut: {old_label}")
    if new_status == AdhesionStatus.rejetee and adhesion.motif_rejet:
        text_lines += ["", f"Motif: {adhesion.motif_rejet}"]
    if link:
        text_lines += ["", f"Suivi: {link}"]
    text = "\n".join(text_lines) + "\n"

    motif_html = ""
    if new_status == AdhesionStatus.rejetee and adhesion.motif_rejet:
        motif_html = f"<p><strong>Motif</strong>: {escape(adhesion.motif_rejet)}</p>"

    html = f"""
    <html>
      <body>
        <p>{escape(f"Bonjour {full_name}," if full_name else "Bonjour,")}</p>
        <p>Le statut de votre demande d’adhésion a été mis à jour.</p>
        <ul>
          <li><strong>Référence</strong>: {escape(str(adhesion.id))}</li>
          <li><strong>Nouveau statut</strong>: {escape(status_label)}</li>
          {f'<li><strong>Ancien statut</strong>: {escape(old_label)}</li>' if old_label else ''}
        </ul>
        {motif_html}
        {f'<p>Suivi: <a href="{link}">{link}</a></p>' if link else ''}
        <p>Merci.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_payment_confirmed(*, adhesion: Adhesion, base_url: str | None = None) -> tuple[str, str, str]:
    full_name = _format_full_name(adhesion)
    subject = "MONCAP — Paiement confirmé"
    link = _maybe_tracking_link(base_url=base_url, adhesion=adhesion)

    ref = adhesion.reference_paiement or ""
    text_lines = [
        f"Bonjour {full_name}," if full_name else "Bonjour,",
        "",
        "Votre paiement a été confirmé.",
        f"Référence adhésion: {adhesion.id}",
        f"Montant: {adhesion.montant_adhesion}",
    ]
    if ref:
        text_lines.append(f"Référence paiement: {ref}")
    if link:
        text_lines += ["", f"Suivi: {link}"]
    text = "\n".join(text_lines) + "\n"

    html = f"""
    <html>
      <body>
        <p>{escape(f"Bonjour {full_name}," if full_name else "Bonjour,")}</p>
        <p>Votre paiement a été confirmé.</p>
        <ul>
          <li><strong>Référence adhésion</strong>: {escape(str(adhesion.id))}</li>
          <li><strong>Montant</strong>: {escape(str(adhesion.montant_adhesion))}</li>
          {f'<li><strong>Référence paiement</strong>: {escape(ref)}</li>' if ref else ''}
        </ul>
        {f'<p>Suivi: <a href="{link}">{link}</a></p>' if link else ''}
        <p>Merci.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def _derive_password_label(adhesion: Adhesion) -> tuple[str, str]:
    """Retourne (valeur, label_humain) du mot de passe initial selon les
    règle de MemberAccountService._build_initial_password.
    """
    if adhesion.carte_pastef and adhesion.carte_pastef.strip():
        return adhesion.carte_pastef.strip(), "votre numéro de carte PASTEF"
    if adhesion.cni and adhesion.cni.strip():
        return adhesion.cni.strip(), "votre numéro de CNI"
    return "", "un code temporaire"


def build_adhesion_validee_welcome(
    *,
    adhesion: Adhesion,
    old_status: AdhesionStatus | None,
    base_url: str | None = None,
    account_created: bool,
    temporary_password: str,
) -> tuple[str, str, str]:
    """
    Template dédié à la validation FINALE par le comité directoire (statut = validee).
    Inclut un bloc clair « VOTRE COMPTE MEMBRE EST CRÉÉ / MIS À JOUR » avec :
      - Identifiant de connexion : EMAIL (identifiant accepté par /api/v1/auth/login
        dans la version actuelle du backend ; TODO: adapter quand login multi-identifiants).
      - Mot de passe initial : carte_pastef OU cni OU code temporaire UUID selon
        ce qui a été fourni dans l'adhésion.
      - Conseil : changer le mot de passe à la 1ère connexion.
    """
    full_name = _format_full_name(adhesion)
    subject = "MONCAP — Votre adhésion a été validée ! 🎉"
    link = _maybe_tracking_link(base_url=base_url, adhesion=adhesion)

    status_label = adhesion.statut.value if hasattr(adhesion.statut, "value") else str(adhesion.statut)
    if old_status is not None and hasattr(old_status, "value"):
        old_label: str | None = old_status.value
    else:
        old_label = str(old_status) if old_status else None

    pwd_value, pwd_label = _derive_password_label(adhesion)
    if not pwd_value:
        pwd_value = temporary_password or ""
    account_title = (
        "Votre compte membre a été créé."
        if account_created
        else "Votre compte membre a été mis à jour avec le rôle militant."
    )

    text_lines = [
        f"Bonjour {full_name}," if full_name else "Bonjour,",
        "",
        "Félicitations ! 🎉 Votre demande d'adhésion au MONCAP a été approuvée par le comité directoire.",
        "",
        f"Référence adhésion : {adhesion.id}",
        f"Statut : {status_label}",
    ]
    if old_label:
        text_lines.append(f"Ancien statut : {old_label}")
    text_lines += [
        "",
        "------------------------------------------------------------------",
        account_title,
        "------------------------------------------------------------------",
    ]
    if account_created:
        text_lines += [
            "",
            "Pour vous connecter à l'espace membre :",
            f"  • Identifiant (login) : {adhesion.email}  (Votre adresse email)",
        ]
        if pwd_value:
            text_lines.append(f"  • Mot de passe initial : {pwd_value}")
            text_lines.append(f"    (il correspond à {pwd_label})")
        text_lines += [
            "",
            "IMPORTANT : pour votre sécurité, changez ce mot de passe dès votre 1ère connexion,",
            "depuis la section profil / mot de passe de l'application.",
        ]
    else:
        text_lines += [
            "",
            "Votre identifiant de connexion reste inchangé.",
            "Si vous avez oublié votre mot de passe, utilisez la fonctionnalité « mot de passe oublié.",
        ]
    if link:
        text_lines += [
            "",
            f"Suivi de votre adhésion : {link}",
        ]
    text_lines += [
        "",
        "Bienvenue parmi nous, camarade.🙏.",
        "",
        "--",
        "L'équipe MONCAP",
    ]
    text = "\n".join(text_lines) + "\n"

    # ---- HTML ----
    pwd_info_html = ""
    if account_created:
        pwd_info_html = f"""
        <div style="background:#f1f2f6;padding:16px;border-left:4px solid #222;margin:16px 0;">
          <p style="margin:0 0 8px 0;"><strong>{escape(account_title)}</strong></p>
          <p style="margin:4px 0;">Pour vous connecter à l'espace membre :</p>
          <ul>
            <li><strong>Identifiant (login) :</strong> {escape(adhesion.email)}</li>
            {f'<li><strong>Mot de passe initial :</strong> <code style="background:#fff;padding:2px 6px;border-radius:4px;">{escape(pwd_value)}</code><br><em>(il correspond à {escape(pwd_label)}</li>' if pwd_value else ''}
          </ul>
          <p style="color:#c0392b;margin:8px 0 0 0;"><strong>IMPORTANT</strong> : pour votre sécurité, changez ce mot de passe dès votre 1ère connexion, depuis la section profil / mot de passe de l'application.</p>
        </div>
        """
    else:
        pwd_info_html = f"""
        <div style="background:#f1f2f6;padding:16px;border-left:4px solid #222;margin:16px 0;">
          <p style="margin:0 0 8px 0;"><strong>{escape(account_title)}</strong></p>
          <p style="margin:4px 0;">Votre identifiant de connexion reste inchangé.</p>
          <p style="margin:4px 0;">Si vous avez oublié votre mot de passe, utilisez la fonctionnalité « mot de passe oublié.</p>
        </div>
        """

    html = f"""
    <html>
      <body style="font-family: Arial, 'Helvetica Neue', Helvetica, sans-serif; line-height: 1.5; color:#222;">
        <p>{escape(f"Bonjour {full_name}," if full_name else "Bonjour,")}</p>
        <p>Félicitations ! 🎉 Votre demande d'adhésion au <strong>MONCAP</strong> a été approuvée par le comité directoire.</p>
        <ul>
          <li><strong>Référence adhésion</strong>: {escape(str(adhesion.id))}</li>
          <li><strong>Statut</strong>: {escape(status_label)}</li>
          {f'<li><strong>Ancien statut</strong>: {escape(old_label)}</li>' if old_label else ''}
        </ul>
        {pwd_info_html}
        {f'<p>Suivi de votre adhésion : <a href="{link}">{link}</a></p>' if link else ''}
        <p>Bienvenue parmi nous, camarade.🙏.</p>
        <p>—<br>L'équipe MONCAP</p>
      </body>
    </html>
    """.strip()
    return subject, text, html

