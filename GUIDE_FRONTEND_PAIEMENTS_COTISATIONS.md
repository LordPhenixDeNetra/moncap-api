# 📘 Guide Frontend — Module Paiements & Cotisations Mensuelles (Kopar Pay + QR Permanent)

> **Projet** : MONCAP API — Backend FastAPI
> **Version module** : 1.0
> **Public visé** : développeur·euse frontend, intégrateur·ice, chargé·e de recette
> **Code du module backend** : tout dans `app/models/paiements.py`, `app/services/*_paiement*`, `app/services/kopar.py`, `app/services/qr_code.py`, `app/api/v1/routes/paiements.py`

---

## 🗺️ 1. Vue d'ensemble — 3 parcours utilisateur·ice

Ce module expose **3 parcours** différents :

| N° | Parcours | Public | Point d'entrée |
|----|----------|--------|----------------|
| A | **Paiement après SCAN du QR Code permanent** (scénario principal) | Tout le monde (route publique) | URL frontend `{PUBLIC_BASE_URL}/payer-cotisation?adh={UUID_ADHESION}` |
| B | **Paiement d'adhésion** (juste après validation dossier par comité) | Utilisateur connecté·e ayant une adhésion | Page "Payer mes frais d'adhésion" |
| C | **Espace adhérent** (historique, état mois en cours, mon QR) | Utilisateur connecté·e lié·e à une adhésion | Menu "Mon compte / Mes cotisations" |
| D | **Dashboard Admin** (gestion tarifs, état mensuel, paiement manuel) | Admin, Comité Directoire, Coordinateurs | Back-office "Cotisations" |

### ⚙️ Prérequis techniques côté frontend

- **Auth** : Utiliser le même JWT que pour le reste de MONCAP (header `Authorization: Bearer <token>`). Les rôles sont gérés côté backend (décorateur `require_roles`), tu n'as rien de spécial à vérifier côté UI (si tu appelles un endpoint admin sans bon rôle → HTTP 403).
- **URL publique du backend** : variable d'environnement `PUBLIC_BASE_URL` (voir `.env.exemple`, généralement `http://localhost:8000` en local, `https://api.moncap.sn` en prod).
- **URL publique du frontend** : c'est aussi `PUBLIC_BASE_URL` + `/payer-cotisation?adh=XXXX` qui est **encodée DANS le QR Code permanent**. Configure `PUBLIC_BASE_URL` à la bonne URL avant de générer les QRs (sinon mauvais lien dans le QR !).

---

## 🔗 2. Liste complète des endpoints utiles au frontend

> Les routes sont regroupées par `router`. Préfixe API global = `/api/v1`.
> Exemple : `public_router="/paiements"` → URL finale `/api/v1/paiements/cotisation/etat`.

### 🟢 Router PUBLIC (sans token) — 2 endpoints

#### 2.1 GET `/paiements/cotisation/etat` (après scan QR)
**But** : Quand un·e adhérent·e scanne son QR Code, sa caméra ouvre `{PUBLIC_BASE_URL}/payer-cotisation?adh=<UUID>`. Ta page frontend doit appeler cet endpoint avec `adh=` pour récupérer l'identité, la cotisation à payer et l'historique.

**Query params** :
| Param | Type | Obligatoire |
|---|---|---|
| `adh` | UUID | ✅ (c'est l'UUID de l'adhésion, récupéré dans l'URL `?adh=`) |

**Exemple appel** :
```
GET /api/v1/paiements/cotisation/etat?adh=a1b2c3d4-0000-0000-0000-000000000001
```

**Réponse (JSON)** : 👇
```jsonc
{
  "adhesionId": "uuid",
  "nom": "DIOP",
  "prenom": "Mamadou",
  "adhesionEstValidee": true,      // false si le dossier n'est pas encore validé
  "paiementAdhesionConfirme": true,  // false si frais d'adhésion pas encore payés
  "qrUrl": "https://api.moncap.sn/storage/qr_codes/a1b2c3d4-....png",
  "cotisationCourante": {
    "id": "uuid-cotisation",
    "adhesionId": "uuid",
    "annee": 2026,
    "mois": 3,
    "montant": 5,
    "devise": "FCFA",
    "statut": "en_attente",       // "en_attente" | "payee" | "echue"
    "paiementDate": null,
    "referencePaiement": null
  },
  "montantDu": 5,                    // 0 si déjà payé ce mois
  "montantAnnuelPaye": 10,           // cumul FCFA sur l'année en cours
  "moisPayesAnnee": 2,               // nombre mois payés en 2026
  "historique24Mois": [
    {"annee":2026,"mois":2,"statut":"payee","montant":5},
    {"annee":2026,"mois":1,"statut":"payee","montant":5}
  ]
}
```

**Ce que tu dois afficher** :
1. Nom + prénom + QR (image `<img src={qrUrl}>`)
2. Encart **"Cotisation de <mois> <année>"** :
   - Si `statut === "payee"` → encart VERT "Payée ✔️, référence : XXXX"
   - Si `statut === "en_attente"` ou `"echue"` → encart ROUGE + bouton **"Payer {montantDu} FCFA via Kopar Pay"** (appelle endpoint init paiement, voir § 2.2 router PROTECTED)
3. Historique 24 mois sous forme de tableau.

#### 2.2 POST `/paiements/webhook/kopar`
**But** : Endpoint public appelé AUTOMATIQUEMENT par Kopar Pay quand un paiement passe en "réussi" ou "échec". **Tu n'as rien à faire ici**, c'est Kopar qui appelle ça. Mais il faut informer l'admin de configurer l'URL de webhook Kopar à :
```
https://<TON_DOMAINE>/api/v1/paiements/webhook/kopar
```
Le backend valide la signature HMAC-SHA256 du header `X-KOPAR-SIGNATURE` avec `KOPAR_PRIVATE_KEY`. **Cette URL doit être en HTTPS en PROD (Kopar refuse le HTTP)**.

---

### 🔵 Router PROTECTED (avec Bearer Token) — 2 endpoints d'initiation de paiement

Ces 2 endpoints lancent une transaction Kopar et te renvoient un `paymentUrl` vers lequel tu **dois rediriger l'utilisateur·ice** pour qu'il·elle paye (Wave / Orange Money / Carte bancaire).

#### 2.3 POST `/paiements/adhesion/{adhesion_id}/initier`
**But** : Paiement des **frais d'adhésion** (unique). À proposer quand `paiementAdhesionConfirme === false`.

- Query params optionnels :
  - `service` (string) : `wave_checkout` | `orange_money_sn` | `kopar_services_cross` | `null` (laisse l'utilisateur choisir sur la page Kopar, **recommandé = null**)
  - `force=true` : relancer une transaction même si déjà payé (rarement utile côté frontend).

**Réponse (JSON)** :
```jsonc
{
  "koparToken": "KOPARtk_xxx",
  "paymentUrl": "https://koparpay.com/payment/orders/KOPARtk_xxx",
  "qrCode": "data:image/png;base64,iVBORw0KGgo..."   // QR code image si tu veux l'afficher
  "montant": 5,
  "devise": "FCFA"
}
```

**Flux côté frontend** :
```
Bouton "Payer les 25.000 FCFA d'adhésion"
  → fetch POST /api/v1/paiements/adhesion/<id>/initier
  → extraire paymentUrl
  → window.location.href = paymentUrl  // OU  ouvrir un iframe / modal
L'utilisateur·ice paie sur Kopar
  → Kopar appelle Webhook backend (/paiements/webhook/kopar)
  → Backend marque adhésion = paiement_confirme=true + envoie un email
  → (optionnel) Tu dois mettre en place une page de retour : Kopar peut
     rediriger vers ?redirect_url=https://tonfront/paiement/retour
```

#### 2.4 POST `/paiements/cotisation/{cotisation_id}/initier **(PROTÉGÉ JWT)**
**Identique à 2.3 mais pour une cotisation mensuelle — utilisateur·ice CONNECTÉ·E (JWT)**.

- Utilise `cotisationCourante.id` de la réponse de `/cotisation/etat`.
- Même flux : `paymentUrl` → redirection → webhook → marquée payée.
- **⚠️ Ce point IMPORTANT : Ce endpoint est seulement pour l'ESPACE MEMBRE CONNECTÉ (avec JWT). Pour le parcours QR SCAN (sans token), il FAUT utiliser **2.4bis** juste en dessous !

#### 2.4bis POST `/paiements/cotisation/{cotisation_id}/initier-public` **(PUBLIC — QR Scan QR — SANS JWT)**
**✅ **POINT D'ENTRÉE PRINCIPAL POUR LE PARCOURS SCAN QR CODE `/payer-cotisation`.

- **Sans JWT** : Vérification d'identité par email (user saisit email lié à l'adhésion).
- **Sécurité** : compare `body.email` (trimé insensible à la casse) vs `adhesions.email` → 403 si mismatch.
- **Montant** : Lit systématiquement la référence DB `ParametresPaiementService.get_montant(cotisation_mensuelle, today)` et met à jour la ligne cotisation.montant (audit Figé), **même principe que initier-public adhésion.

**Body JSON** (alias camelCase ou snake_case acceptés (populate_by_name=True):
```jsonc
{
  "email": "mbe@example.com",        // OBLIGATOIRE, correspond à adhesions.email
  "prenom": "Moustapha",                // optionnel override KYC (si renseigné)
  "nom": "Diagne",                     // optionnel
  "telephone": "+221770000000,         // optionnel
  "cni": "12345678",                // optionnel
  "dateNaissance": "1990-05-15",   // optionnel
  "lieuNaissance": "Dakar"             // optionnel
  "servicePaiement": "kopar_services_cross"   // optionnel (default: wave_checkout, orange_money_sn, kopar_services_cross)
}
```

**Query optionnel** : `?service=wave_checkout` (force un service specifique).

**Frontend QR Scan** : Utilisesur `/payer-cotisation?adh=UUID après avoir demandé à l'user son email → POST `/cotisation/` **public`/payer-cotisation` page 👇👇:
```ts
POST /api/v1/paiements/cotisation/<cotisationCourante.id>/initier-public?service=kopar_services_cross
{ "email": "user@example.com" }
```
→ Redirection `paymentUrl` (Kopar) → Webhook marquée payée.

---

### 🟣 Router ESPACE ADHÉRENT (préfixe `/mon-compte`, avec token) — 3 endpoints

**⚠️ Important** : Ces endpoints nécessitent que l'utilisateur connecté·e ait un **User.adhesion_id** non null (sinon HTTP 404 "Aucune adhésion liée à votre compte").

#### 2.5 GET `/mon-compte/qr-cotisation`
Retourne l'URL publique du QR Code permanent de l'adhérent·e + lien de paiement.

**Query** : `?regenerate=true` (force la régénération PNG — uniquement si le QR a changé de PUBLIC_BASE_URL).

**Réponse** :
```jsonc
{
  "data": {
    "qrUrl": "https://api.moncap.sn/storage/qr_codes/<adhesion_id>.png",
    "lienPaiement": "https://api.moncap.sn/payer-cotisation?adh=<adhesion_id>"
  }
}
```
**Frontend** : Afficher image + bouton "Télécharger" (tu peux utiliser `<a href={qrUrl} download="mon-qr-cotisation-moncap.png">`) + bouton "Partager" (Web Share API).

#### 2.6 GET `/mon-compte/cotisations?limit=24`
Historique des cotisations de l'adhérent·e connecté·e.
```jsonc
{
  "data": [
    {"id":"...","annee":2026,"mois":3,"montant":5,"statut":"en_attente","paiementDate":null,"referencePaiement":null},
    {"id":"...","annee":2026,"mois":2,"montant":5,"statut":"payee","paiementDate":"2026-02-10T14:30:00Z","referencePaiement":"KOPARtk_abc"}
  ],
  "total": 12
}
```

#### 2.7 GET `/mon-compte/cotisation-du-mois`
État complet du mois en cours (même réponse format que `/paiements/cotisation/etat` mais pour l'adhérent·e connecté·e : **pas besoin de `?adh=`**).

---

### 🔴 Router ADMIN (préfixe `/admin`, rôles nécessaires) — 8 endpoints

Rôles autorisés selon endpoint :
- `admin` & `comite_directoire` : tout
- `coordinateur_regional` & `coordinateur_commissariat` : lecture dashboard, listing, paiements manuels
- Autres : 403

#### 2.8 Lister / Créer / Modifier les paramètres de paiement (tarifs & règles)

| Méthode | URL | Rôle | Utilité |
|---|---|---|---|
| GET | `/admin/parametres-paiement?code=cotisation_mensuelle` | admin + CD | Lister les tarifs actuels + historiques |
| POST | `/admin/parametres-paiement` | admin | **Nouveau tarif** (ferme automatiquement le tarif en cours à la date d'effet - 1 jour) |
| PATCH | `/admin/parametres-paiement/{id}` | admin | Corrections (rare) |

**Schéma POST ParametrePaiementCreate** :
```jsonc
{
  "code": "adhesion_initiale",    // OU "cotisation_mensuelle" OU "regle_date_premiere_cotisation"
  "libelle": "Frais adhésion 2026",
  "montant_fcfa": 25000,          // ignoré si code = regle_date_premiere_cotisation
  "valeur_texte": null,           // obligatoire si code = regle_date_premiere_cotisation : "jour_15" ou "mois_suivant"
  "devise": "FCFA",
  "date_effet": "2026-01-01",     // IMPORTANT : changement pris en compte SEULEMENT pour les paiements/gen après cette date
  "date_fin_effet": null          // (laisser null, le backend fermera l'ancien)
}
```

> 💡 **Règle de première cotisation** : modifiable facilement avec code=`regle_date_premiere_cotisation` + valeur_texte=`"jour_15"` (adhésion validée ≤ 15 → cotisation mois courant ; >15 → mois suivant) OU `"mois_suivant"` (toujours mois suivant).

#### 2.9 GET `/admin/cotisations/dashboard?annee=2026&mois=3`
**Dashboard principal** de l'espace admin cotisations.

**Réponse** :
```jsonc
{
  "data": {
    "annee": 2026, "mois": 3,
    "total": 800,              // adhérents ayant une ligne (générés le 1er jour)
    "payes": 420,
    "enAttente": 360,
    "echues": 20,
    "tauxPaiementPct": 52.5,
    "montantTotal": 20000000,  // 800 * 25.000 FCFA
    "montantPerçu": 10500000,
    "montantRestant": 9500000
  }
}
```

#### 2.10 GET `/admin/cotisations` — Listing paginé + filtres
Query params (tous optionnels) :
- `annee`, `mois` (défaut : mois courant)
- `statut` : `payee` / `en_attente` / `echue`
- `region_id` (UUID région)
- `commissariat` (string)
- `offset`, `limit` (défaut 0, 50)

**Réponse** format `CotisationDetailListResponse` : chaque ligne a `adhesionNom`, `adhesionPrenom`, `adhesionTelMobile`, `adhesionCommissariat` en plus du détail cotisation.

#### 2.11 POST `/admin/cotisations/{cotisation_id}/paiement-manuel`
**Paiement hors Kopar** (espèces, chèque, transfert manuel Wave non relié, etc.).

**Body** :
```jsonc
{
  "reference_paiement": "Reçu n° 789 / caisse",
  "note": "Paiement en espèces au siège le 15/03"
}
```
Cela marque la cotisation `statut="payee"` avec les flags `paiement_manuel=true` et enregistre `user_id` = coordinateur ayant validé + date.now(). **Envoie automatiquement l'email de confirmation** à l'adhérent·e.

#### 2.12 GET `/admin/transactions-kopar?limit=50`
Historique toutes transactions Kopar (suivi erreurs, relances, debug webhook). Requête pour dev / support.

#### 2.13 POST `/admin/cotisations/generer-mois?annee=2026&mois=4`
Force la génération des lignes de cotisation pour un mois donné (en plus du cron automatique le 1er du mois). Utile pour backfill ou test.

---

## 💸 3. Intégration pas à pas — Parcours SCAN QR PARFAIT (90% des cas d'usage)

### Étape 1 : Créer la page `/payer-cotisation` dans le frontend
Ta route **doit accepter le query param `adh`** :

```tsx
// pages/payer-cotisation.tsx / PayerCotisationScreen.jsx
import { useSearchParams } from "react-router-dom"; // ou next/router / expo-router

export default function PayerCotisation() {
  const [search] = useSearchParams();
  const adhesionId = search.get("adh");

  if (!adhesionId) return <div>QR invalide, aucun paramètre adh</div>;

  return <PayerCotisationView adhesionId={adhesionId} />;
}
```

### Étape 2 : Charger l'état cotisation au chargement de la page
```tsx
async function loadEtat(adhesionId: string) {
  const r = await fetch(
    `${PUBLIC_API_URL}/api/v1/paiements/cotisation/etat?adh=${adhesionId}`
  );
  if (!r.ok) throw new Error("Erreur chargement état");
  return r.json();
}
```
Vérifie **d'abord** `data.paiementAdhesionConfirme` : si `false` → proposer **d'abord** le paiement d'adhésion (car les cotisations ne seront pas dues avant paiement adhésion).
→ Tu peux aussi charger **ET AFFICHER le tarif référentiel DB** via `GET /paiements/parametres-public` pour l'afficher DÈS LE DÉBUT (montant = cotisation_mensuelle.montantFcfa).

### Étape 3 : Au clic "Payer" (PARCOURS SANS JWT — QR SCAN TELEPHONE)
**⚠️ Important : Quand l'user SCANNE le QR depuis son téléphone, il N'A PAS de JWT actif ! Il FAUT utiliser le endpoint **PUBLIC `initier-public` (vérif email), PAS le protégé `/cotisation/{id}/initier` (401 garanti sans token).**

```tsx
// Étape 3a : Demande email (vérif identité) avant paiement
const [email, setEmail] = useState(""); // input controlé — adhérent saisit son email

// Étape 3b : Au clic Payer — POST INITIER-PUBLIC (PAS de JWT !)
async function onPayerCotisationPublic(cotisationId: string, email: string, servicePaiement?: string) {
  const url = new URL(`${PUBLIC_API_URL}/api/v1/paiements/cotisation/${cotisationId}/initier-public`);
  if (servicePaiement) {
    url.searchParams.set("service", servicePaiement); // default = kopar_services_cross (page standard : Wave / OM / Carte)
  }
  const r = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email.trim(),  // OBLIGATOIRE — backend vérifie vs adhesions.email (403 si non correspondant)
      prenom: prenomFromEtat,      // optionnel
      nom: nomFromEtat,            // optionnel
      telephone: telephoneFromEtat,// optionnel
    }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail?.message || data.message || "Erreur init paiement");
  // 🔑 Redirection vers Kopar :
  window.location.href = data.paymentUrl;
}
```

**Alternative : Si l'user est DÉJÀ connecté en JWT (espace membre), tu peux utiliser le endpoint protégé POST `/cotisation/{id}/initier` (avec Bearer token) — mais il est RECOMMANDÉ d'utiliser systématiquement initier-public depuis la page `/payer-cotisation` scan QR — elle fonctionne dans TOUS les cas (JWT ou non).

### Étape 4 : Kopar retourne vers ton frontend (page de succès)
Configure côté **dashboard marchand Kopar** le `redirect_url` pour que Kopar renvoie vers :
```
https://ton-frontend.moncap.sn/paiement/resultat?status=success&token=KOPARtk_xxx
```
⚠️ L'information "paiement réussi" vient DU WEBHOOK backend, **pas du redirect_url** (le redirect_url est juste de la décoration UX). Tu ne dois **pas** marquer comme payé côté frontend. Affiche juste :
```
✔️ Votre paiement est en cours de validation, un email de confirmation vous sera envoyé sous peu.
```
Puis refresh 5 secondes après `/cotisation/etat?adh=XXXX` pour voir si `statut` est passé à `payee`.

---

## 📧 4. Emails automatiques — Ce que le backend envoie

Le backend envoie **5 types d'emails** (templates HTML dans `app/services/adhesion_mail_templates.py`). **Tu n'as rien à coder côté frontend**, c'est juste pour info / QA :

| Quand | Destinataire | Sujet | Contenu |
|---|---|---|---|
| Paiement adhésion confirmé (webhook success) | Adhérent·e | `[MONCAP] Paiement adhésion confirmé` | Référence Kopar + montant + QR Code permanent en pièce-jointe (lien URL image) |
| Paiement cotisation confirmé (webhook success OU paiement manuel) | Adhérent·e | `[MONCAP] Paiement cotisation Mois confirmé` | Mois + montant + référence paiement |
| 1er jour du mois (après génération lignes) | Tous les adhérents | `[MONCAP] Votre cotisation du mois est disponible` | Montant + lien direct vers page `payer-cotisation?adh=XXX` + QR permanent |
| J+10 du mois (relance 1) | Adhérents non payés | `[MONCAP] Relance - Paiement cotisation` | Rappe montant + QR |
| J+20 du mois (relance 2 - plus ferme) | Non payés | `[MONCAP] Relance 2 - Paiement cotisation` | Même chose + "A défaut de paiement, vous serez radiés" (template personnalisable) |

---

## 🕐 5. Scripts automatisés (CRON) — Pour l'admin·sys

**À mettre en place** (crontab du serveur / GitHub Actions / Supervisor) :

### 5.1 Génération cotisations le 1er du mois à 00h05
```bash
# crontab -e sur le serveur
PATH=/usr/bin:/usr/local/bin:/srv/moncap-api/.venv/bin
5 0 1 * *  cd /srv/moncap-api && \
           python -m app.cli.generate_monthly_dues \
             --annee $(date -d next-month +\%Y) \
             --mois  $(date -d next-month +\%m) \
             --seed-defaults \
             >> /var/log/moncap/generate_cotisations.log 2>&1
```
**Idempotent** : si tu lances 2x, pas de doublons (UniqueConstraint DB).

### 5.2 Emails début mois le 1er à 07h00
```bash
0 7 1 * * python -m app.cli.send_payment_reminders debut_mois --dry-run false \
          >> /var/log/moncap/relances.log 2>&1
```
**Relances** :
```bash
# Niveau 1 (J+10) à 07h00
0 7 10 * * python -m app.cli.send_payment_reminders relance --niveau 1 --dry-run false
# Niveau 2 (J+20) à 07h00
0 7 20 * * python -m app.cli.send_payment_reminders relance --niveau 2 --dry-run false
```
Astuce dev : teste avec `--dry-run true` pour compter sans envoyer.

---

## 🧪 6. Recette — Checklist pour QA / démo

### 6.1 Test rapide backend (curl) — sans frontend
1. **Installer les nouvelles deps** : `poetry install`
2. **Lancer migration** : `alembic upgrade head` → crée 3 tables (vérifie dans `pgcli` / `psql`)
3. **Démarrer API** : `uvicorn app.main:app --reload` → dans les logs du premier démarrage tu dois voir :
   ```
   [seed] parametres_paiement table vide → insertion 3 paramètres (adhesion=5, mensuelle=5, regle=jour_15)
   ```
4. **Créer une adhésion** via `/adhesions` (formulaire public).
5. **Valider l'adhésion** via les 2 validations (comité accueil + CD).
6. **Générer cotisation mois courant** :
   ```bash
   python -m app.cli.generate_monthly_dues --annee 2026 --mois 3
   ```
7. **Récupérer UUID adhésion** (depuis admin `/adhesions`), puis tester l'endpoint public :
   ```bash
   curl "http://localhost:8000/api/v1/paiements/cotisation/etat?adh=<UUID>"
   ```
   → Doit renvoyer `cotisationCourante.statut="en_attente"` + `qrUrl` (ouvre dans navigateur, image QR doit s'afficher).
8. **Scan QR** : Scanne QR avec ton téléphone → URL doit être `{PUBLIC_BASE_URL}/payer-cotisation?adh=<UUID>` (vérifie `PUBLIC_BASE_URL` était bonne au moment de la génération du QR).

### 6.2 Test webhook Kopar sans passer par Kopar (signature HMAC mockée)
```python
# quick_test_webhook.py
import hmac, hashlib, json, requests

priv = "TA_KOPAR_PRIVATE_KEY"
body = json.dumps({
    "commandRef": "ADH-12345",
    "status": "paid",
    "amount": 5,
    "customFields": {"type": "adhesion", "adhesion_id": "<UUID_ADHESION>"},
    "transactionToken": "KOPARtk_mock"
})
sig = hmac.new(priv.encode(), body.encode(), hashlib.sha256).hexdigest()
r = requests.post(
    "http://localhost:8000/api/v1/paiements/webhook/kopar",
    data=body, headers={"X-KOPAR-SIGNATURE": sig, "Content-Type": "application/json"}
)
print(r.status_code, r.text)  # → 200 {"statut":"traité","paiement_applique":true}
```
Maintenant re-curl `/cotisation/etat` : `paiementAdhesionConfirme` doit passer à `true`.

---

## 🐞 7. Dépannage — Erreurs fréquentes

| Symptôme | Cause probable | Solution |
|---|---|---|
| QR affiche URL `http://localhost:8000/payer-cotisation...` alors que nous sommes en PROD | `PUBLIC_BASE_URL` était localhost au moment de la génération du QR | `PUBLIC_BASE_URL=https://api.moncap.sn` dans `.env`, puis régénérer les QRs via code ou nouvelle route admin |
| `/cotisation/etat` retourne `"adhesionEstValidee": false` | Adhésion n'a pas eu les 2 validations (comité accueil + CD) | Passer par les endpoints validation |
| Paiement Kopar réussi mais statut pas à jour | 1. Kopar a-t-il reçu l'URL de webhook ? 2. `X-KOPAR-SIGNATURE` valide ? 3. `KOPAR_ENABLED=true` ? | Vérifier `/admin/transactions-kopar` → colonne `last_webhook_body` + `statut` |
| Toutes les lignes cotisations ne sont pas générées le 1er | Script cron non lancé OU `Adhesion.statut != validee` | Lancer manuellement `POST /admin/cotisations/generer-mois` |
| Emails pas envoyés | 1. `MAIL_ENABLED=false` 2. SMTP mal configuré 3. Mails en spam | Vérifier `.env` + dossier spam |

---

## 📦 8. Fichiers importants backend — pour dev frontend curieux·se

| Fichier | Rôle |
|---|---|
| [app/models/paiements.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/models/paiements.py) | Définition DB (ParametrePaiement, CotisationMensuelle, TransactionKopar) + enums (statuts, types) |
| [app/services/qr_code.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/qr_code.py) | Génération PNG QR permanent → dossier `storage/qr_codes/<adhesion_id>.png` |
| [app/services/kopar.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/kopar.py) | Client Kopar Pay v2 (transaction request, checkout, refund, verify HMAC webhook) |
| [app/services/paiements.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiements.py) | Récupération montants par date + historique tarifs, génération cotisations, rapport mois |
| [app/services/paiement_orchestrator.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiement_orchestrator.py) | Centralise init paiements (adh + cot) + traitement webhook + envoi emails en arrière-plan |
| [app/api/v1/routes/paiements.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py) | 15 endpoints (public + protected + adhérent + admin) |
| [app/services/adhesion_mail_templates.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/adhesion_mail_templates.py) | 4 templates emails paiements ajoutés aux templates adhésions déjà existants |
| [alembic/versions/i4j5k6l7m8n9_add_paiements_tables.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/alembic/versions/i4j5k6l7m8n9_add_paiements_tables.py) | Migration créant les 3 tables (run `alembic upgrade head`) |

---

## ✅ 9. Checklist de livraison pour mise en prod

Avant mise en prod, vérifier **impérativement** :

1. [ ] `.env` = `KOPAR_ENABLED=true` + `KOPAR_API_KEY`/`KOPAR_PRIVATE_KEY` remplis (clés de PROD, pas test)
2. [ ] `.env` = `PUBLIC_BASE_URL=https://api.moncap.sn` (DOMAINE FINAL HTTPS)
3. [ ] `alembic upgrade head` exécuté sur PROD
4. [ ] Création dossier `storage/qr_codes/` avec droits d'écriture user app
5. [ ] Scripts cron activés (génération + début_mois + relance 1 + relance 2)
6. [ ] Dashboard marchand Kopar configuré avec URL webhook : `https://api.moncap.sn/api/v1/paiements/webhook/kopar`
7. [ ] Kopar marchand activé sur services désirés (`wave_checkout`, `orange_money_sn`, `kopar_services_cross`)
8. [ ] Tarif de PROD configuré dans `/admin/parametres-paiement` (adhesion_initiale=25.000, cotisation_mensuelle=XXXX, **pas 5 FCFA**) — enregistrer avec `date_effet` = jour J
9. [ ] QRs régénérés après passage en bonne `PUBLIC_BASE_URL`
10. [ ] Test end-to-end sur un vrai compte de test avec 5 FCFA : soumission → validation → génération cotisation → init paiement Kopar → paiement réel → webhook → marque payée → email reçu

Bon courage pour l'intégration frontend 🚀 ! Si tu bloques sur un contrat JSON, ouvre Swagger `http://localhost:8000/docs#/Paiements` et `http://localhost:8000/docs#/Admin` qui affiche les schémas exacts.
