# Changelog Backend MONCAP — à destination du développeur Frontend

> Date : 2026-08-14
> Projet : `moncap-api` (FastAPI + PostgreSQL)
> Base URL API : `http://localhost:<port>/api/v1` (adapter selon environnement)

Ce fichier résume **toutes les nouveautés backend** récentes que tu peux consommer côté frontend.
Il est structuré par thème :

- 1) Erreurs API (format uniforme)
- 2) Formulaire d’adhésion (champs, anti-doublons, erreurs robustes)
- 3) Admin (modif/suppression d’adhésion + remplacement fichiers)
- 4) Workflow validation “Complément requis” (`complement`)
- 5) Module “Militants” (stats / ventilation / recherche adhérent validé)
- 6) Comptes militants + connexion “email + Carte PASTEF”
- 7) Module Articles / Publications (couverture + pièces jointes max N + likes + commentaires)
- 8) Infos utiles (prefixes, auth, roles)

---

## 1) Format d’erreur uniforme (TOUS endpoints)

Désormais, **toutes** les erreurs backend (400/401/403/404/409/422…) renvoient un format standard :

```json
{
  "error": {
    "code": "DUPLICATE_EMAIL",
    "message": "Une adhésion existe déjà avec cet email",
    "details": [
      { "field": "email" }
    ]
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- `error.code` : code stable exploitable en frontend (ex: `DUPLICATE_EMAIL`, `VALIDATION_ERROR`, `NOT_FOUND`, `FORBIDDEN`).
- `error.details` : tableau (peut contenir des champs, ou des erreurs Pydantic multi-champs).
- `request_id` : à afficher dans la console/log UI si tu veux qu’on retrouve le bug dans les logs backend.

Référence backend : [core/errors.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/core/errors.py)

---

## 2) Formulaire d’adhésion (maj)

### Endpoint
`POST /adhesions` (multipart/form-data)

### Nouveau champ (photo profil, pour la carte membre)
- `profile_photo` : `File` (optionnel)
- Le backend stocke l’URL retournée dans la réponse (`profile_photo_url`).

### Autres champs déjà présents mais rappel utiles
- `commissariat_scientifique_principal` et `commissariat_scientifique_secondaire` :
  - Utilisés **seulement si** `commissariat == "Commissariat scientifique"` (trim + case-insensitive).
  - Dans ce cas les 2 sont **requis** (sinon 400).

### Anti-doublons (IMPORTANT : à afficher clairement en UI)
Si un même identifiant existe déjà sur une adhésion **non supprimée**, tu recevras :

| Situation | HTTP | error.code | error.details[0].field |
|---|---|---|---|
| Même email | 409 | `DUPLICATE_EMAIL` | `email` |
| Même CNI | 409 | `DUPLICATE_CNI` | `cni` |
| Même carte électeur (si fournie) | 409 | `DUPLICATE_CARTE_ELECTEUR` | `carte_electeur` |
| Race condition (bloquée par DB) | 409 | `DUPLICATE_IDENTIFIER` | — |

Format d’erreur typique :
```json
{
  "error": {
    "code": "DUPLICATE_EMAIL",
    "message": "Une adhésion existe déjà avec cet email",
    "details": [{ "field": "email" }]
  },
  "request_id": "..."
}
```

Notes :
- `email` est normalisé (lowercase + trim).
- `cni` et `carte_electeur` sont trimés ; `carte_electeur` vide → `NULL` en base (plusieurs null autorisés).

### Erreurs de validation formulaire (422 mappé en 400)
- `error.code = "VALIDATION_ERROR"`
- `error.details` contient la liste des erreurs Pydantic (champs `loc`, `msg`, `type`) pour chaque champ invalide.

Référence backend :
- Route create : [routes/adhesions.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/adhesions.py)
- Service validation/erreurs : [services/adhesions.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesions.py)

---

## 3) Admin : modifier / supprimer une adhésion

Tous endpoints ci-dessous sont **rôle `admin` uniquement** (sinon 403).

### 3.1 Suppression “soft delete”
- `DELETE /admin/adhesions/{adhesion_id}`
- Réponse :
```json
{ "data": { "deleted": true } }
```
- Remarques :
  - Après suppression : l’adhésion n’apparaît plus dans les listes/lookups.
  - Les index “email/cni/carte_electeur uniques” s’appliquent **uniquement aux adhésions non supprimées** → tu peux recréer une adhésion avec les mêmes identifiants si besoin.

### 3.2 Modifier les champs du formulaire
- `PATCH /admin/adhesions/{adhesion_id}/info`
- Body JSON (presque tous les champs du formulaire, **tous optionnels**) :
  - nom, prenom, date_naissance, lieu_naissance, profession
  - tel_mobile, tel_fixe, email, cni, carte_electeur, carte_pastef
  - est_diaspora (true/false)
  - region_domicile_id, departement_domicile_id, commune_domicile_id
  - pays_domicile_id, ville_domicile
  - region_militantisme_id, departement_militantisme_id, commune_militantisme_id
  - pays_militantisme_id, ville_militantisme
  - fonction_professionnelle, engagement (liste)
  - commissariat, commissariat_scientifique_principal, commissariat_scientifique_secondaire
  - mode_paiement, paiement_confirme (bool), reference_paiement
  - niveau_etude, annees_experience, biographie
  - statut (autorisé pour admin : en_attente/complement/validee_accueil/validee/rejetee)
- Le backend refait toutes les validations métier (diaspora/cohérence géo/commissariat scientifique + unicité email/cni/carte_electeur) → erreurs 400/409 structurées.

### 3.3 Remplacer les fichiers d’une adhésion
- `PATCH /admin/adhesions/{adhesion_id}/files` (multipart/form-data)
- Fichiers acceptés (tous optionnels dans la requête) :
  - `profile_photo`
  - `photo_recto`
  - `photo_verso`
  - `cv`
- Retourne la fiche complète de l’adhésion mise à jour.

Référence backend : [routes/admin.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/admin.py)

---

## 4) Workflow “Complément requis”

Contexte : statut `complement` existe déjà.

### 4.1 Sortir du statut `complement`
Autorisé **comité d’accueil** (`comite_accueil`) :

- `PATCH /accueil/adhesions/{adhesion_id}/valider`
- Accepte les statuts sources :
  - `en_attente`
  - `complement`
- Transition : passe en `validee_accueil`.

(Précédemment, seulement `en_attente` était accepté → bloquait `complement` ; maintenant corrigé.)

Référence backend : [validations.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/validations.py#L182-L207)

---

## 5) Module “Militants” (stats + lookup carte membre)

Définition “militant” côté backend : adhésion avec `statut = "validee"`.

### Accès / rôles
- **Stats** : `admin`, `comite_accueil`, `comite_directoire` (403 sinon).
- **Lookup carte membre** : **public** (pas de rôle requis) — exposé volontairement pour /suivi sans login.

### 5.1 Endpoints stats (agrégations)
- `GET /militants/count`
  - Query (optionnels) : `commissariat`, `from_date`, `to_date`
  - Réponse :
```json
{ "data": { "total": 241 } }
```

- `GET /militants/stats/{dimension}` (ventilation)
  - `dimension` ∈ `regions | departements | communes | pays | villes`
  - Query : `mode=domicile|militantisme` (défaut `domicile`) + filtres `commissariat/from_date/to_date`
  - Réponse :
```json
{
  "data": [
    { "id": "uuid-région", "label": "Dakar", "count": 120 },
    { "id": null, "label": "paris", "count": 7 }
  ]
}
```
  - Note : pour `villes`, `id` est toujours `null` (ville stockée en texte libre).

- `GET /militants/stats/commissariats`
- `GET /militants/stats/diaspora` → réponse :
```json
{ "data": { "diaspora": 50, "local": 191 } }
```

- `GET /militants/timeseries`
  - Query : `interval=day|week|month` (défaut `month`) + filtres habituels
  - Réponse :
```json
{ "data": [ { "period": "2026-07-01", "count": 12 }, { "period": "2026-08-01", "count": 22 } ] }
```

- `GET /militants/hierarchy`
  - Query : `level=regions_departements` OU `departements_communes`, `mode=domicile|militantisme`
  - Retourne une hiérarchie 2 niveaux (pratique pour dashboards drill-down).

### 5.2 Lookup “fiche carte membre” (public)
- `GET /militants/lookup`
- **Un seul critère à la fois** (sinon 400 “Un seul critère est autorisé”) :
  - `email=...`
  - `cni=...`
  - `tel_mobile=...`
  - `carte_pastef=...`
  - `id=<adhesion_id>`
- Réponse “carte membre” (exemple, `data.militant`) :
```json
{
  "data": {
    "id": "uuid-adhésion",
    "nom": "Diallo",
    "prenom": "Aminata",
    "email": "a.diallo@example.com",
    "tel_mobile": "771234567",
    "cni": "1234567890",
    "carte_pastef": "ABC123",
    "commissariat": "Commissariat scientifique",
    "commissariat_scientifique_principal": "Numérique",
    "commissariat_scientifique_secondaire": "Bonne Gouvernance",
    "photo_url": "https://.../photo.jpg",
    "profile_photo_url": "https://.../profile.jpg",
    "region_domicile_id": "uuid",
    "departement_domicile_id": "uuid",
    "commune_domicile_id": "uuid",
    "pays_domicile_id": "uuid",
    "ville_domicile": "Dakar",
    "region_domicile": { "id": "...", "nom": "Dakar", "code": "..." },
    "departement_domicile": { "id": "...", "nom": "Dakar", "code": "...", "region_id": "..." },
    "commune_domicile": { "id": "...", "nom": "Plateau", "code": "...", "departement_id": "..." },
    "pays_domicile": { "id": "...", "nom": "Sénégal", "code": "SN" }
  }
}
```

Références backend :
- [routes/militants.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py)
- [schemas/militants.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/militants.py)

---

## 6) Comptes militants + connexion “email + Carte PASTEF”

### 6.1 Quand est-ce qu’un compte militant est créé ?
- Lors de la validation finale (directoire) :
  - `PATCH /directoire/adhesions/{id}/valider`
- Le backend crée automatiquement un `User` :
  - email = `adhesion.email`
  - rôle = `militant`
  - **mot de passe initial = valeur de `carte_pastef` (trim)**
  - fallback si `carte_pastef` est absent : **CNI (trim)**
  - `user.adhesion_id` = lien 1:1 vers l’adhésion
- Si le mail est activé, un email part avec identifiant + mot de passe initial.

Tu peux aussi **sans compte pré-existant** faire la 1ère connexion (le backend crée le compte “à la volée”) si :
- l’email correspond à une adhésion validée,
- ET le mot de passe fourni = Carte PASTEF (ou fallback CNI).

### 6.2 Se connecter
- `POST /auth/login`
- Body JSON :
```json
{ "email": "militant@example.com", "password": "ABC123" }
```
- Où `password` est la **Carte PASTEF** en général (ou la CNI si pas de carte).
- Réponse :
```json
{ "data": { "accessToken": "<JWT>" } }
```
- + cookie HTTP-only `refresh_token` (géré par le navigateur, comme avant).
- Erreur : 401 si identifiants invalides.

Notes importantes :
- La 1ère connexion réussie “upgrade” immédiatement le mot de passe en hash argon2 (la valeur Carte PASTEF reste valide mais elle n’est pas stockée en clair dans `users`).
- Si un militant a à la fois un mot de passe “classique” ET une Carte PASTEF : les 2 marchent (le hash argon2 est vérifié en premier, sinon la Carte PASTEF/CNI agit comme “mot de passe initial”).

### 6.3 Rafraîchir le token
- `POST /auth/refresh` (utilise le cookie HTTP-only `refresh_token`)
- Même comportement qu’avant.

### 6.4 Obtenir l’utilisateur courant (et sa fiche carte membre)
- `GET /auth/me` (avec `Authorization: Bearer <accessToken>`)
- Réponse enrichie avec un bloc `militant` si lié à une adhésion :
```json
{
  "data": {
    "id": "uuid-user",
    "email": "militant@example.com",
    "roles": ["militant"],
    "lastLoginAt": "2026-08-14T10:00:00Z",
    "militant": {
      "adhesion_id": "uuid-adhésion",
      "nom": "Diallo",
      "prenom": "Aminata",
      "cni": "1234567890",
      "carte_pastef": "ABC123",
      "commissariat": "Numérique",
      "commissariat_scientifique_principal": "...",
      "commissariat_scientifique_secondaire": "...",
      "profile_photo_url": "https://...",
      "photo_url": "https://...",
      "tel_mobile": "771234567"
    }
  }
}
```

Références backend :
- Auth login/refresh/logout/me : [routes/auth.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/auth.py)
- Auth service (mot de passe initial/carte) : [services/auth.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/auth.py)
- Schema `MeResponse` : [schemas/auth.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/auth.py)

---

## 7) Module Articles / Publications

Un module complet “articles” est disponible sous le préfixe **`/api/v1/articles`**.
Il sépare clairement les routes **publiques** (pas de JWT) et les routes **protégées** (JWT + rôle membre/coordinateur/admin).

### 7.1 Configuration (`.env` à synchroniser au déploiement)
Le nombre max de pièces jointes par article est **programmable via `.env`** (valeur backend lue au démarrage) :

```dotenv
ARTICLE_MAX_ATTACHMENTS=5
ARTICLE_MAX_COVER_MB=8
ARTICLE_MAX_ATTACHMENT_MB=20
ARTICLE_ALLOWED_COVER_MIMES=image/jpeg,image/png,image/webp
ARTICLE_ALLOWED_ATTACHMENT_MIMES=application/pdf,image/jpeg,image/png,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

- Si tu dépasses `ARTICLE_MAX_ATTACHMENTS` → 400 `error.code="TOO_MANY_ATTACHMENTS"`
- Mime invalide → 400 `INVALID_MIME`
- Taille dépassée → 400 `FILE_TOO_LARGE`

### 7.2 Modèle Article (schémas réponse)

```ts
interface ArticleAttachment {
  id: string;
  article_id: string;
  file_url: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  order: number;
  created_at: string;
}

interface ArticleOut {
  id: string;
  title: string;
  summary: string | null;
  body: string;
  cover_url: string | null;
  status: "draft" | "published";
  commissariat: string | null;
  tags: string[];
  author_id: string;
  author?: {
    id: string;
    email: string;
    nom: string | null;
    prenom: string | null;
  } | null;
  attachments: ArticleAttachment[];
  view_count: number;
  likes_count: number;
  comments_count: number;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ArticleListResponse {
  total: number;
  page: number;
  page_size: number;
  items: ArticleOut[];
}
```

### 7.3 Endpoints PUBLICS (sans auth)

- `GET /api/v1/articles` : liste paginée articles PUBLIÉS (status=published)`
  - Query params : `page`, `page_size`, `q`, `commissariat`, `author_id`, `sort ∈ {latest,popular,oldest}`
  - Réponse : `ArticleListResponse`

- `GET /api/v1/articles/{article_id}` : détail article publié (+ incrémente view_count)
  - Réponse : `ArticleOut`

- `GET /api/v1/articles/{article_id}/comments` : commentaires paginés
  - Query : `page`, `page_size`
  - Réponse : `{ total, items: ArticleCommentOut[] }`

```ts
interface ArticleCommentOut {
  id: string;
  article_id: string;
  author_id: string;
  parent_id: string | null;
  body: string;           // "[supprimé]" si deleted=true et pas l'auteur
  deleted: boolean;
  created_at: string;
  updated_at: string;
}
```

### 7.4 Endpoints PROTÉGÉS (Bearer JWT)
Rôles autorisés : `militant` / `admin` / `comite_accueil` / `comite_directoire` / `coordinateur_commissariat` / `coordinateur_regional`.

- `GET /api/v1/articles/mine : mes articles
  - Query : `page`, `page_size`, `status ∈ {draft,published}`, `include_deleted=true/false`

- `POST /api/v1/articles` — multipart/form-data — création article`

| Champ Form | type | oblig. |
|---|---|---|
| title | string(3-255) | OUI |
| body | string | OUI |
| summary | string(0-500) | NON |
| status | `"draft"` \| `"published"` | NON (défaut draft) |
| commissariat | string | NON |
| tags | string : JSON array ou CSV | NON |
| cover | UploadFile | NON |
| attachments | File[] | NON (max N) |

- `PATCH /api/v1/articles/{article_id}` — multipart — modifier article (auteur seul OU admin)
  - mêmes champs optionnels + `remove_attachment_ids` (JSON array ou CSV, UUIDs à supprimer)
  - règle net-count : `(existants - remove_ids) + nouveaux <= ARTICLE_MAX_ATTACHMENTS`

- `DELETE /api/v1/articles/{article_id}` — soft delete (auteur seul OU admin

### 7.5 Likes

- `POST /api/v1/articles/{article_id}/like` (toggle on)
- `DELETE /api/v1/articles/{article_id}/like` (toggle off)
- `GET /api/v1/articles/{article_id}/like/me` → statut like + total likes

Tous retournent :
```ts
interface LikeResponse { liked: boolean; likes_count: number }
```

### 7.6 Commentaires (protégés)

- `POST /api/v1/articles/{article_id}/comments` — JSON
```ts
{ body: string; parent_id?: string }
```

- `PATCH /api/v1/articles/comments/{comment_id}` — JSON `{ body }` — éditer (auteur/admin)
- `DELETE /api/v1/articles/comments/{comment_id}` — soft delete (auteur/admin)

### 7.7 Erreurs spécifiques articles — codes stables

| HTTP | code | cause |
|---|---|---|
| 400 | `TOO_MANY_ATTACHMENTS` | > Nb max atteints |
| 400 | `INVALID_MIME` | type MIME interdit |
| 400 | `FILE_TOO_LARGE` | fichier trop gros |
| 400 | `INVALID_STATUS` | status hors draft/published |
| 400 | `INVALID_PARENT_COMMENT` | parent_id inexistant / mauvais article |
| 403 | `FORBIDDEN` | pas auteur ni admin |
| 404 | `NOT_FOUND` | article/commentaire introuvable |

---

## 8) Infos utiles (prefixes, auth, rôles)

### 8.1 Préfixes / routes
- Toutes nos routes sont préfixées : `/api/v1/...`
- Auth : `/api/v1/auth/...`
- Adhésions (public) : `/api/v1/adhesions`
- Admin : `/api/v1/admin/...`
- Validation accueil : `/api/v1/accueil/adhesions/...`
- Validation directoire : `/api/v1/directoire/adhesions/...`
- Rejet (accueil + directoire) : `/api/v1/adhesions/{id}/rejeter` (protégé)
- Militants : `/api/v1/militants/...`
- Articles : `/api/v1/articles/...`
- Geo : `/api/v1/geo/...`
- Santé : `/api/v1/health/...`
- Users (admin users) : `/api/v1/users/...`

### 8.2 Rôles actuellement reconnus (backend)
- `admin`
- `comite_accueil`
- `comite_directoire`
- `militant` (nouveau)
- `coordinateur_commissariat` (enum présent, scope de permissions pas encore implémenté)
- `coordinateur_regional` (enum présent, pas encore implémenté)
- `user` (générique)

### 8.3 Auth sur endpoints protégés
- Header : `Authorization: Bearer <accessToken>`
- Certains endpoints (admin, accueil, directoire, militants stats) nécessitent les rôles correspondants → sinon 403 avec `error.code="FORBIDDEN"`.

### 8.4 OpenAPI / Docs
Si l’API tourne en local, consulte :
- `/docs` (Swagger UI)
- `/redoc` (Redoc)
Cela liste tous les endpoints + schémas de body/response à jour.

---

## Checklist rapide côté frontend (ce que tu peux faire maintenant)

- [ ] Sur création adhésion, afficher les messages erreurs via `error.code` (`DUPLICATE_EMAIL`, `DUPLICATE_CNI`, `DUPLICATE_CARTE_ELECTEUR`, `VALIDATION_ERROR`).
- [ ] Ajouter l’upload `profile_photo` au formulaire adhésion.
- [ ] Admin : boutons “Modifier infos” + “Remplacer fichiers” + “Supprimer (soft delete)”.
- [ ] Workflow complement : permettre à l’accueil de `valider` depuis `complement`.
- [ ] Écrans stats militants : `/count`, `/stats/*`, `/timeseries`, `/hierarchy`.
- [ ] Écran “carte membre” en suivi `/suivi` : utiliser `GET /militants/lookup?email=...` (ou autre critère).
- [ ] Écran “espace membre” : login `email + carte pastef`, ensuite `GET /auth/me` pour afficher profil/photo/carte.
- [ ] Module articles publiques : liste, détail, commentaires (GET public + like/comment connectés).
- [ ] Module articles espaces membre : créer/éditer/supprimer article + uploads, likes, commentaires (réponses), `/articles/mine`.

Fin du changelog.
