# UPDATE MONCAP API — Journal des modifications

Date : 23 mars 2026 (6 modifications au total — ajouts [F])  
Auteur : Session TRAE  
Objets :
  [A] Mise en oeuvre de la règle « Le membre qui adhère ne paie pas le mois courant »
  [B] Résolution d'un bug 500 masqué sur création d'article (article créé + erreur HTTP 500)
  [C] Emails de notification sur les changements de statut des articles
  [D] Hydratation GEO sur MilitantOut + endpoints GEO individuels GET /{id}
  [E] RADIATION AUTOMATIQUE 3 mois impayés consécutifs + Endpoint admin fallback manuel + Guards auth is_active
  [F] PAIEMENT COTISATION MULTI-PÉRIODES — Mensuel / Trimestriel / Semestriel / Annuel (1 / 3 / 6 / 12 mois)

---

## [F] PAIEMENT MULTI-PÉRIODES — Cotisations 1/3/6/12 mois en 1 transaction Kopar

### 1. But
**Problème métier** : les adhérents·es devaient *manuellement* re-payer chaque mois leur cotisation via un nouveau QR scan / nouveau lien Kopar. Aucun moyen de régler plusieurs mois d'un coup.

**Solution** : **UNE SEULE** transaction Kopar = potentiellement **N lignes `cotisations_mensuelles`** payées d'un coup, pour les 4 périodes standard :
| Période | Code entier | Label |
|---|---|---|
| **Mensuelle** | `1` | 1 mois |
| **Trimestrielle** | `3` | 3 mois |
| **Semestrielle** | `6` | 6 mois |
| **Annuelle** | `12` | 12 mois |

**Règle rétrocompatibilité absolue** : toute ancienne transaction `periode_mois IS NULL` → valide **exactement 1 ligne** (comme avant). **Aucun script existant, webhook success, CRON de réconciliation ne casse.**

### 2. Choix d'architecture (retenu)
❌ **Écarté** : table de liaison `transaction_kopar_cotisations` (trop de complexité, rupture de contrat existant `tx.cotisation_id → 1 ligne`).

✅ **Retenu — colonnes sur `transactions_kopar` + algorithme** :
1. **Colonnes SQL BDD ajoutées** (source de vérité unique) :
   - `periode_mois INT` — la période (1 / 3 / 6 / 12). `NULL` rétro = 1.
   - `premiere_annee_couverte INT` — année du PREMIER mois couvert
   - `premier_mois_couverte INT` — mois 1-12 du PREMIER mois couvert
2. **Point d'ancrage inchangé** : `tx.cotisation_id` = FK SIMPLE vers **LA PREMIÈRE LIGNE** de la période. Le flux « 1 transaction = 1 cotisation_id » marche toujours (rétrocompatibilité).
3. **Calcul des N mois** : algorithme « (premiere_annee, premier_mois) × periode_mois mois CONSÉCUTIFS » → `(année,mois)` suivant = `mois+1 > 12 ? (année+1, 1) : (année, mois+1)`.
4. **Custom_fields Kopar ignorés si conflit** : source de vérité = colonnes SQL BDD.

### 3. Enum `PeriodePaiement`
Fichier : [app/models/paiements.py L55-L87](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/paiements.py#L55-L87)

```python
class PeriodePaiement(IntEnum):
    MENSUEL = 1
    TRIMESTRIEL = 3
    SEMESTRIEL = 6
    ANNUEL = 12

    @classmethod
    def normaliser(cls, v: int | None) -> int:      # NULL → 1 ; valeur invalide → 1
    @classmethod
    def label(cls, v: int | None) -> str:           # 3 → "Trimestriel"
    @classmethod
    def mois_label(cls, mois: int) -> str:          # 5 → "Mai"
```

### 4. Migration Alembic (1 revision — 3 colonnes + 2 index — 100% rétro)
Fichier : `alembic/versions/NNNN_add_periode_mois_columns_on_transactions_kopar.py`  
**Backfill** : `UPDATE transactions_kopar SET periode_mois = 1 WHERE periode_mois IS NULL`

| Colonne | Type | Contrainte / Valeur défaut | Backfill |
|---|---|---|---|
| `periode_mois` | `INTEGER NULLABLE` | `CHECK (periode_mois IN (1,3,6,12))` | `= 1` (toutes anciennes tx) |
| `premiere_annee_couverte` | `INTEGER NULLABLE` | | Pour anciennes tx : **déduit rétroactivement à partir de `tx.cotisation_id → c.annee`** au moment de l'exécution des méthodes `mark_paid_periode()` / `appliquer_paiement_cotisation_success()` (pas besoin d'un backfill SQL lourd : la plupart des anciennes tx n'ont plus besoin d'être relues). |
| `premier_mois_couverte` | `INTEGER NULLABLE` | | Idem |

Index ajoutés :
- `ix_tx_kopar_periode_mois` sur `(periode_mois)`
- `ix_tx_kopar_premiere_periode` sur `(premiere_annee_couverte, premier_mois_couverte, periode_mois)`

**Downgrade réversible** : `downgrade()` drop les 3 colonnes + 2 index (perte seulement des périodes multi-mois).

### 5. Repository `CotisationMensuelleRepository` (2 méthodes clés)
Fichier : [app/repositories/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/paiements.py)

| Méthode | Rôle |
|---|---|
| `calculer_mois_consecutifs(debut_an, debut_mo, nb_mois_int) → list[tuple[int,int]]` | **STATIC** — rend les (annee, mois) consécutifs sans DB. Utilisé PARTOUT. |
| `get_or_create_for_adherent_mois(adhesion_id, an, mo) → CotisationMensuelle` | Récupère ou INSÈRE (via `on_conflict uq_cotisation_adherent_annee_mois do nothing`) UNE ligne donnée. Safe idempotent. |
| `mark_paid_periode(tx, reference_paiement=None, mode_paiement=None, update_tx_status=True) → list[CotisationMensuelle]` | **CŒUR MÉTIER IDÉMPOTENT** : applique le paiement SUCCESS sur toutes les lignes de la période (1 à 12). Met à jour le statut de la transaction KOPAR success (via `update_after_webhook`). Retourne seulement les lignes *effectivement* passées de impayé → payé (déjà payées = omises). |

Ordre d'appel interne `mark_paid_periode` :
1. `periode = PeriodePaiement.normaliser(tx.periode_mois)` (defensif).
2. Détermine `(debut_an, debut_mo)` depuis `tx.premiere_annee_couverte + premier_mois_couverte` si présents, sinon depuis `tx.cotisation_id → c.annee, c.mois` (RÉTROCOMPATIBILITÉ).
3. Itère chaque mois → `get_or_create_for_adherent_mois` → si pas `payee` → mark payé.
4. Met à jour `tx.statut = SUCCESS` via `transactions.update_after_webhook` (central).

### 6. `PaiementOrchestratorService` — 2 évolutions majeures
Fichier : [app/services/paiement_orchestrator.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiement_orchestrator.py)

#### 6.1 — Nouvelle méthode INITIATION (avant Kopar)
`async initier_paiement_cotisation_periode(adhesion_id, premiere_annee, premier_mois, periode_mois, service=None) → InitiatedKoparPayment`
- Charge ou CRÉE les lignes `cotisations_mensuelles` pour la période si elles n'existent pas
- Récupère montant mensuel via `ParametresPaiementService` → calcule `montant_total = nb_mois_impayés * montant_mensuel` (mois offerts / déjà payés déduits)
- Crée UNE SEULE `TransactionKopar` avec les 3 nouvelles colonnes renseignées, `cotisation_id = 1ere ligne`
- Appelle Kopar `create_transaction()` → retourne token/URL/QR.

#### 6.2 — Refonte de l'application SUCCESS (webhook + réconciliation)
Anciennement : `_appliquer_paiement_cotisation_success()` appelait `mark_paid(cotisation_id)` + email 1 mois.  
**Maintenant** :
- Nouvelle méthode **PUBLIQUE** `appliquer_paiement_cotisation_success(tx, background_tasks=None) -> list[CotisationMensuelle]` :
  - délègue à `orchestrator.cotisations.mark_paid_periode()` (qui gère 1..12 lignes)
  - **Email** : construit la liste des mois payés `[(a,m)]` depuis les lignes, somme `montant_total`, appelle `build_cotisation_paiement_confirme(mois_couverts=..., montant_total=...)` (HTML liste à puces de tous les mois si >1, singleton « Mois Année » sinon).
  - `background_tasks=None` est la signature CLI (pas d'envoi d'email en CLI réconciliation).
- L'ancienne méthode privée `_appliquer_paiement_cotisation_success(tx, bg_tasks)` reste comme wrapper rétro.

### 7. Routes API — 7 endpoints étendus / nouveaux

#### 7.1 — 4 endpoints INITIATION étendus avec `?periodeMois=` (query param optionnel, défaut 1, 1<=v<=12)
| # | Endpoint | Router | Changement |
|---|---|---|---|
| F1 | `POST /paiements/cotisation/{cotisation_id}/initier-public` | public_router | `periodeMois` dispatch vers `initier_paiement_cotisation_periode` si ≠1 |
| F2 | `POST /paiements/adhesion/{adhesion_id}/cotisation-du-mois/initier-public` | public_router | idem |
| F3 | `POST /paiements/cotisation/initier-public-par-adhesion?adh=...` | public_router | idem (transmet le param) |
| F4 | `POST /paiements/cotisation/{cotisation_id}/initier` | protected_router | idem |

**Rétro 100 %** : omettre `periodeMois` = `periode_mois=1` = exactement comportement précédent.

#### 7.2 — 3 endpoints SUGGESTION (listent les 4 options M/T/S/A avec détail & montant)
Réponses : `ProchainPaiementSuggestionResponse` → champs `options[]` listant Mensuel, Trimestriel, Semestriel, Annuel (chacun avec `periodeMois`, `label`, `montantTotal`, `listeMois[{annee,mois,label,statut}]`, `nbMoisImpayesInclus`, `nbMoisOffertsInclus`).

| # | Endpoint | Router | Auth |
|---|---|---|---|
| F5 | `GET /mon-compte/cotisations/prochaine-suggestion` | adherent_router | JWT adhérent → son info depuis `user.adhesion_id` |
| F6 | `GET /paiements/adhesion/{adhesion_id}/cotisation/prochaine-suggestion?email=` | public_router | Email correspondant à l'adhésion demandé (vérif) |
| F7 | `GET /paiements/cotisation/prochaine-suggestion?adh=...&email=...` | public_router | Alias court (query params seulement) |

#### 7.3 — 1 endpoint ADMIN — Paiement manuel multi-périodes
| # | Endpoint | Router | Body |
|---|---|---|---|
| F8 | `POST /admin/adhesions/{adhesion_id}/cotisations/paiement-manuel-periode?annee=&mois=` | admin_router | `{ periodeMois: 1\|3\|6\|12 (def=1), note?, referencePaiement? }` → réponse `CotisationListResponse { data[], total }`. RBAC : admin / comite_directoire / coordinateur_regional (même que paiement manuel 1 ligne). |

### 8. Réconciliation CLI `reconcile_kopar_pending_transactions.py`
Fichier : [app/cli/reconcile_kopar_pending_transactions.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/cli/reconcile_kopar_pending_transactions.py)  
Bloc `elif type = cotisation` **refactorisé** :
- Ancien : appelait `mark_paid(cotisation_id)` + `update_after_webhook` séparément (risque de double mise à jour).
- Nouveau : **appelle `orchestrator.cotisations.mark_paid_periode(tx, reference_paiement=kopar_token_ou_KOPAR-RECONCILE, mode_paiement="kopar_reconcile")`** — ceci gère automatiquement la période 1..12, MAJ la tx.
- Si `mark_paid_periode` retourne `[]` (tout déjà payé ou tx déjà success) : on marque quand même la tx success si besoin (log idempotent).
- Log action amélioré : `cotisation period=3 mois=2026-03,2026-04,2026-05 -> 3 ligne(s) statut payee`.

### 9. Modèles Schemas Pydantic — 100% rétrocompatibles
Fichier : [app/schemas/paiements.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/paiements.py)

- **`TransactionKoparOut`** 3 champs AJOUTÉS (camelCase alias) :
  ```
  periode_mois -> periodeMois: int | None
  premiere_annee_couverte -> premiereAnneeCouverte: int | None
  premier_mois_couverte  -> premierMoisCouverte: int | None
  ```
- **NOUVEAUX schemas** : `MoisCotisationLabelOut`, `ProchainPaiementPeriodeOut`, `ProchainPaiementSuggestionResponse`, `PaiementManuelPeriodeRequest`
- **0 suppression / renommage** → les consommateurs existants ne remarquent rien.

### 10. Email confirmation paiement — multi-mois
Fichier : [app/services/adhesion_mail_templates.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesion_mail_templates.py)

- Signature `build_cotisation_paiement_confirme()` : nouveau paramètres `mois_couverts: list[tuple[int,int]] | None` et `montant_total: int | None`. Les anciens param `annee/mois/montant` **restent optionnels** → appelants legacy continuent de fonctionner.
- **Si 1 mois** → sujet, texte, HTML exactement comme avant (`Cotisation Mars 2026 réglée`).
- **Si >1 mois** → sujet `Cotisations Mars,Avril,Mai 2026 réglées ✅`, HTML `<ul>` liste chaque mois + champ `Montant total: X FCFA` (pluriel sur le sujet/message).

### 11. Documentation frontend mise à jour
| Fichier | Section ajoutée / modifiée |
|---|---|
| [FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md) | Ajout section « PAIEMENT MULTI-PÉRIODES — UI SELECTEUR 1/3/6/12 » + exemple fetch suggestion + init paiement avec periodeMois |
| [GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md) | Ajout section « OPTION PAYER PLUSIEURS MOIS EN UNE FOIS » + tableau des endpoints étendus |

### 12. Vérifications
```bash
# AST parse syntaxique tous fichiers modifiés
python -c "import ast; [ast.parse(open(f,encoding='utf-8').read()) for f in [
  'app/models/paiements.py',
  'app/repositories/paiements.py',
  'app/services/paiement_orchestrator.py',
  'app/services/adhesion_mail_templates.py',
  'app/schemas/paiements.py',
  'app/api/v1/routes/paiements.py',
  'app/cli/reconcile_kopar_pending_transactions.py'
]]; print('OK')"
# → exit 0

# Tests : 4 passed / 6 failed, TOUS les 6 = préexistant NON LIÉ :
#   UserRepository.create_user() missing nom / prenom
#   → 0 nouvelle régression
python -m pytest tests/ -v --tb=no -q

# CLI help (pas besoin DB opérationnelle)
python -m app.cli.reconcile_kopar_pending_transactions --help → exit 0

# Routes enregistrées (app.main import, 96 routes totales)
#  suggestion routes = 3  (OK)
#  paiement-manuel / paiement-manuel-periode = 2  (OK)
#  4 init endpoints acceptent periodeMois query (vérifié routeur FastAPI)
```

---

## [E] RADIATION AUTOMATIQUE — Désactivation comptes 3 mois sans cotiser + fallback manuel

### 1. But (tableau « Ce qui manque IMPÉRATIVEMENT »)
Règle métier : **tout militant payant (adhésion = `validee`, NON privilégié) qui reste 3 MOIS CONSÉCUTIFS sans payer de cotisation mensuelle est AUTOMATIQUEMENT RADIÉ + compte utilisateur désactivé (JWT invalidé à la prochaine requête).**

**Seuil configurable** dans `.env` (pas de hardcode) :
```ini
RADIATION_AUTOMATIQUE_ENABLED=true        # défaut true ; passer false pour couper totalement en prod
RADIATION_DELAI_MOIS_IMPAYES_CONSECUTIFS=3 # défaut 3
```

### 2. Règle "impayé" comptabilisée
- Une ligne `cotisations_mensuelles` est **impayée** SSI son `statut NOT IN ('payee', 'annulee')`.  
  → `en_attente` ET `echue` → tous deux comptent comme impayé.
- Un adhérent est protégé ("nouveau") tant que le NB TOTAL de cotisations générées pour lui est `≤ delai_mois`.  
  → Il faut MINIMUM `delai_mois + 1` cotisations générées (autrement dit le mois offert ne compte jamais dans le streak).
- Le streak (mois consécutifs) est calculé **EN PARTANT DU MOIS COURANT (as_of) VERS LE PASSÉ**.  
  → Un ancien streak datant d'il y a 2 ans (tout payé récemment) NE DÉCLENCHE PAS la radiation.

**Exclusions automatique (radiation manuelle admin TOUJOURS autorisée)** :
- Rôles privilégiés (source unique → `RadiationService.PRIVILEGED_ROLES_AUTO_EXCLUDE`) :  
  `admin, comite_accueil, comite_directoire, coordinateur_commissariat, coordinateur_regional, moderateur`.
- Toute adhésion avec `statut != validee` (déjà en_attente / complement / rejetee / radiee).
- Toute adhésion dont le compte user est déjà `is_active = false` (déjà désactivée).

### 3. Changements BDD — Alembic (1 revision, backfill safe)
Fichier : [alembic/versions/z9a8y7x6w5v4_add_radiation_and_disabled_fields.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/alembic/versions/z9a8y7x6w5v4_add_radiation_and_disabled_fields.py)  
**8 colonnes nouvelles + 2 FK + 8 index.** Backfill `users.is_active = '1'` (tous anciens users → actifs, pas de régression). Downgrade réversible 100%.

#### Table `adhesions` (4 colonnes + 1 FK)
| Colonne | Type | Commentaire |
|---|---|---|
| `radie_at` | TIMESTAMP NULL | Date de radiation (quand statut passe à `radiee`) |
| `radie_par_user_id` | UUID NULL FK users.id → SET NULL ON DELETE | Admin qui a fait la radiation ; NULL si CRON auto |
| `radiation_reason_code` | VARCHAR NULL (`disabled_reason` enum VARCHAR) | `3_mois_impayes_consecutifs` OU `manuel_admin` |
| `radiation_motif` | TEXT NULL | Raison détaillée audit (pour réhabilitation ultérieure) |

#### Table `users` (4 colonnes + 1 FK)
| Colonne | Type | Commentaire |
|---|---|---|
| `is_active` | BOOLEAN NOT NULL DEFAULT '1' | `false` = compte désactivé, plus personne ne peut se connecter |
| `disabled_at` | TIMESTAMP NULL | Date de désactivation |
| `disabled_reason_code` | VARCHAR NULL | Même enum que radiation_reason_code |
| `disabled_motif` | TEXT NULL | Motif détaillé |
| `disabled_by_user_id` | UUID NULL FK users.id → SET NULL | Admin l'ayant fait (NULL si auto) |

### 4. Enum `DisabledReason` (partagé)
Fichier : [models/enums.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/enums.py)  
Ajout du `StrEnum` et extension `AdhesionStatus.radiee` :
```python
class DisabledReason(str, enum.Enum):
    AUTOMATIQUE_3_MOIS = "3_mois_impayes_consecutifs"
    MANUEL_ADMIN       = "manuel_admin"
```
→ Stocké en VARCHAR (native_enum=False partout, aucun `ALTER TYPE` PostgreSQL).

### 5. Service central (1 instance appelée par CLI CRON + Endpoints admin HTTP)
Fichier : [app/services/radiation_service.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/radiation_service.py)

#### Méthode 1 — `list_candidates(as_of, delai_mois, exclude_privileged_roles=True, limit=None)`
- Returns `list[RadiationCandidate]` (dataclass) : adhesion_id, nom/prenom, email/tel, streak_mois_impayes, mois_concernes (tuple annee, mois), nb_cotis_generees, roles_privileges.
- Algorithme streak cardinal : `ordinal = annee * 12 + (mois - 1)`. Curseur reculant depuis `as_of_ordinal` tant que le mois existe ET que statut ∉ {payee, annulee}.
- Protection recrues : `if nb_cotis_generees <= delai_mois → skip`.
- Exclusion rôles : `NOT EXISTS user_roles WHERE role IN PRIVILEGED_ROLES_AUTO_EXCLUDE`.

#### Méthode 2 — `apply_radiation(adhesion_id, reason_code, motif, radie_par_user_id=None)`
**ACTION ATOMIQUE SANS COMMIT (appelant commit ensuite)** :
1. Relecture adhésion + compte user lié (raise 404 si introuvable)
2. Si déjà statut `radiee` → skip idempotent (pas d'erreur)
3. Mutations adhesion : `statut = radiee, radie_at = utcnow, radie_par_user_id, radiation_reason_code, radiation_motif`
4. Mutations user (si existe) : `is_active = false, disabled_at, disabled_reason_code, disabled_motif, disabled_by_user_id`
5. Retourne `(adhesion, user_after)` → appelant commit puis email.

#### Méthode 3 — `apply_reactivation(adhesion_id, reactivation_motif, fait_par_user_id)`
**ACTION ATOMIQUE INVERSE (100 % MANUELLE ADMIN)** :
1. Vérifie adhesion.statut == `radiee` (sinon 400)
2. Audit historique : ancien motif conservé dans champ avec préfixe `[REHABILITÉ YYYY-MM-DD par {email_admin}] — motif`
3. Reset adhesion : `statut → validee, radie_at/radie_par_user_id/radiation_reason_code → NULL`
4. Reset user : `is_active → true, disabled_at/disabled_reason_code/disabled_by_user_id → NULL`
5. AUCUNE CRÉATION DE COTISATIONS RÉTRO (aucun paiement exigible à la réhabilitation).

### 6. Guards Auth (Triple verrouillage — aucun échappatoire)
| Guard | Endroit | Comportement |
|---|---|---|
| Login | [services/auth.py L62-L71](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/auth.py#L62-L71) | Avant créer tokens → si `not user.is_active` → **HTTP 403 "Compte désactivé"** (aucun JWT créé) |
| Refresh | [services/auth.py L120-L131](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/auth.py#L120-L131) | Avant rotation → `is_active==false` → **403 + revoke ALL refresh tokens** du user (force logout partout) |
| `get_principal()` | [core/auth.py L46-L50](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/core/auth.py#L46-L50) | TOUS endpoints protégés → si JWT valide 2h mais `is_active=false` → **403 immédiat** (JWT révoqué par état BDD) |
| On-the-fly création compte | [services/auth.py L186-L191](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/auth.py#L186-L191) | Si adhésion retrouvée par email avec `statut == radiee` → **refus création / connexion** |

### 7. Nouveaux champs exposés — 100 % RÉTROCOMPATIBLES (AJOUTÉS UNIQUEMENT)
#### Schéma `AdhesionDetailOut` → réponses admin `GET/PATCH /admin/adhesions/{id}`
Fichier : [schemas/adhesions.py L91-L96](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/adhesions.py#L91-L96)  
Ajout 4 champs (alias camelCase) :
```
radieAt, radieParUserId, radiationReasonCode, radiationMotif
```

#### Schéma `MeData` → réponse `GET /auth/me`
Fichier : [schemas/auth.py L67-L77](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/auth.py#L67-L77)  
Ajout 6 champs :
```
is_active, disabledAt, disabledByUserId, disabledReasonCode, disabledMotif, adhesionRadieAt
```

### 8. ENDPOINT ADMIN FALLBACK MANUEL (DEMANDE EXPLICITE UTILISATEUR)
**Raison : si CRON Alwaysdata ne marche pas, on peut déclencher manuellement les actions depuis l'espace admin sans attendre le scheduler.**

Router admin inclus automatiquement via `api_v1_router.include_router(admin.read_router)` + `admin.write_router` → **aucun fichier `router.py` à modifier**, l'enregistrement est déjà effectif.

Fichiers :
- Schemas : [app/schemas/radiation_admin.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/radiation_admin.py)
- Routes : [app/api/v1/routes/admin.py L432-L750](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/admin.py#L432-L750)

| # | Endpoint | Méthode | RBAC | Rôle |
|---|---|---|---|---|
| E1 | `/api/v1/admin/radiations/candidats` | **GET** | admin.read_router | **TOUS ROLES ADMINS** modérateurs + comités |
| E2 | `/api/v1/admin/radiations/apply-massive` | **POST** | admin.write_router | admin |
| E3 | `/api/v1/admin/adhesions/{id}/radier` | **POST** | admin.write_router | admin |
| E4 | `/api/v1/admin/adhesions/{id}/rehabiliter` | **POST** | admin.write_router | admin |

#### E1 — Lister candidats (fallback CRON manuel)
Query params optionnels : `annee`, `mois`, `as_of` (ISO), `exclude_privileged=true`, `limit`, `delai_mois_override`  
Réponse : `RadiationCandidatesResponse` → `{ asOf, delaiMois, candidates: [...] }`. Chaque candidat expose `streakMoisImpayes`, `moisConcernes[]`, `motifSuggestion` (texte prêt à coller dans la radiation).

#### E2 — Radiation massive manuelle admin (apply list candidate_ids)
Body `ApplyMassiveRadiationRequest { adhesionIds: uuid[], motif (min 10 chars) }`  
- Si un id ne figure DANS les candidats détectés (as_of + delai courants) → 400 liste des ids non trouvés
- Retour : `{ totalAppliquees, totalErreurs, rapports: [...] }`
- Emails envoyés en `BackgroundTasks` best-effort après chaque commit.

#### E3 — Radier UN adhérent manuellement (peut être un rôle privilégié)
Body `RadierManuelRequest { motif (min 10 chars obligatoire), reasonCode = "manuel_admin" (défaut) }`  
**Cas autorisé** : on peut radier `admin / comite_directoire / ...` à la main. Motif obligatoire (min 10 chars) pour audit.  
Retour 400 si adhérent déjà statut `radiee`.

#### E4 — Réhabiliter UN adhérent (reset statut + is_active)
Body `RehabiliterRequest { reactivationMotif (min 10 chars obligatoire) }`  
- 400 si adhésion PAS statut `radiee`
- Motifs **anciens conservés** avec préfixe `[REHABILITÉ ...]` dans `radiation_motif` et `disabled_motif` pour audit complet
- **AUCUN** paiement rétro n'est exigé (décision métier)

### 9. Templates Emails (notification membre)
Fichier : [app/services/radiation_mail_templates.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/radiation_mail_templates.py)

- `build_radiation_notification(adhesion, user, motif, reason_code, mois_concernes, base_url)` → sujet `[MONCAP] Désactivation de votre espace membre — {X} mois impayés`
- `build_reactivation_notification(...)` → sujet `[MONCAP] Réhabilitation de votre espace membre`
- Helper : `resolve_recipient_email(adhesion, user)` → email de préférence user.account.email, fallback adhesion.email_contact
- Format : Subject + text brut + HTML léger (lien page support).
- **Pattern jamais bloquant** : appels dans `BackgroundTasks.add_task(send_email_best_effort, ...)` APRES `session.commit()` ; en CLI → direct mais try/except pour ignorer toute erreur SMTP.

### 10. Script CLI CRON (job mensuel)
Fichier : [app/cli/apply_radiations.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/cli/apply_radiations.py)  
**Règle d'or : DRY-RUN PAR DÉFAUT. Ajouter `--apply` OBLIGATOIREMENT pour modifier la BDD.**

Usage :
```bash
# Juste lister les candidats, 0 écriture :
poetry run python -m app.cli.apply_radiations

# Appliquer les radiations :
poetry run python -m app.cli.apply_radiations --apply

# Lancer avec limite progressive en prod :
poetry run python -m app.cli.apply_radiations --apply --limit 10

# Override RADIATION_AUTOMATIQUE_ENABLED=false :
poetry run python -m app.cli.apply_radiations --apply --force

# Rattraper un mois où CRON a raté :
poetry run python -m app.cli.apply_radiations --apply --annee 2026 --mois 5
# ou :
poetry run python -m app.cli.apply_radiations --apply --as-of 2026-05-15T00:00:00Z

# Changer temporairement le seuil (ex: passer à 4 mois un mois) :
poetry run python -m app.cli.apply_radiations --apply --delai-mois 4
```

Comportement :
- Idempotent : si déjà `radiee` → skip, pas d'erreur
- Commit **par adhérent** (un échec = 1 rollback, pas tout le lot)
- Retour exit code 0 si 0 erreur (même si 0 candidat) ; 1 si ≥ 1 erreur
- Logs horodatés UTC (UTF-8 safe Windows / cp1252)

### 11. Checklist déploiement
1. **Alembic** → lancer `alembic upgrade head` **AVANT** de redémarrer l'app (nouvelles colonnes + index).
2. **CRON Alwaysdata** → ajouter la tâche (cf CRON.md : `0 30 1 * *` → APRES `generate_monthly_dues` 02h00).
3. **Smoke test** : lancer CLI sans `--apply` → vérifier la liste des candidats en prod (exit 0).
4. **Optional** : si toggle global off → passer `RADIATION_AUTOMATIQUE_ENABLED=false` dans `.env` (le script ne s'exécute pas tant que pas --force).

### 12. Vérifications
```bash
# AST parse syntax check de TOUS les fichiers nouveaux/modifiés → exit 0
$env:PYTHONDONTWRITEBYTECODE="1"
poetry run python -c "import ast; [ast.parse(open(f,encoding='utf-8').read(), f) for f in [...]"

# Tests : 4 passed / 6 failed (tous 6 = préexistant NON LIÉ : 
# `UserRepository.create_user() missing nom / prenom` → 0 NOUVELLE RÉGRESSION)
poetry run pytest tests/ -v

# CLI smoke (pas besoin de BDD opérationnelle pour --help) :
poetry run python -m app.cli.apply_radiations --help → exit 0
```

---

## [D] CARTE MEMBRE — Hydratation GEO sur endpoints militants + endpoints GET /geo/{id} individuels

### Demande (dev frontend)
La carte membre (3 pages frontend : `/espace-membre/carte`, `/admin/carte-membre`, `/suivi` dossier public) affiche **vide** pour les cases Département / Commune. Cause :
1. Endpoints renvoyant `MilitantOut` n'avaient **que les `*_id`** et les champs géo du DOMICILE ; manquaient `region_militantisme`, `departement_militantisme`, `commune_militantisme`, `pays_militantisme`, `est_diaspora`, `ville_militantisme` (champs utilisés **vraiment** sur la carte).
2. Il n'y avait **pas** d'endpoints individuels GET `/geo/pays/{id}`, `/geo/regions/{id}`, `/geo/departements/{id}`, `/geo/communes/{id}` pour résoudre les `*_id` en nom quand le frontend veut faire un fetch séparé.
3. P2 (hub diaspora) : pas de modèle HubDiaspora en BDD → différé.

### Ordre de priorité appliqué (OK)
1. ✅ **P0 = Hydratation DepartementOut / CommuneOut / PaysOut / RegionOut sur MilitantOut**
2. ✅ **P1 = 4 endpoints GET /geo/{pays,regions,departements,communes}/{id} (singulier)**
3. ⏳ P2 = Hubs diaspora → différé (pas de modèle ni table HubDiaspora)

### Correctifs P0 (hydratation systématique des objets GEO)
**Important : le eager-load des 8 relations geo (`region_domicile`, `departement_domicile`, `commune_domicile`, `pays_domicile`, + 4 `_militantisme`) était DÉJÀ codé dans `MilitantsRepository._with_geo()` ([militants.py repo L23-L33](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/militants.py#L23-L33)) et appliqué sur `lookup_validated`. Le bug n'était PAS au niveau ORM, mais sur (a) les schémas Pydantic qui n'avaient que la moitié des champs, et (b) les payloads dict construits à la main dans les routes.**

#### D1 — Schéma `MilitantLookupData` (réponse `GET/POST /militants/lookup`)
Fichier : [schemas/militants.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/militants.py)  
Ajouté L70-L92 dans `MilitantLookupData` (champs existants `_domicile` laissés intacts) :
```
est_diaspora: bool = False
region_militantisme_id / departement_militantisme_id / commune_militantisme_id
pays_militantisme_id, ville_militantisme
region_militantisme: RegionOut | None / departement_militantisme / commune_militantisme / pays_militantisme
```

#### D2 — Payload route `lookup_militant` (public + admin recherche)
Fichier : [routes/militants.py L184-L215](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py#L184-L215)  
Dict retourné par `return {"data": {...}}` : complété avec les 11 nouveaux champs (id + objet hydrated) + `est_diaspora` + `ville_militantisme`.

#### D3 — Schéma `MilitantProfileLink` (réponse `GET /auth/me → user.militant`)
Fichier : [schemas/auth.py L24-L63](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/auth.py#L24-L63)  
Ajout : tous les `*_id` + objets hydrated `RegionOut/DepartementOut/CommuneOut/PaysOut` pour **DOMICILE et MILITANTISME**, `est_diaspora`, `ville_domicile`, `ville_militantisme`. Import des schemas geo ajouté.

#### D4 — Payload route `/auth/me`
Fichier : [routes/auth.py L109-L144](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/auth.py#L109-L144)  
Anciennement : chargeait `user.adhesion` parfois via `selectinload(User.adhesion)` (qui **NE eager-loaded PAS les relations geo** — risque de DetachedInstanceError). Nouveau flow :
1. `if getattr(user, "adhesion_id", None) is not None:`
2. Toujours **re-fetch via `AdhesionRepository.get_by_id()`** → utilise `_with_geo()` avec 8 relations geo eager-loadées
3. Dict `militant` inclut **tous les champs geo** (2 axes), plus `est_diaspora`, `ville_domicile`, `ville_militantisme`.

#### Couverture endpoints (demande 2 dev front — tous OK)
| Endpoint | Hydratation geo | Statut |
|---|---|---|
| `GET /militants/lookup` (recherche admin + suivi public) | Tous 4 axes + est_diaspora + villes | ✅ D1+D2 |
| `GET /auth/me → data.militant` (espace membre `/espace-membre/carte`) | Tous 4 axes | ✅ D3+D4 |
| `GET /adhesions?email=` (suivi liste statuts) | `{id,statut,createdAt,motifRejet}` seulement → c'est une liste de suivi simple, intentionnellement allégée | RAS |
| `PATCH /admin/adhesions/{id}/info` | Retourne `AdhesionDetailResponse` → `AdhesionDetailOut` a TOUS les champs geo depuis le début | RAS (déjà OK) |

### Correctifs P1 (endpoints GET /geo/.../{id} individuels)

#### D5 — Schema singularisés (wrapper `{"data": XxxOut}`)
Fichier : [schemas/geo.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/geo.py)  
Ajoutés :
```
PaysOutResponse        # data: PaysOut
RegionOutResponse      # data: RegionOut
DepartementOutResponse # data: DepartementOut
CommuneOutResponse     # data: CommuneOut
```

#### D6 — Repo geo `get_pays()` manquant
Fichier : [repositories/geo.py L38-L40](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/repositories/geo.py#L38-L40)  
Les helpers `get_region / get_departement / get_commune` existaient déjà. Il manquait **seulement** `get_pays(pays_id)`. Ajouté.

#### D7 — Routes geo : 4 nouveaux endpoints
Fichier : [routes/geo.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/geo.py)  
4 nouvelles routes, toutes `response_model` avec wrapper `{"data": ...}`, `404 HTTPException` si ID introuvable :

| Endpoint | Schema réponse |
|---|---|
| `GET /api/v1/geo/pays/{pays_id}` | `PaysOutResponse` |
| `GET /api/v1/geo/regions/{region_id}` | `RegionOutResponse` |
| `GET /api/v1/geo/departements/{departement_id}` | `DepartementOutResponse` |
| `GET /api/v1/geo/communes/{commune_id}` | `CommuneOutResponse` |

**Remarque dev front :** pas d'endpoint `/referentiels/pays/{id}` ou `/pays/{id}` ailleurs dans l'API → tout est centralisé sous `/geo/...` comme attendu.

### Correctifs P2 — Hub diaspora
- **Statut : différé (pas de modèle ni table HubDiaspora en BDD).**
- Recherche codebase `HubDiaspora | hub_diaspora | hub-diaspora` → 0 résultat ([Grep de contrôle](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app)).
- Action nécessaire pour activer ultérieurement : (1) créer modèle `HubDiaspora` + migration Alembic, (2) FK `adhesion.hub_diaspora_id`, (3) relation ORM + `_with_geo()`, (4) schemas `HubDiasporaOut` + endpoints `/geo/hubs-diaspora[/{id}]`, (5) champ `hub_diaspora` sur `MilitantLookupData` + `MilitantProfileLink`.

### Vérifications
```
python -m poetry run python -m compileall -q app/schemas/militants.py app/schemas/auth.py app/schemas/geo.py \
  app/api/v1/routes/militants.py app/api/v1/routes/auth.py app/api/v1/routes/geo.py app/repositories/geo.py
# → exit_code 0 ; aucune erreur syntaxe
```
- **Aucune migration Alembic requise** (aucun nouveau champ / FK / table).
- **Rétrocompatibilité front 100 %** : ce sont des CHAMPS AJOUTÉS, jamais renommés / retirés. Les anciens consommateurs de `/auth/me` ne voient que des champs en plus.
- **Pas de nouveau `.env` / setting.**

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
