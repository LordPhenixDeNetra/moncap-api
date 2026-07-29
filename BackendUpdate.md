Voici un message complet à destination du développeur frontend :

---

## 📋 Mise à jour API — moncap-api

Bonjour,

Voici un récapitulatif de toutes les nouveautés disponibles sur l'API. Merci de mettre à jour vos implémentations en conséquence.

---

### 🔐 Authentification

**Base URL :** `/api/v1/auth`

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/login` | Connexion — retourne un `access_token` + cookie `refresh_token` |
| `POST` | `/auth/refresh` | Rafraîchir le `access_token` via le cookie |
| `GET` | `/auth/me` | Infos de l'utilisateur connecté (id, email, nom, prénom, rôles) |
| `POST` | `/auth/logout` | Déconnexion |

---

### 👥 Gestion des Utilisateurs *(admin uniquement)*

**Base URL :** `/api/v1/users`
**Header requis :** `Authorization: Bearer <access_token>`
**Rôle requis :** `admin`

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/users` | Lister tous les utilisateurs |
| `POST` | `/users` | Créer un utilisateur |
| `GET` | `/users/{user_id}` | Détail d'un utilisateur |
| `PATCH` | `/users/{user_id}` | Modifier (email, mot de passe, nom, prénom, rôles) |
| `DELETE` | `/users/{user_id}` | Supprimer un utilisateur |

**Corps de création (`POST /users`) :**
```json
{
  "email": "user@example.com",
  "password": "motdepasse123",
  "nom": "Diop",
  "prenom": "Moussa",
  "roles": ["comite_accueil"]
}
```

**Rôles disponibles :**
- `admin`
- `comite_accueil`
- `comite_directoire`
- `user`

**Réponse utilisateur :**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "nom": "Diop",
    "prenom": "Moussa",
    "roles": ["comite_accueil"],
    "createdAt": "2026-07-29T...",
    "updatedAt": "2026-07-29T...",
    "lastLoginAt": null
  }
}
```

---

### ✅ Validation des Adhésions — Double validation

Le processus de validation est maintenant en **2 étapes obligatoires**.

**Statuts possibles d'une adhésion :**
```
en_attente → validee_accueil → validee
                             ↘ rejetee (à n'importe quelle étape)
```

| Méthode | Endpoint | Rôle requis | Description |
|---|---|---|---|
| `PATCH` | `/api/v1/accueil/adhesions/{id}/valider` | `comite_accueil` | 1ère validation |
| `PATCH` | `/api/v1/directoire/adhesions/{id}/valider` | `comite_directoire` | Validation finale |
| `PATCH` | `/api/v1/adhesions/{id}/rejeter` | `comite_accueil` ou `comite_directoire` | Rejeter |
| `PATCH` | `/api/v1/admin/adhesions/{id}` | `admin` | Demander complément / rejeter |
| `PATCH` | `/api/v1/admin/adhesions/{id}/payment` | `admin` | Confirmer le paiement |

---

### 🌍 Données Géographiques

**Base URL :** `/api/v1/geo`
*(Pas d'authentification requise)*

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/geo/pays` | Lister tous les pays (189 pays ISO) |
| `GET` | `/geo/pays?continent=Afrique` | Filtrer par continent |
| `GET` | `/geo/regions` | Régions du Sénégal |
| `GET` | `/geo/regions/{id}/departements` | Départements d'une région |
| `GET` | `/geo/departements/{id}/communes` | Communes d'un département |

**Continents disponibles :** `Afrique`, `Europe`, `Amérique`, `Asie`, `Océanie`

**Réponse pays :**
```json
{
  "data": [
    { "id": "uuid", "code": "SN", "nom": "Sénégal", "continent": "Afrique" },
    { "id": "uuid", "code": "FR", "nom": "France", "continent": "Europe" }
  ]
}
```

---

### 📝 Formulaire d'adhésion — Nouveaux champs Diaspora

Le formulaire d'adhésion supporte maintenant deux cas :

**Adhérent au Sénégal (`est_diaspora: false`) :**
- Remplir : `region_domicile_id`, `departement_domicile_id`, `commune_domicile_id`
- Remplir : `region_militantisme_id`, `departement_militantisme_id`, `commune_militantisme_id` (optionnel)

**Adhérent de la diaspora (`est_diaspora: true`) :**
- Remplir : `pays_domicile_id` (FK vers `/geo/pays`), `ville_domicile`
- Remplir : `pays_militantisme_id`, `ville_militantisme`
- Les champs région/département/commune sont ignorés

---

### 📊 Export des données *(admin)*

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/admin/adhesions/export.csv` | Export CSV |
| `GET` | `/api/v1/admin/adhesions/export.xlsx` | Export Excel |
| `GET` | `/api/v1/admin/adhesions` | Liste avec filtres |

---

> ⚠️ **Important :** Toutes les routes protégées nécessitent le header `Authorization: Bearer <access_token>`. Le `access_token` s'obtient via `POST /api/v1/auth/login`.