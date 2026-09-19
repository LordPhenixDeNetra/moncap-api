# UPDATE MONCAP API — Journal des modifications

Date : 19 septembre 2026 (3 modifications)  
Auteur : Session TRAE  
Objets :
  [A] Mise en oeuvre de la règle « Le membre qui adhère ne paie pas le mois courant »
  [B] Résolution d'un bug 500 masqué sur création d'article (article créé + erreur HTTP 500)
  [C] Emails de notification sur les changements de statut des articles

---

## [C] NOUVEAUTÉ — Emails de notification sur les statuts d'articles

### But
Pour chaque **changement de statut** d'un article, un email est envoyé **à l'auteur de l'article** (détenteur du compte User lié à `article.author_id`).  
Cas particulier : quand l'auteur **re-soumettra** son article après un rejet ou une demande de corrections, un email est envoyé **à TOUT le staff de modération** (admins + modérateurs) pour notification dans la file d'attente.

### Activation / Désactivation
- **Globale** : toggle `mail_enabled=true/false` dans `.env` (défaut = `false`). Si `false`, **aucun email n'est envoyé, aucune erreur, aucun log** (pattern `send_email_best_effort`).
- **SMTP** : `smtp_host`, `smtp_port`, `smtp_use_tls/ssl`, `smtp_username/password`, `mail_from`, `mail_from_name` (même config que les mails adhésions/paiements).

### Configuration emails STAFF (destinataires notifications resoumission)
Pas de variable `.env` ajoutée. La liste est **dynamique via BDD** (source de vérité = rôles des utilisateurs) :
- Requête : `SELECT DISTINCT email FROM users u JOIN user_roles r ON r.user_id=u.id WHERE r.role IN ('admin','moderateur')`
- Helper : `UserRepository.list_staff_emails()` ([users.py L76-L102](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/users.py#L76-L102))
- Cas limites : emails vides / nulls filtrés ; doublons supprimés (insensible à la casse).

### Destinataire AUTEUR (résolution email)
1. `article.author.email` via relation `Article.author` (eager-loadée par `ArticleRepository.get_by_id` → `selectinload(Article.author)`, donc pas de lazy-load hors session).
2. Helper : `resolve_author_email(article)` dans [article_mail_templates.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py).
3. Si email absent → **envoi silencieusement ignoré** (pas d'erreur HTTP, pas d'exception).

### Transitions déclenchant un email

| # | Endpoint (route) | Trigger (changement statut) | Destinataire | Template utilisé |
|---|---|---|---|---|
| C1 | `POST /api/v1/articles` (création) | statut final = `waiting_validation` | auteur | [build_article_submitted_for_validation](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py#L69-L125) |
| C2 | `PATCH /api/v1/articles/{id}` (édition) | `avant → waiting_validation` **ET** `avant != waiting_validation` | auteur | idem C1 |
| C3 | `PATCH /api/v1/articles/{id}` (édition) | `avant ∈ {rejected, changes_requested} → waiting_validation` (resoumission après feedback) | **staff (admins + moderateurs)** | [build_article_resubmitted_after_feedback](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py#L259-L320) — envoi UN mail PAR destinataire via `BackgroundTasks` |
| C4 | `POST /api/v1/articles/{id}/approuver` | `X → published` | auteur | [build_article_published](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py#L128-L182) — inclut nom du modérateur + motif (commentaire) si fourni |
| C5 | `POST /api/v1/articles/{id}/rejeter` | `X → rejected` | auteur | [build_article_rejected](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py#L185-L234) — inclut **toujours** le `validation_motif` |
| C6 | `POST /api/v1/articles/{id}/demander-corrections` | `X → changes_requested` | auteur | [build_article_changes_requested](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py#L237-L296) — inclut **toujours** le `validation_motif` |

Les status `draft` / transitions sans changement de statut → **aucun email** (pas d'annonce pour un brouillon).

### Contenu / Format des emails
- **Format** : toujours `subject` (prefix `[MONCAP]`) + version texte brut (`text`) + version HTML (`html`) léger (pas de logo ni QR code).
- **Champs inclus par email auteur** : titre article, résumé, statut, lien espace auteur, lien public (si publié), commissariat, nom/email du modérateur ayant agi (si applicable).
- **Champs inclus par email staff** : titre article, nom auteur, commissariat, lien vers la file d'attente modération (`/admin/articles/validation`).

### Robustesse / Non-régression
- **Exécution hors cycle requête** : tous les envois sont poussés dans `FastAPI.BackgroundTasks.add_task(send_email_best_effort, ...)` → jamais de blocage de la réponse HTTP, jamais de 500 si SMTP timeout / down.
- **Gestion d'échec** : `send_email_best_effort` attrape **toutes** exceptions et retourne silencieusement → la création/modification d'article **jamais impactée** par un mail en échec.
- **Déclenchement APRÈS commit** : les lectures (email du validator via `UserRepository.get_by_id`, staff emails via `list_staff_emails`) sont faites **après** un `commit` réussi + relecture ORM → emails toujours sur l'état final réellement écrit en base.

### Fichiers modifiés / ajoutés
| Fichier | Type | Rôle |
|---|---|---|
| [app/services/article_mail_templates.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article_mail_templates.py) | NOUVEAU | 5 templates emails + helpers `resolve_author_email`, `_status_label`, génération liens public/owner/modération. |
| [app/repositories/users.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/users.py#L76-L102) | ÉVOLUTION | `list_staff_emails(roles=None)` → emails uniques des admins/modérateurs. |
| [app/api/v1/routes/articles.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/articles.py) | ÉVOLUTION | Ajout paramètre `background_tasks: BackgroundTasks` sur les 5 endpoints concernés (C1, C2, C4, C5, C6) + trigger conditionnel selon transition statut après commit. |

### Vérifications
- `python -m compileall` sur les fichiers modifiés → **0 erreur syntaxe**.
- Aucune migration Alembic nécessaire (pas de colonne/table nouvelle : la relation `author` sur `ArticleComment` est ORM-only ajoutée [B] + nouvelle méthode query helper `list_staff_emails`).
- Rétro-compatibilité front : **100%** (aucun changement de schéma entrée/sortie des endpoints ; seuls des effets de bord `BackgroundTasks` sont ajoutés).

---

## [B] BUG CORRIGÉ — Création article : 500 masqué (article créé, réponse en erreur)

### Symptôme
Côté frontend, sur création d'un article via `POST /api/v1/articles` :
- L'article est BIEN persisté en base (apparaît dans la liste / la BDD)
- Mais le front reçoit une erreur 500 (parfois masquée par le middleware CORS : le navigateur affiche « Failed to fetch » ou erreur opaque, pas de JSON)

### Cause racine — Double problème

**Problème #1 — CRITIQUE** — ORM relations non chargées après commit :  
[ArticleService.create_article](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article.py#L149-L238) faisait :
1. Création + flush
2. Commit
3. `await session.refresh(article)` → ne recharge PAS les relations `author` et `attachments`
4. Route fait `ArticleOut.model_validate(art)` → Pydantic tente de lire `art.author` / `art.attachments` → **lazy-load SQL hors session → DetachedInstanceError → 500**

**Problème #2** — ordre d'exécution :  
Les pièces jointes étaient insérées *après* l'article flush mais `add_attachments` pouvait échouer partiellement (rollback sur cette partie mais pas sur l'article si ça arrive à cheval sur le commit). Et les compteurs (`likes_count`, `comments_count`) n'étaient pas initialisés à la création (ils restaient null / pas cohérents si l'on n'appelait pas update).

### Correctifs apportés

| Fichier | Lignes | Type | Description |
|---|---|---|---|
| [app/services/article.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article.py#L149-L238) | L149-L238 | Bugfix + refonte | `create_article` : 1) vérifs MIME/taille → 2) couverture → 3) article.flush → 4) insertions attachments.flush → 5) `set_counters` → 6) UN commit → 7) `get_by_id(include_deleted=True)` qui fait `selectinload(author, attachments)` → **Pydantic a toutes ses relations, plus de lazy-load** |
| [app/services/article.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article.py#L327-L440) | L327-L440 | Cohérence | `update_article` : `set_counters` déplacé AVANT le commit unique (déjà correct en fin, mais sécurisation complémentaire + relecture `get_by_id` déjà présente) |
| [app/services/article.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/article.py#L485-L522) | L485-L522 | Bugfix | `create_comment` : même pattern — `session.commit()` puis relecture via `comments.get_by_id()` (qui a maintenant `selectinload(author)`) au lieu de `session.refresh(c)` |
| [app/models/article.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/article.py#L88-L108) | L108 | ORM ajout | Ajout de la relation `author` manquante sur `ArticleComment` (le schéma `ArticleCommentOut.author: ArticleAuthorOut` la réclamait mais l'ORM n'avait pas la relation — bug silencieux, `author` restait `null` ou faisait lazy-load) |
| [app/repositories/article.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/article.py#L349-L389) | L349-L389 | Repository | `ArticleCommentRepository._base_loads` : ajout de `selectinload(ArticleComment.author)` sur `get_by_id` et `list` → plus aucun lazy-load après commit sur les commentaires |

### Tests / Vérifications
- `python -m compileall` sur les 5 fichiers modifiés : **OK, 0 erreur de syntaxe**
- Suite pytest (4 passés / 3 échoués) : les 3 échecs sont **pré-existants non liés** (`UserRepository.create_user()` réclame `nom`/`prenom` dans `test_auth.py`, `test_rbac.py`) ; les tests articles/adhésions passent.
- Aucune migration Alembic requise (pas de colonne / contrainte nouvelle — l'ORM ajoute une `relationship`, rien en BDD).

---

## [A] RÈGLE MÉTIER APPLIQUÉE

---

## 1. RÈGLE MÉTIER APPLIQUÉE

**Ancienne règle par défaut** : `jour_15`
- Adhésion validée ≤ jour 15 du mois → cotisation du mois courant facturée
- Adhésion validée > jour 15 → mois suivant (mois courant offert partiellement)

**Nouvelle règle par défaut** : `mois_suivant`
- Quel que soit le jour de validation dans le mois → **le mois de l'adhésion est systématiquement OFFERT**
- Première facturation de cotisation mensuelle = **le mois suivant la validation**

La règle reste **configurable à la volée via BDD** (table `parametres_paiement`, code `regle_date_premiere_cotisation`, champ `valeur_texte` = `mois_suivant` | `jour_XX`). Seule la VALEUR PAR DÉFAUT (fallback + seed initial) change.

---

## 2. FICHIERS MODIFIÉS

### 2.1 — Règle de première cotisation (backend métier)

| Fichier | Lignes | Changement |
|---|---|---|
| [app/services/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiements.py#L66-L73) | L73 | Fallback hardcodé si BDD vide : `return "jour_15"` → `return "mois_suivant"` |
| [app/services/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiements.py#L133-L138) | L135-L137 | `seed_defaults_if_empty()` : libellé + `valeur_texte="jour_15"` → `valeur_texte="mois_suivant"` + libellé explicite |

### 2.2 — Correction de BUG CRITIQUE : création intempestive cotisation mois courant

**Constat** : les endpoints `/cotisation/etat` (public, appelé après scan QR) et `/mon-compte/cotisation-du-mois` (adherent connecté) appelaient `creer_cotisation(adhesion.id, today.year, today.month)` en aveugle s'il n'y avait pas de ligne. Résultat : un nouvel adhérent validé ce mois-ci se voyait attribuer une cotisation DU MOIS EN COURS, en violation de la règle.

**Correction apportée** : les deux endpoints déterminent d'abord `(premiere_cotisation_annee, premiere_cotisation_mois)` via le même service (`ParametresPaiementService.determiner_premier_mois_cotisation`) utilisé lors de la validation d'adhésion. Puis :
- Si 1ère cotisation > mois en cours → **`est_premier_mois_offert = true`**, on crée (si besoin) la cotisation au **mois de première facturation**, pas au mois courant ; `montantDu = 0`
- Sinon → `generer_pour_adherent_suite_validation()` pour aligner avec le flow de validation classique

| Fichier | Lignes | Changement |
|---|---|---|
| [app/api/v1/routes/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py#L352-L489) | L360-L443 | Endpoint `GET /paiements/cotisation/etat` (scan QR public) — logique refondue |
| [app/api/v1/routes/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py#L472-L490) | L487-L489 | 3 nouveaux champs dans la réponse JSON du endpoint public |
| [app/api/v1/routes/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py#L907-L1062) | L932-L1062 | Endpoint `GET /mon-compte/cotisation-du-mois` (espace adhérent JWT) — logique refondue + 3 nouveaux champs |

### 2.3 — Nouveaux champs exposés au frontend (rétrocompatibles)

Ajoutés au schéma `AdherentEtatCotisationFlatOut` utilisé par les 2 endpoints :

| Champ (camelCase dans JSON) | Type | Valeur |
|---|---|---|
| `estPremierMoisOffert` | `boolean` (défaut false) | `true` = le mois courant est gratuit pour cet adhérent |
| `premiereCotisationAnnee` | `int \| null` | Année de la 1ère cotisation mensuelle réellement due |
| `premiereCotisationMois` | `int \| null` | Mois de la 1ère cotisation mensuelle réellement due |

Fichier : [app/schemas/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/paiements.py#L195-L197)

### 2.4 — Documentation frontend mise à jour

| Fichier | Lignes | Changement |
|---|---|---|
| [FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md#L206) | L206 | Exemple JSON `valeurTexte: jour_15` → `mois_suivant` |
| [FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md#L63-L70) | L63-L70 | Nouvelle section « RÈGLE LOGIQUE FRONTEND #2 — MOIS DE L'ADHÉSION OFFERT » |
| [GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md#L292) | L292 | Paragraphe règle première cotisation : `mois_suivant` devient la valeur par défaut présentée |
| [GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md#L475) | L475 | Log seed attendu : `regle=jour_15` → `regle=mois_suivant` |

---

## 3. ACTION ATTENDUE CÔTÉ FRONTEND

### Rien de bloquant — le backend renvoie déjà `montantDu = 0` si premier mois offert.

### Améliorations UX recommandées (2 ajustements)

**Ajustement 1 — Bandeau d'information**
Si `estPremierMoisOffert === true`, afficher un texte explicite :
> [OK] Votre premier mois de cotisation est offert. Prochaine échéance : `<Mois> <Année>` (utiliser `premiereCotisationMois` + `premiereCotisationAnnee`).

**Ajustement 2 — Bouton « Payer »**
Désactiver / masquer le bouton de paiement cotisation si `montantDu === 0`.

Règle de garde déjà existante à conserver :
- Si `paiementAdhesionConfirme === false` → rediriger vers paiement des FRAIS D'ADHÉSION INITIAUX (pas la cotisation).

---

## 4. BDD DÉJÀ EXISTANTE — PATCH MANUEL REQUIS

Si une BDD MONCAP contient déjà une ligne active `regle_date_premiere_cotisation` avec l'ancienne valeur `jour_15`, le seed automatique NE remplace PAS une ligne existante (conformité au design). Il faut appliquer un patch SQL :

```sql
-- 1) Fermer l'ancienne règle à la veille
UPDATE parametres_paiement
SET date_fin_effet = CURRENT_DATE - INTERVAL '1 day'
WHERE code = 'regle_date_premiere_cotisation' AND date_fin_effet IS NULL;

-- 2) Insérer la nouvelle règle active dès aujourd'hui
INSERT INTO parametres_paiement (id, code, libelle, montant_fcfa, valeur_texte, devise, date_effet, created_at, updated_at)
VALUES (
  gen_random_uuid(),
  'regle_date_premiere_cotisation',
  'Règle première cotisation (mois_suivant = l''adhésion du mois courant ne paie pas le mois en cours, première cotisation le mois suivant)',
  NULL,
  'mois_suivant',
  'XOF',
  CURRENT_DATE,
  NOW(),
  NOW()
);
```

OU BIEN via l'interface admin : `POST /api/v1/admin/parametres-paiement` avec `code=regle_date_premiere_cotisation`, `valeur_texte="mois_suivant"`, `date_effet=aujourd'hui` (le backend ferme automatiquement la règle précédente).

---

## 5. FICHIERS NON-MODIFIÉS (intacts)

- Logique `generer_pour_adherent_suite_validation` appelée après validation d'adhésion — inchangée, elle utilise déjà la règle venant de BDD.
- Script cron `generate_monthly_dues` — inchangé, il génère le mois cible pour TOUS les adhérents validés (ceux pour qui le mois en cours est leur 1er mois facturé seront bien concernés).
- Endpoints paiement (`initier-public-par-adhesion`, webhook Kopar) — inchangés.
- Modèles SQLAlchemy — inchangés (pas de migration à créer).

---

## 6. VÉRIFICATION (À FAIRE MANUELLEMENT APRÈS DÉPLOIEMENT)

1. Nouveau seed BDD vide → `regle_date_premiere_cotisation.valeur_texte = 'mois_suivant'`.
2. Endpoint `/api/v1/paiements/parametres-public` → bien renvoyer `valeurTexte: "mois_suivant"`.
3. Créer une adhésion + valider les 2 étapes le jour J → appeler `/cotisation/etat?adh=...` → `estPremierMoisOffert: true`, `montantDu: 0`, `premiereCotisationMois: (mois J+1)`.
4. Même adhérent via `/mon-compte/cotisation-du-mois` (après création compte JWT) → mêmes 3 champs.
5. Attendre / simuler le 1er du mois suivant → `generate_monthly_dues` créé bien une ligne cotisation pour cet adhérent (1er paiement réel).
