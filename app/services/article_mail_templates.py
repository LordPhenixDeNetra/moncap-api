from __future__ import annotations

from datetime import datetime
from html import escape

from app.models.article import Article


_ARTICLE_STATUS_LABELS: dict[str, str] = {
    "draft": "Brouillon",
    "waiting_validation": "En attente de validation",
    "changes_requested": "Corrections demandées",
    "rejected": "Rejeté",
    "published": "Publié",
}


def _status_label(s: str | None) -> str:
    if not s:
        return ""
    if s in _ARTICLE_STATUS_LABELS:
        return _ARTICLE_STATUS_LABELS[s]
    return str(s)


def _author_name(a: Article) -> str:
    author = getattr(a, "author", None)
    if author is not None:
        parts = [getattr(author, "prenom", None), getattr(author, "nom", None)]
        out = " ".join([x for x in parts if x]).strip()
        if out:
            return out
    return ""


def _author_email(a: Article) -> str | None:
    author = getattr(a, "author", None)
    email = None
    if author is not None:
        email = getattr(author, "email", None)
    if not email:
        return None
    return str(email).strip() or None


def _public_article_url(*, base_url: str | None, article: Article) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/") + f"/actualites/{article.id}"


def _owner_article_url(*, base_url: str | None, article: Article) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/") + f"/espace/articles/{article.id}"


def _admin_moderation_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    return base_url.rstrip("/") + "/admin/articles/validation"


def resolve_author_email(article: Article) -> str | None:
    """Retourne l'email de l'auteur d'un article, ou None si introuvable.

    Ordre de résolution :
      1) relation ORM article.author.email (si eager loadée → déjà dispo)
      2) email directement attaché via propriété / preload custom
    """
    return _author_email(article)


def _build_author_intro(article: Article) -> str:
    name = _author_name(article)
    if name:
        return f"Bonjour {name},"
    return "Bonjour,"


def build_article_submitted_for_validation(
    *,
    article: Article,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    """Mail adressé à l'AUTEUR quand il soumet un article en attente de validation.

    Cas typiques :
      - Article non-privilégié créé avec statut != draft (forcé à waiting_validation)
      - Auteur qui fait passer son brouillon à waiting_validation
    """
    subject = "[MONCAP] Votre article a été soumis pour modération"
    intro = _build_author_intro(article)
    pub_url = _owner_article_url(base_url=base_url, article=article)
    created_dt = getattr(article, "created_at", None)
    created_label = (
        created_dt.strftime("%d/%m/%Y à %H:%M")
        if isinstance(created_dt, datetime)
        else ""
    )

    text_lines = [
        intro,
        "",
        "Merci pour votre contribution. Votre article a bien été soumis à l'équipe de modération.",
        "",
        f"Titre : {article.title}",
    ]
    if article.summary:
        text_lines.append(f"Résumé : {article.summary}")
    if created_label:
        text_lines.append(f"Date de soumission : {created_label}")
    text_lines.append(
        f"Statut actuel : {_status_label(article.status)}"
    )
    if article.commissariat:
        text_lines.append(f"Commissariat : {article.commissariat}")
    if pub_url:
        text_lines += ["", f"Votre article (espace auteur) : {pub_url}"]
    text_lines += [
        "",
        "Vous recevrez un email dès qu'une décision sera prise (publication, rejet ou demande de corrections).",
        "",
        "Merci de votre engagement.",
        "L'équipe MONCAP",
    ]
    text = "\n".join(text_lines) + "\n"

    summary_html = (
        f"<li><strong>Résumé</strong> : {escape(article.summary)}</li>"
        if article.summary
        else ""
    )
    created_html = (
        f"<li><strong>Date de soumission</strong> : {escape(created_label)}</li>"
        if created_label
        else ""
    )
    commissariat_html = (
        f"<li><strong>Commissariat</strong> : {escape(article.commissariat)}</li>"
        if article.commissariat
        else ""
    )
    link_html = (
        f'<p>Votre article : <a href="{pub_url}">{pub_url}</a></p>'
        if pub_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>Merci pour votre contribution. Votre article a bien été soumis à l'équipe de modération.</p>
        <ul>
          <li><strong>Titre</strong> : {escape(article.title)}</li>
          {summary_html}
          {created_html}
          <li><strong>Statut actuel</strong> : {escape(_status_label(article.status))}</li>
          {commissariat_html}
        </ul>
        {link_html}
        <p>Vous recevrez un email dès qu'une décision sera prise (publication, rejet ou demande de corrections).</p>
        <p>Merci de votre engagement.<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_article_published(
    *,
    article: Article,
    base_url: str | None = None,
    validator_name: str | None = None,
) -> tuple[str, str, str]:
    """Mail adressé à l'AUTEUR quand son article est publié."""
    subject = "[MONCAP] Votre article a été publié"
    intro = _build_author_intro(article)
    public_url = _public_article_url(base_url=base_url, article=article)
    owner_url = _owner_article_url(base_url=base_url, article=article)
    motif = getattr(article, "validation_motif", None)

    text_lines = [
        intro,
        "",
        "Bonne nouvelle : votre article a été validé et est maintenant en ligne.",
        "",
        f"Titre : {article.title}",
    ]
    if motif:
        text_lines.append(f"Motif du modérateur : {motif}")
    if validator_name:
        text_lines.append(f"Validé par : {validator_name}")
    if public_url:
        text_lines += ["", f"Lien public : {public_url}"]
    if owner_url:
        text_lines.append(f"Votre espace : {owner_url}")
    text_lines += [
        "",
        "Merci de votre engagement.",
        "L'équipe MONCAP",
    ]
    text = "\n".join(text_lines) + "\n"

    motif_html = (
        f"<li><strong>Motif du modérateur</strong> : {escape(motif)}</li>"
        if motif
        else ""
    )
    validator_html = (
        f"<li><strong>Validé par</strong> : {escape(validator_name)}</li>"
        if validator_name
        else ""
    )
    public_html = (
        f'<p>Lien public : <a href="{public_url}">{public_url}</a></p>'
        if public_url
        else ""
    )
    owner_html = (
        f'<p>Votre espace : <a href="{owner_url}">{owner_url}</a></p>'
        if owner_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>Bonne nouvelle : votre article a été validé et est maintenant en ligne.</p>
        <ul>
          <li><strong>Titre</strong> : {escape(article.title)}</li>
          {motif_html}
          {validator_html}
        </ul>
        {public_html}
        {owner_html}
        <p>Merci de votre engagement.<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_article_rejected(
    *,
    article: Article,
    base_url: str | None = None,
    validator_name: str | None = None,
) -> tuple[str, str, str]:
    """Mail adressé à l'AUTEUR quand son article est rejeté."""
    subject = "[MONCAP] Votre article a été rejeté"
    intro = _build_author_intro(article)
    owner_url = _owner_article_url(base_url=base_url, article=article)
    motif = getattr(article, "validation_motif", None)

    text_lines = [
        intro,
        "",
        "Nous avons étudié votre article. Malheureusement, il n'a pas été retenu à la publication.",
        "",
        f"Titre : {article.title}",
    ]
    if motif:
        text_lines.append(f"Motif du rejet : {motif}")
    else:
        text_lines.append("Motif du rejet : non communiqué.")
    if validator_name:
        text_lines.append(f"Traité par : {validator_name}")
    if owner_url:
        text_lines += ["", f"Votre article (espace auteur) : {owner_url}"]
    text_lines += [
        "",
        "Vous pouvez modifier votre article et le soumettre à nouveau, en tenant compte du motif ci-dessus.",
        "",
        "Merci de votre engagement.",
        "L'équipe MONCAP",
    ]
    text = "\n".join(text_lines) + "\n"

    motif_html = (
        f"<li><strong>Motif du rejet</strong> : {escape(motif)}</li>"
        if motif
        else "<li><strong>Motif du rejet</strong> : non communiqué.</li>"
    )
    validator_html = (
        f"<li><strong>Traité par</strong> : {escape(validator_name)}</li>"
        if validator_name
        else ""
    )
    owner_html = (
        f'<p>Votre article : <a href="{owner_url}">{owner_url}</a></p>'
        if owner_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>Nous avons étudié votre article. Malheureusement, il n'a pas été retenu à la publication.</p>
        <ul>
          <li><strong>Titre</strong> : {escape(article.title)}</li>
          {motif_html}
          {validator_html}
        </ul>
        {owner_html}
        <p>Vous pouvez modifier votre article et le soumettre à nouveau, en tenant compte du motif ci-dessus.</p>
        <p>Merci de votre engagement.<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_article_changes_requested(
    *,
    article: Article,
    base_url: str | None = None,
    validator_name: str | None = None,
) -> tuple[str, str, str]:
    """Mail adressé à l'AUTEUR quand des corrections sont demandées."""
    subject = "[MONCAP] Corrections demandées sur votre article"
    intro = _build_author_intro(article)
    owner_url = _owner_article_url(base_url=base_url, article=article)
    motif = getattr(article, "validation_motif", None)

    text_lines = [
        intro,
        "",
        "L'équipe de modération a examiné votre article et demande quelques ajustements avant publication.",
        "",
        f"Titre : {article.title}",
    ]
    if motif:
        text_lines.append(f"Corrections demandées : {motif}")
    else:
        text_lines.append("Aucune précision fournie par le modérateur.")
    if validator_name:
        text_lines.append(f"Demande de : {validator_name}")
    if owner_url:
        text_lines += ["", f"Modifier votre article : {owner_url}"]
    text_lines += [
        "",
        "Après modifications, repassez votre article en attente de validation pour une nouvelle revue.",
        "",
        "Merci de votre engagement.",
        "L'équipe MONCAP",
    ]
    text = "\n".join(text_lines) + "\n"

    motif_html = (
        f"<li><strong>Corrections demandées</strong> : {escape(motif)}</li>"
        if motif
        else "<li>Aucune précision fournie par le modérateur.</li>"
    )
    validator_html = (
        f"<li><strong>Demande de</strong> : {escape(validator_name)}</li>"
        if validator_name
        else ""
    )
    owner_html = (
        f'<p>Modifier votre article : <a href="{owner_url}">{owner_url}</a></p>'
        if owner_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>{escape(intro)}</p>
        <p>L'équipe de modération a examiné votre article et demande quelques ajustements avant publication.</p>
        <ul>
          <li><strong>Titre</strong> : {escape(article.title)}</li>
          {motif_html}
          {validator_html}
        </ul>
        {owner_html}
        <p>Après modifications, repassez votre article en attente de validation pour une nouvelle revue.</p>
        <p>Merci de votre engagement.<br>L'équipe MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html


def build_article_resubmitted_after_feedback(
    *,
    article: Article,
    base_url: str | None = None,
    author_name: str | None = None,
) -> tuple[str, str, str]:
    """Mail adressé À L'ÉQUIPE STAFF (boîte de modération) quand l'auteur a
    modifié son article suite à corrections / rejet et l'a repassé en waiting_validation.

    Ce mail doit être envoyé à une adresse unique (ex: modérateurs@domaine ou admins).
    """
    subject = f"[MONCAP - Modération] Article modifié et resoumis : {article.title}"
    moderation_url = _admin_moderation_url(base_url)
    author_label = author_name or _author_name(article) or "(auteur non identifié)"

    text_lines = [
        "Bonjour équipe de modération,",
        "",
        "Un article a été modifié par son auteur et repassé en attente de validation.",
        "",
        f"Titre : {article.title}",
        f"Auteur : {author_label}",
        f"Statut actuel : {_status_label(article.status)}",
    ]
    if article.commissariat:
        text_lines.append(f"Commissariat : {article.commissariat}")
    if moderation_url:
        text_lines += ["", f"File d'attente de modération : {moderation_url}"]
    text_lines += [
        "",
        "Merci de relire cet article.",
        "L'équipe MONCAP (notification automatique)",
    ]
    text = "\n".join(text_lines) + "\n"

    commissariat_html = (
        f"<li><strong>Commissariat</strong> : {escape(article.commissariat)}</li>"
        if article.commissariat
        else ""
    )
    mod_html = (
        f'<p>File d\'attente : <a href="{moderation_url}">{moderation_url}</a></p>'
        if moderation_url
        else ""
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5;">
        <p>Bonjour équipe de modération,</p>
        <p>Un article a été modifié par son auteur et repassé en attente de validation.</p>
        <ul>
          <li><strong>Titre</strong> : {escape(article.title)}</li>
          <li><strong>Auteur</strong> : {escape(author_label)}</li>
          <li><strong>Statut actuel</strong> : {escape(_status_label(article.status))}</li>
          {commissariat_html}
        </ul>
        {mod_html}
        <p>Merci de relire cet article.<br>Notification automatique MONCAP.</p>
      </body>
    </html>
    """.strip()
    return subject, text, html
