FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir poetry

# Dépendances d'abord : couche mise en cache tant que pyproject/poetry.lock ne changent pas
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# Planificateur des tâches CRON (utilisé seulement par le conteneur "cron",
# lancé avec : supercronic /app/crontab). Version à vérifier sur
# https://github.com/aptible/supercronic/releases (remplacer amd64 par arm64 sur serveur ARM).
ARG SUPERCRONIC_VERSION=v0.2.33
ADD https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

# Utilisateur sans privilèges root
RUN useradd --create-home --uid 1000 moncap

COPY --chown=moncap:moncap . .

# Fichiers uploadés (CV, photos, diplômes, QR codes) : à monter en volume
RUN mkdir -p /app/storage && chown moncap:moncap /app/storage
VOLUME ["/app/storage"]

USER moncap

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
