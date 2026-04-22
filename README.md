# MONCAP API

Backend MONCAP (FastAPI + PostgreSQL + JWT)

## Prérequis

- Python 3.12+
- Poetry
- PostgreSQL (accessible via `DATABASE_URL`)

## Installation

```bash
python -m pip install --user poetry
python -m poetry install
```

## Configuration (.env)

Le projet charge automatiquement un fichier `.env` à la racine (ignoré par git).

Variables principales :

- `DATABASE_URL` (PostgreSQL)
  - Accepté : `postgresql+asyncpg://...`
  - Accepté aussi : `postgresql://...` ou `postgresql+psycopg2://...` (converti automatiquement en `asyncpg`)
- `JWT_SECRET` (min 32 caractères)
- `CORS_ALLOW_ORIGINS` (liste JSON d’origines)
- `REFRESH_COOKIE_SECURE` (`false` en dev HTTP, `true` en prod HTTPS)

## Lancer l’application

```bash
python -m poetry run uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- API : http://127.0.0.1:8000
- Docs : http://127.0.0.1:8000/docs

## Base de données & migrations

```bash
python -m poetry run alembic upgrade head
```

## Créer un admin

```bash
python -m poetry run python -m app.cli.create_admin --email admin@example.com --password "Password123!"
```

## Tests

```bash
python -m poetry run pytest
```

## Endpoints (v1)

- Health : `GET /api/v1/health`
- Auth :
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/refresh`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
- Geo :
  - `GET /api/v1/geo/regions`
  - `GET /api/v1/geo/regions/{regionId}/departements`
  - `GET /api/v1/geo/departements/{departementId}/communes`
- Adhésions :
  - `POST /api/v1/adhesions` (multipart, support `Idempotency-Key`)
  - `GET /api/v1/adhesions?email=...`
- Admin (JWT + rôle `admin`) :
  - `GET /api/v1/admin/adhesions`
  - `PATCH /api/v1/admin/adhesions/{id}`
  - `GET /api/v1/admin/adhesions/export.csv`

## Structure (résumé)

- `app/api/v1/` : routes HTTP
- `app/models/` : modèles SQLAlchemy
- `app/schemas/` : schémas Pydantic
- `app/services/` : logique métier
- `app/repositories/` : accès DB
- `alembic/` : migrations




<!-- .\.venv\Scripts\activate -->
<!-- .\.venv\Scripts\Activate.ps1 -->


<!-- LINUX -->
<!-- source .venv/bin/activate -->
<!-- source venv/bin/activate -->

<!-- python -m pip install -U poetry
poetry --version
poetry install -->

<!-- python -m poetry run uvicorn main:app --reload --host 127.0.0.1 --port 8000 -->
