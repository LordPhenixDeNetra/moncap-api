# Prompt “Vibe Coding” — Backend MONCAP (API propre, JWT, rôles, refresh tokens)

Tu es un·e ingénieur·e backend senior. Génère une application backend production‑ready pour MONCAP, en respectant les bonnes pratiques d’API, la sécurité, SOLID, et une architecture modulaire.

Objectif : remplacer Supabase par un backend propriétaire.

Référence modèle métier : [MODELES_BACKEND.md](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/MODELES_BACKEND.md)

## 1) Stack & contraintes

- Langage : Python 3.12+
- Framework HTTP : FastAPI
- Serveur : Uvicorn (prod : Gunicorn + Uvicorn workers)
- Base de données : PostgreSQL
- ORM : SQLAlchemy 2.0 (async) + Alembic (migrations)
- Validation : Pydantic v2
- Tests : Pytest + HTTPX (ou TestClient) + factory fixtures
- OpenAPI : auto‑générée par FastAPI (Swagger UI)
- Configuration : `.env` + validation au démarrage via Pydantic Settings (pas de secrets loggés)
- Conteneurisation : Docker + docker-compose (db + api)

## 2) Principes (à appliquer partout)

### API Design (bonnes pratiques)

- Nommage clair et cohérent : ressources au pluriel, chemins “noun-based”
- Versioning : `/api/v1/...`
- Idempotence :
  - `GET/HEAD` sûrs
  - `PUT` idempotent
  - `POST` non-idempotent par défaut, mais supporte une clé d’idempotence pour les créations sensibles
- Pagination :
  - Offset pour simplicité (admin), et option cursor pour gros volumes
- Tri & filtres :
  - `?q=`, `?status=`, `?commissariat=`, `?from=`, `?to=`, `?sort=createdAt:desc`
- Références cross‑ressources : utiliser des chemins hiérarchiques lisibles quand c’est une vraie sous‑ressource
- Rate limiting : global + par route sensible (`/auth/*`, `/adhesions`)

### SOLID / Clean code

- SRP : séparer contrôleurs, services, repositories, validations, auth, erreurs
- DIP : injecter les dépendances (DB, cache, mail, storage) via interfaces
- OCP : ajouter une feature sans modifier en cascade
- Pas de logique métier dans les contrôleurs

## 3) Modules à implémenter

1. Auth
2. Users
3. Roles/Permissions (RBAC)
4. Référentiel géographique (Region/Departement/Commune)
5. Adhesions (soumission + suivi)
6. Admin (listing, filtres, export CSV, update statut)

## 4) Sécurité & Auth (JWT + Refresh tokens)

### Rôles (RBAC)

- Rôles : `admin`, `moderator`, `user`
- Autorisations (minimum) :
  - Public : soumission adhésion, suivi par email
  - Admin :
    - Lire toutes les adhésions
    - Mettre à jour statut + motif
    - Export CSV
    - Gérer le référentiel géographique (optionnel)
  - Moderator : lecture adhésions + demander complément (optionnel)

### JWT access token

- JWT court : 10–15 minutes
- Claims :
  - `sub` (userId)
  - `roles` (tableau)
  - `iat`, `exp`, `iss`, `aud`, `jti`
- Signature : HS256 (secret fort) ou RS256 (clé privée) ; documenter le choix
- Transmission :
  - Recommandé : `Authorization: Bearer <accessToken>`

### Refresh token (sécurisé, rotatif)

- Refresh token long : 7–30 jours
- Stockage :
  - Stocker uniquement un hash en DB (ex : SHA-256 du token)
  - Associer au user + device/session (`user_agent`, `ip`, `created_at`, `expires_at`)
- Rotation :
  - À chaque refresh, invalider l’ancien token et en émettre un nouveau
  - Détecter la réutilisation (token reuse) :
    - Si un refresh token déjà “rotated/revoked” est réutilisé : révoquer toute la session (ou tous les refresh tokens de l’utilisateur selon politique)
- Révocation :
  - Logout = révoquer le refresh token courant
  - Endpoint admin pour révoquer tous les refresh tokens d’un user (optionnel)

### Stockage côté client

- Si tu exposes l’API au navigateur :
  - Option A (recommandée) : refresh token en cookie `HttpOnly + Secure + SameSite`, access token en mémoire
  - Option B : refresh token en stockage sécurisé (moins recommandé)
- Implémenter CORS strict (origines autorisées)

### Protections complémentaires

- Rate limit sur `/auth/login` et `/auth/refresh`
- Hash mots de passe : Argon2 (ou bcrypt cost élevé)
- Verrouillage/anti bruteforce (progressif) sur login (optionnel)
- Normalisation email (`trim`, `lowercase`)
- Logging : pas de tokens, pas de passwords, pas de secrets

## 5) Modèles & Schéma DB (SQLAlchemy + Alembic)

Aligner le schéma avec [MODELES_BACKEND.md](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/MODELES_BACKEND.md) et inclure :

- `User`
- `UserRole` (unique `(userId, role)`)
- `Profile` (optionnel)
- `RefreshTokenSession` (ou `AuthSession`)
  - `tokenHash`, `userId`, `expiresAt`, `revokedAt`, `rotatedAt`, `userAgent`, `ip`, `createdAt`
- `Region`, `Departement`, `Commune`
- `Adhesion`
  - Remplacer les champs géographiques texte par des FK vers Region/Departement/Commune

Contraintes à implémenter :
- Unicité des noms :
  - `Region.nom` unique
  - `Departement.nom` unique par `regionId`
  - `Commune.nom` unique par `departementId`
- Cohérence :
  - `Adhesion.departementDomicileId` doit appartenir à `Adhesion.regionDomicileId`
  - `Adhesion.communeDomicileId` doit appartenir à `Adhesion.departementDomicileId`
  - Idem pour militantisme

Implémentation recommandée (FastAPI) :
- `models/` SQLAlchemy : tables, contraintes, index
- `schemas/` Pydantic : request/response DTOs
- `repositories/` : accès DB
- `services/` : logique métier (validation cohérence geo, idempotence, rotation refresh token)
- `api/` : routes FastAPI, dépendances, RBAC
- Migrations Alembic : `alembic/versions/*`

## 6) Endpoints (contrat API)

### Versioning

- Base path : `/api/v1`

### Public

- `POST /adhesions`
  - Supporter `Idempotency-Key` (header) : même payload + même clé => ne pas recréer
  - Payload validé (Pydantic), erreurs 400 structurées
- `GET /adhesions`
  - Query : `email` requis
  - Retour : liste triée `createdAt desc`
- `GET /geo/regions`
- `GET /geo/regions/:regionId/departements`
- `GET /geo/departements/:departementId/communes`

### Auth

- `POST /auth/login`
  - Body : `email`, `password`
  - Retour : `accessToken` + refresh token (cookie HttpOnly ou body selon option choisie)
- `POST /auth/refresh`
  - Rotate refresh token + renvoyer un nouveau access token
- `POST /auth/logout`
  - Révoquer la session refresh
- `GET /auth/me` (protégé)

### Admin (protégé, RBAC)

- `GET /admin/adhesions`
  - Pagination : `limit`, `offset` (et option cursor)
  - Filtres : `status`, `commissariat`, `q`, `from`, `to`
  - Tri : `sort=createdAt:desc`
- `PATCH /admin/adhesions/:id`
  - Update statut (`validee|rejetee|complement`) + `motifRejet`
  - Validation : motif requis si rejet
- `GET /admin/adhesions/export.csv`
  - Même filtres que listing, export CSV
- `POST /admin/geo/regions|departements|communes` (optionnel)

## 7) Convention des réponses & erreurs

### Succès

- Toujours JSON
- Exemple :
  - `{ "data": ..., "meta": { ... } }`

### Erreurs

- Format unique :
  - `{ "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [...] } }`
- Statuts :
  - 400 validation
  - 401 non authentifié
  - 403 interdit (rôle insuffisant)
  - 404 introuvable
  - 409 conflit (idempotence, duplicate)
  - 429 rate limit
  - 500 défaut interne

## 8) Observabilité

- Logger structuré (logging + structlog ou loguru)
- Correlation ID (`x-request-id`) généré si absent
- Logs : request/response time, status, route, userId (si auth)

## 9) Qualité & livrables attendus

Génère :
- Arborescence complète du projet
- Code complet (routers/dépendances/services/repositories)
- Modèles SQLAlchemy + migrations Alembic
- Tests clés :
  - login/refresh/logout (rotation + reuse detection)
  - RBAC (403)
  - POST /adhesions idempotency
  - cohérence geo (rejeter un departement qui n’appartient pas à la region)
- OpenAPI accessible via `/docs`
- Scripts :
  - `dev`, `start`, `test`, `lint`

## 10) Notes d’implémentation (décisions à prendre et à expliquer)

- Choix HS256 vs RS256
- Stratégie refresh token : cookie HttpOnly vs body
- Politique de révocation sur token reuse
- Stratégie de pagination pour `/admin/adhesions` (offset vs cursor)

## 11) Rappels de style

- Pas de logique d’accès DB directe dans les routes
- Fonctions petites, nommage explicite
- Couverture de tests minimale sur auth et adhésions
- Ne jamais logger tokens / passwords
