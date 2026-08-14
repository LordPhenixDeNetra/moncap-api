# Tâches restantes MONCAP — par rapport au Cahier des Charges

Source : [MONCAP_Cahier_des_Charges.md](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/MONCAP_Cahier_des_Charges.md)

> Ce fichier liste les fonctionnalités du CdC qui **ne sont pas encore implémentées** (ou seulement partiellement), classées par ordre de priorité estimé.

---

## Priorité HAUTE (ferme le MVP et sécurise la campagne)

### 1. Paiement en ligne + reçu PDF (CdC §2.1.4)
- Intégrations effectives : **Wave**, **Orange Money**, **Free Money**, **Carte bancaire** (Stripe / PayTech Sénégal).
- Statut actuel : les colonnes `mode_paiement`, `paiement_confirme`, `reference_paiement` existent dans [Adhesion](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/adhesion.py#L68-L73), mais il n’y a :
  - **pas de session de paiement initiée** (endpoint de paiement),
  - **pas de webhooks / callbacks**,
  - **pas de génération de reçu PDF** de l’adhésion,
  - **pas de contrôle « paiement OK avant validation finale »**.
- Sous-tâches :
  - [ ] Endpoint `POST /adhesions/{id}/paiement/init` (selon mode)
  - [ ] Webhooks (Wave / OM / Free / CB) pour `paiement_confirme=true` + `reference_paiement`
  - [ ] Génération **PDF reçu** (téléchargeable)
  - [ ] Règle : paiement confirmé obligatoire avant `validee` (directoire) — ou paramétrable
- [x] **Partiellement fait** : les champs de paiement et les modes existent ; les admins peuvent modifier `paiement_confirme` et `reference_paiement` via `PATCH /admin/adhesions/{id}/info`.

### 2. Suivi citoyen sécurisé + carte membre PDF (CdC §2.1.5, §2.2.3)
- Ce qu’il manque par rapport au CdC :
  - [ ] Numéro de dossier **unique** et stable (champ dédié + index unique)
  - [ ] Page de suivi **sécurisée** (OTP email/SMS ou token signé, pas juste l’email)
  - [ ] Téléchargement du **reçu PDF** paiement
  - [ ] Génération et téléchargement de la **carte de membre numérique PDF** (photo + commissariat + identité, QR vers lookup public)
- [x] Lookup public JSON pour la carte via [militants/lookup](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py#L1-L180) (critères email/cni/tel/carte_pastef/id)
- [x] Endpoint **/me enrichi (infos carte membre pour le militant connecté) : [auth.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/auth.py#L91-L134) : bloc `militant` avec `profile_photo_url`, `commissariat*`, `carte_pastef`, etc.
- [x] **Photo profil adhérent** : champ `profile_photo` uploadé en création + remplaçable via admin (`PATCH /admin/adhesions/{id}/files`) — utilisée pour la carte.
- Partiellement fait : lookup public JSON pour la carte via [militants/lookup](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py#L1-L180) et [/me enrichi](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/auth.py#L91-L134).

### 3. Notifications SMS (CdC §2.1.5, §2.2.3)
- Aujourd’hui : seulement emails via [mail.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/mail.py).
- Manque : envoi SMS (infobip / twilio / Orange SMS API) pour :
  - [ ] confirmation de dépôt,
  - [ ] changements de statut,
  - [ ] relances de cotisation.

### 4. Comptes & rôles “coordinateur” dédiés (CdC §5)
- [x] Les enums existent dans [AppRole](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/enums.py#L30-L37) : `coordinateur_commissariat`, `coordinateur_regional`, **et aussi `militant`** (ajouté).
- [x] **Lien `User ↔ Adhesion` (1:1)** : colonne `users.adhesion_id` (nullable, unique, FK) dans [user.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/user.py#L27-L33) + migration Alembic `g2h3i4j5k6l7`.
- [x] **Création automatique du compte militant** lors de la validation finale directoire (`validee`) avec email + mot de passe initial = **Carte PASTEF** (fallback CNI). Voir [validations.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/validations.py#L230-L284) et service [members.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/members.py).
- [x] **Login militant `email + Carte PASTEF`** (fallback CNI) dans [auth.py (service)](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/auth.py#L36-L200) + création “à la volée” du compte si pas déjà créé.
- [ ] **aucun endpoint / scope / filtre** ne force leur périmètre d’accès (pour coordonnateur de commissariat / régional).
- Sous-tâches :
  - [ ] Tables ou champs pour : `commissariat_coordonne_par_user`, `region_coordonne_par_user`
  - [ ] Listes d’adhésions filtrées + lookups autorisés selon périmètre
  - [ ] Dashboard coordonnateur (KPIs sur son périmètre)

### 5. Module Articles / Publications / Interactions
- Point demandé par le métier (pas explicitement “articles” dans CdC mais découle de “commissariats scientifiques” + “coin documentaire”).
- **Prérequis faits** :
  - [x] Comptes militants (création auto à la validation) + login `email + Carte PASTEF` : section “Comptes & rôles”.
  - [x] Rôle `militant` reconnu et JWT / auth / `/me` fonctionnels.
- À faire :
  - [ ] Modèles `Article`, `Comment`, `Like` + tags / commissariat / auteur
  - [ ] Endpoints publics : liste, détail, commentaires (paginer)
  - [ ] Endpoints militants connectés : créer/modifier (brouillon/publié), like, commenter
  - [ ] Modération : admin/coordinateur (dépublier, supprimer commentaire)

---

## Priorité MOYENNE (gestion opérationnelle & croissance)

### 6. Cotisations mensuelles & suivi financier (CdC §2.2.3, §2.2.5)
- **Prérequis indispensable** : confirmer le **vrai montant** de cotisation mensuelle (le CdC mentionne “1 025 000 FCFA/mois” noté “probable erreur de frappe”).
- Modèles à créer :
  - [ ] `Cotisation` (adhésion, période, montant, statut payé/en_retard, référence paiement, preuve)
- Endpoints :
  - [ ] Historique complet par membre
  - [ ] Dashboard membre : payé / retard / à venir
  - [ ] Relances automatiques email/SMS
  - [ ] Option prélèvement automatique autorisé
  - [ ] Rapports financiers (région, pays, commissariat, profession, période)
  - [ ] Traçabilité comptable (numéro transaction unique, piste audit)

### 7. Profil “cadre” & base nationale des compétences (CdC §2.2.3)
- [x] **Préparation faite** : champs `niveau_etude` / `annees_experience` / `biographie` dans [Adhesion](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/adhesion.py#L32-L34).
- [x] **Modifications possibles** : un admin peut modifier ces champs (et tous les autres) via `PATCH /admin/adhesions/{id}/info` ; un militant peut les éditer via un endpoint dédié si on le crée (reste à faire).
- Il manque :
  - [ ] Diplômes, certifications, domaines d’expertise, expériences pro, publications, langues parlées, disponibilité, centres d’intérêt
  - [ ] Moteur de recherche multicritères experts (commissariat / spécialité / région / département / disponibilité)
  - [ ] Endpoint “Profil du cadre” visible / modifiable par le militant connecté (avec moderation)

### 8. Gestion des commissariats (CdC §2.2.4)
- [ ] Vue par commissariat avec membres rattachés + KPIs
- [x] **KPIs par commissariat (partiellement fait)** : endpoint `GET /militants/stats/commissariats` → renvoie la ventilation des militants validés par commissariat. Voir [routes/militants.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py)
- [ ] Outils de communication interne par commissariat (export liste emails/tels minimum)
- [ ] Donner missions / invitations / convocations (modèles + état)

---

## Priorité PLUS BASSE (produit riche, après stabilisation MVP)

### 9. Événements (CdC §2.2.5)
- [ ] Inscription en ligne événements
- [ ] QR Code présence + feuille de présence automatique
- [ ] Génération attestations de participation

### 10. Communication interne (CdC §2.2.5)
- [ ] Messagerie interne / forums par commissariat
- [ ] Sondages
- [ ] Newsletters (envois groupés + suivi)

### 11. Coin documentaire + E-learning (CdC §2.2.5)
- [ ] Bibliothèque numérique : statuts, règlements, notes politiques, rapports, vidéos
- [ ] Espace e-learning : cours/vidéos, quiz, parcours de formation, certifications internes

### 12. Annuaire intelligent (CdC §2.2.5)
- [ ] Moteur multicritère membre : profession / spécialité / région / département / commissariat / ancienneté / disponibilité

### 13. Nominations & historique de fonctions (CdC §2.2.5)
- [ ] Modèle pour responsabilités internes / mandats / commissions / nominations
- [ ] Historique par membre

### 14. Observatoire des compétences (CdC §2.2.5)
- [ ] Tableau de bord stratégique : secteurs fortement représentés / domaines manquants / besoins futurs

---

## Points techniques transverses à confirmer / faire

- [ ] **2FA admin** (CdC §4.3)
- [ ] **Logs d’audit complets** (accès + modifications — il y a déjà des user_id sur validations accueil/directoire, mais pas généralisé)
- [ ] **Sauvegarde automatique DB + fichiers (CV/photos)** (CdC §4.3)
- [ ] **WCAG 2.1 AA** (CdC §4.2) — à faire principalement côté frontend
- [ ] **Mobile-first / offline partiel** (CdC §4.2 + §10)
- [ ] **Page d’accueil MONCAP** + présentation + contact WhatsApp `77 636 32 59` (CdC §2.1.1) → principalem. frontend
- [x] **Format d’erreur API uniforme (tous endpoints)** : handler global `error.code / error.message / error.details + request_id` : [core/errors.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/core/errors.py)
- [x] **Anti-doublons adhésions** (email/cni/carte_electeur) : erreurs 409 structurées + indexes uniques partiels (sur adhésions actives, soft delete aware) : [services/adhesions.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesions.py#L117-L216) + migration Alembic correspondante
- [x] **Soft delete adhésions** + remplacement fichiers + modif infos admin : `DELETE /admin/adhesions/{id}`, `PATCH /admin/adhesions/{id}/info`, `PATCH /admin/adhesions/{id}/files` : [routes/admin.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/admin.py)
- [x] **Validation workflow `complement` → `validee_accueil`** : endpoint accueil accepte `complement` (pas seulement `en_attente`) : [validations.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/validations.py#L182-L207)
- [x] **Module militants (stats/ventilation)** : `/militants/count`, `/militants/stats/*` (regions/departements/communes/pays/villes/commissariats/diaspora), `/militants/timeseries`, `/militants/hierarchy` : [routes/militants.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/militants.py)
- [x] **Champs Commissariat scientifique (Principal/Secondaire)** : `commissariat_scientifique_principal` + `commissariat_scientifique_secondaire` + validation si `commissariat == "Commissariat scientifique"` : [schemas/adhesions.py](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/adhesions.py#L77-L83)

---

## Blocants / questions à arbitrer avant de coder

1. **Montant cotisation mensuelle** : valider la vraie valeur (actuellement suspect dans le CdC).
2. **Paiements** : API Wave / OM / Free réellement disponibles ? Sandbox ? Ou on implémente un mode “manuel” admin pour confirmer paiements ?
3. **SMS** : fournisseur retenu + budget (Infobip, Twilio, Orange SMS, etc.)
4. **Publication d’articles** : publication directe par militant, ou validation par coordinateur de commissariat / admin ?
