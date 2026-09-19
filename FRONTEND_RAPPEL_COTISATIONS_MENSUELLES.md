# 📋 MONCAP Backend — Rappel : Paiements COTISATIONS MENSUELLES (Frontend ↔ Backend)

> **Date** : 15 septembre 2026  
> **Phase** : Phase TEST (montants = 5 FCFA ; passe en prod à 25.000 FCFA / 1.000 FCFA mensuelle via admin — **pas de valeurs hardcodées back**)  
> **Règle d'or backend** : Les **montants référence** viennent `parametres_paiement` en base. **TOUT endpoint initier-paiement** (public ou protégé) **remet à jour la ligne (adhesion/cotisation) avec la valeur référence du jour avant d'appeler Kopar**.

---

## ✅ **CE QUI EST FAIT CÔTÉ BACKEND — COTISATIONS MENSUELLES**

---

### 🗓️ **1. CRÉATION AUTOMATIQUE DES COTISATIONS (Chaque 1er du mois)**

- **Script CLI** : `python -m app.cli.generate_monthly_dues` — à **lancer en CRON le 1er jour de chaque mois à 02:00 AM** (ou n'importe quand : **100% idempotent** via `UNIQUE (adhesion_id, annee, mois)`).
- **Comportement** : Pour **TOUS** les adhérents dont `adhésion.statut = validee` → crée 1 ligne `cotisations_mensuelles` avec `annee = année en cours`, `mois = mois en cours`, `montant = valeur DB référence (5 FCFA test)`, `statut = en_attente`.
- **Pas de doublon** : Même si tu lances le cron 5x, pas de création multiple.

---

### 📱 **2. PARCOURS PRINCIPAL (70%) : SCAN QR CODE PERMANENT**

**QR Code** : **1 QR unique et PERMANENT par adhérent** (QR = URL frontend, pas besoin d'en générer un nouveau chaque mois).  
**Format contenu du QR** : `{PUBLIC_BASE_URL}/payer-cotisation?adh=<UUID_ADHESION>` (ex: `https://moncap.sn/payer-cotisation?adh=28c3d1b2-5b1c-4aaa-bbbb-xxxxxxxx`).

#### **Étape 2.1 — Chargement infos (avant bouton Payer)**
```
GET /api/v1/paiements/cotisation/etat?adh=<UUID_ADHESION>
```
→ **PUBLIC, SANS JWT**. Retourne `AdherentEtatCotisationOut` :
```json
{
  "data": {
    "adhesionId": "28c3d1b2...",
    "prenom": "Moustapha",
    "nom": "Diagne",
    "email": "moustapha.d@example.com",
    "telephone": "+221770000000",
    "commissariat": "Commissariat 12",
    "paiementAdhesionConfirme": true,
    "cotisationCourante": {
      "id": "3f1c...ID_COTISATION...",
      "annee": 2026,
      "mois": 9,
      "montant": 5,
      "statut": "en_attente"
    },
    "montantDu": 5,
    "premiereCotisationAnnee": 2026,
    "premiereCotisationMois": 9,
    "estPremierMoisOffert": false,
    "historique24Mois": [ /* 24 derniers mois */ ]
  },
  "count": 1
}
```

⚠️ **RÈGLE LOGIQUE FRONTEND #1 — CRITIQUE :**  
Si `data.paiementAdhesionConfirme === false` → **L'ADHÉRENT N'A PAS ENCORE PAYÉ SES FRAIS D'ADHÉSION INITIALE**.  
→ REDIRIGE-LE D'ABORD VERS LE PAIEMENT DE **L'ADHÉSION INITIALE** → `POST /paiements/adhesion/{adhesion_id}/initier-public` (endpoint public, email check)  
→ **NE PROPOSE PAS LA COTISATION AVANT QUE CE BOLEAN SOIT À `true`** (backend renverra d'ailleurs un 409 si tu appelles les initier-cotisation avec `paiementAdhesionConfirme=false`).

⚠️ **RÈGLE LOGIQUE FRONTEND #2 — MOIS DE L'ADHÉSION OFFERT :**  
Si `data.estPremierMoisOffert === true` → **LE MOIS DE L'ADHÉSION EST OFFERT (gratuit) pour ce nouvel adhérent**.
→ `data.montantDu === 0` (garanti par le backend)
→ Affiche un bandeau texte explicite, par exemple :
> **[BON PLAN] Votre premier mois de cotisation est offert. Prochaine échéance : Mois Année (exemple : Octobre 2026).**
→ Le mois facturé réellement est indiqué par `(data.premiereCotisationMois, data.premiereCotisationAnnee)`.
→ Tu peux quand même afficher `cotisationCourante` (s'il existe) mais il représente le PREMIER MOIS FACTURÉ (mois suivant l'adhésion), pas le mois en cours.
→ **Désactive / masque le bouton « Payer ce mois-ci »** si `montantDu === 0` (puisque rien n'est dû).

---

#### **Étape 2.2 — Clic bouton "Payer cotisation" (POST Kopar)**
**2 méthodes possibles** (les 2 marchent, choisis celle qui te plaît le plus) :

##### 🅰️ **MÉTHODE RECOMMANDÉE (LA PLUS SIMPLE) — SANS avoir besoin de `cotisation_id`**
TU UTILISES DIRECTEMENT L'UUID ADHÉSION (même `?adh=XXX` que dans le QR !) → **BACKEND retrouve ou crée la cotisation DU MOIS TOUT SEUL**.

```
POST /api/v1/paiements/cotisation/initier-public-par-adhesion?adh=28c3d1b2-5b1c-4aaa-bbbb&service=kopar_services_cross
Content-Type: application/json

{ "email": "moustapha.d@example.com" }
```

→ **PUBLIC, SANS JWT, SANS QR, SANS `cotisation_id`**  
Body : `InitPaiementAdhesionPublicRequest` → email obligatoire (vérifié contre adhésion), reste optionnel (prenom/nom/telephone/cni/dateNaissance/lieuNaissance/servicePaiement aliases camelCase OK).  
Query `service=` optionnel : default `kopar_services_cross` (multi-canaux Wave/OM/CB) ou `wave_checkout`, `orange_money_sn`, `wave_checkout_ci` (push USSD direct).

✅ **Réponse 200 OK :**
```json
{
  "koparToken": "KOPARtk_a1b2c3d4...",
  "paymentUrl": "https://koparpay.com/payment/orders/KOPARtk_a1b2c3d4",
  "qrCode": null,
  "montant": 5,
  "devise": "XOF"
}
```
👉 **Front action** : `window.location.href = response.paymentUrl` → paiement Kopar → Webhook marque payée → email confirmation.

---

##### 🅱️ **MÉTHODE ALTERNATIVE — avec `cotisation_id` (si tu préfères utiliser celui de `/cotisation/etat`)**
```
POST /api/v1/paiements/cotisation/<cotisationCourante.id>/initier-public?service=kopar_services_cross
Content-Type: application/json

{ "email": "moustapha.d@example.com" }
```
→ Même réponse, même vérifications. Différence : tu dois utiliser le `cotisationCourante.id` de la réponse de l'étape 2.1 (tu ne peux pas utiliser que l'adhesion UUID direct).

---

### 🔗 **3. PARCOURS SECONDAIRE (25%) : LIEN DIRECT DEPUIS EMAIL DE RELANCE (SANS QR)**

C'est **exactement le même ENDPOINT que 🅰️ (2.2)** ci-dessus :
```
POST /api/v1/paiements/cotisation/initier-public-par-adhesion?adh=<UUID>&service=kopar_services_cross
```

**Intégration email :** Dans les emails de relance (début mois, J+10, J+20), **tu peux mettre directement** :
> 💡 **Cliquez ici pour payer SANS QR Code** :  
> `https://moncap.sn/payer-cotisation?adh=UUID_ADHESION`

→ Quand l'adhérent clique → page `/payer-cotisation` → appelle directement `POST initier-public-par-adhesion` sans même devoir passer par `/cotisation/etat` d'abord (optionnel, `/cotisation/etat` c'est juste pour afficher les infos avant paiement).

✅ URL ALIAS LONGUE (sémantique REST) dispo aussi (appelle la même fonction) :
```
POST /api/v1/paiements/adhesion/<ADHESION_ID>/cotisation-du-mois/initier-public
```

---

### 🔐 **4. PARCOURS ESPACE MEMBRE (5%) : CONNECTÉ AVEC JWT**

Frontend : utilisateur se logue → bouton "Ma cotisation du mois" :

#### 4.1 Charger ses infos (GET)
```
GET /api/v1/paiements/mon-compte/cotisation-du-mois
Authorization: Bearer <JWT>
```
→ Retour **même format** que `/cotisation/etat` (avec `paiementAdhesionConfirme`, `montant`, `cotisationCourante.id`). Même logique front.

#### 4.2 Initier paiement (POST)
```
POST /api/v1/paiements/cotisation/<cotisationCourante.id>/initier?service=kopar_services_cross
Authorization: Bearer <JWT>
// Body : VIDE — JWT + role adherent suffisent
```
→ Retour : `{paymentUrl, koparToken, montant, devise}` → même workflow Kopar.

---

### 💵 **5. PARCOURS KOPAR : Paiement + Webhook**

#### 5.1 Redirection Kopar
Tu rediriges simplement l'utilisateur vers **`paymentUrl`** (retourné par TOUS endpoints initier).  
Pour **`kopar_services_cross` (default, multi-canaux)** → page standard Kopar, l'utilisateur choisit Wave/OM/CB.  
Pour **`wave_checkout`/`orange_money_sn`** → **push USSD direct** (backend appelle un deuxième endpoint `checkout` Kopar en interne — t'as rien à faire côté front).

#### 5.2 Webhook Kopar success (backend → backend)
**Déjà prêt, RAS côté front, juste pour info :**
```
POST /api/v1/paiements/webhook/kopar
Headers : X-KOPAR-SIGNATURE (HMAC-SHA256, clé privée KOPAR_PRIVATE_KEY du .env)
```
Comportements déclenchés :
1. ✅ Vérifie signature HMAC
2. ✅ Retrouve `tx_type` via `customFields.type` → `adhesion` ou `cotisation`
3. ✅ Marque `cotisations_mensuelles.statut = payee`, `mode_paiement = kopar_pay`, `date_paiement = now`, `reference_kopar = token`
4. ✅ Update `TransactionKopar` avec raw response + statut final
5. ✅ **Envoie email confirmation** à l'adhérent avec référence Kopar + reçu

---

### 🔔 **6. EMAILS AUTOMATIQUES**

Script CLI : `python -m app.cli.send_payment_reminders` — lancer **chaque jour 08:00 AM** :
- **J+1 du mois** : Email à TOUS adhérents avec en-tête cotisation du mois → **LIEN DIRECT SANS QR : `/payer-cotisation?adh=UUID`**
- **J+10** : Relance 1 → seuls ceux qui n'ont pas encore payé
- **J+20** : Relance 2 → seuls ceux-là

✅ **3 templates déjà en place** dans [adhesion_mail_templates.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesion_mail_templates.py) (confirmation paiement + rappels).

---

### 💸 **7. PAIEMENT ADHÉSION INITIALE (Rappel, si `paiementAdhesionConfirme=false`)**

Le frontend affiche le paiement cotisation, mais si `paiementAdhesionConfirme === false` → tu DOIS l'envoyer sur le paiement **ADHÉSION** d'abord :

```
POST /api/v1/paiements/adhesion/<ADHESION_ID>/initier-public
{ "email": "user@example.com" }
```
→ Même réponse `{paymentUrl, montant: 5 (test)}`, puis après paiement webhook → `paiementAdhesionConfirme` passe à `true` → cotisation disponible au prochain appel `/cotisation/etat`.

---

## 🧮 **MONTANTS — Source de vérité (Aucun fallback côté frontend !)**

**Endpoint PUBLIC (SANS JWT) À APPELLER DÈS LE CHARGEMENT DE TOUTES TES PAGES PAIEMENT** :
```
GET /api/v1/paiements/parametres-public
```
→ Retourne 3 paramètres ACTIFS aujourd'hui :
```json
{
  "data": [
    { "code": "adhesion_initiale", "montantFcfa": 5, "libelle": "Frais adhésion initiale" },
    { "code": "cotisation_mensuelle", "montantFcfa": 5, "libelle": "Cotisation mensuelle" },
    { "code": "regle_date_premiere_cotisation", "valeurTexte": "mois_suivant", "libelle": "Règle date première cotisation" }
  ],
  "count": 3
}
```

⚠️ **UTILISE `montantFcfa` de ce endpoint DANS TA VUE ET DANS ton appel `POST /adhesions`** → tu évites le bug 25.000 FCFA / 5 FCFA qui est arrivé en phase test. Tu affiches **ce que dit la DB**, pas un fallback hardcodé.

---

## 🔧 **POUR TESTER (Bouton test rapide Frontend)**

1. Backend : `uvicorn app.main:app --reload`
2. Front : Charge `/parametres-public` → VÉRIFIE `cotisation_mensuelle.montantFcfa = 5`.
3. Crée une adhésion via formulaire, passe-la `statut=validee` et marque `paiement_adhesion_confirme=true` (direct en DB pour test).
4. Front `/payer-cotisation?adh=<UUID_ADH_VALIDEE>` → `/cotisation/etat` → VÉRIFIE `montant = 5` + `paiementAdhesionConfirme=true`.
5. Clique **Payer 5 FCFA** → POST `/initier-public-par-adhesion?adh=XXX` → vérifie réponse `montant: 5` → redirection Kopar.
6. (Si KOPAR_ENABLED=false en dev) → Mock : le backend retournera une simulation de paiement.

---

## 🆘 **Codes erreurs Backend à gérer côté Frontend**

| Code HTTP | Cas | Message front à afficher |
|---|---|---|
| 403 `initier-public` | Email saisi !== adhesions.email | "L'email ne correspond pas à cette adhésion. Vérifiez votre email." |
| 404 | UUID adhésion / cotisation introuvable | "Lien invalide ou expiré." |
| 409 `statut != validee` | Adhésion en attente / refusée | "Votre adhésion est en cours de validation, revenez plus tard." |
| 409 `paiementAdhesionConfirme=false` | ❌ Adhésion initiale non payée avant la cotisation | ⭐ "Veuillez d'abord payer vos frais d'adhésion avant de régler votre cotisation mensuelle." → puis redirection vers paiement adhésion |
| 409 `cotisation déjà payée` | User clique 2x | "Cette cotisation est déjà payée. Merci !" |
| 500 KOPAR_ERROR | Erreur Kopar Pay | `detail.detailsBrutsKopar` → affiche message (ex : "Service indisponible, réessayez") **ET log `detailsBrutsKopar` pour debug** |

---

## 📎 **Fichiers backend pour référence**

- **Routes** : [paiements.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py)
- **Orchestrateur central (userKyc/bankDetails/checkout conditionnel)** : [paiement_orchestrator.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiement_orchestrator.py)
- **Modèles SQLAlchemy** : [paiements.py (models)](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/paiements.py)
- **Schémas Pydantic** : [paiements.py (schemas)](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/schemas/paiements.py)
- **Templates emails** : [adhesion_mail_templates.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesion_mail_templates.py)
- **CLI cron cotisations** : [generate_monthly_dues.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/cli/generate_monthly_dues.py)
- **CLI cron emails relance** : [send_payment_reminders.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/cli/send_payment_reminders.py)
- **QR Code service (PNG permanent)** : [qr_code.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/qr_code.py)

---

**💡 Rappel final Frontend le plus important (TOP PRIORITÉ) :**  
Tu utilises **`/parametres-public`** au mount de tes pages `/adhesion` ET `/payer-cotisation` → les montants dans la DB sont la vérité. **Puis tu préfères systématiquement `/initier-public-par-adhesion?adh=XXX`** (le plus simple) à la place de `/cotisation/{id}/initier-public` — tu as moins de variables à gérer !
