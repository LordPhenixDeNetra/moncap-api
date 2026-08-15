from __future__ import annotations

from functools import lru_cache

from app.core.settings import get_settings


def to_absolute_public_url(url: str | None) -> str | None:
    """
    Préfixe une URL relative de fichier public (/files/...) avec la base URL
    publique de l'API (setting `api_base_url`).

    - Si URL est None → None
    - Si URL est déjà absolue (http/https) → inchangée (cross-domain, prod)
    - Si URL commence par / et api_base_url est défini → concaténation propre
    - Sinon → URL inchangée (compatibilité avec anciens app / tests)
    """
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    settings = get_settings()
    base = settings.api_base_url
    if not base:
        return url
    base = base.rstrip("/")
    if not url.startswith("/"):
        url = "/" + url
    return f"{base}{url}"
