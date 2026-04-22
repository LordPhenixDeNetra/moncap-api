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

