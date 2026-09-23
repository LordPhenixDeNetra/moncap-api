# 🚀 NOUVEAUTÉ BACKEND — Paiement Multi-Périodes COTISATIONS (M/T/S/A)

> **Date livraison backend** : 23 septembre 2026  
> **Rétrocompatibilité** : 100% (aucun code existant à casser ; `periodeMois` est **toujours optionnel**, défaut = 1 mois)  
> **Pour** : Dev Frontend MONCAP  
> **Concerne** : Écrans paiement cotisation (scan QR permanent + espace adhérent + admin back-office)

---

## 🎯 **Pourquoi cette feature ?**

Jusqu'à présent : 1 paiement Kopar = **1 mois de cotisation** (mensuel).  
Maintenant : 1 paiement Kopar = **N mois de cotisation** en un seul clic :

| Option | `periodeMois` | Paiement couvre |
|---|---|---|
| 🟢 **Mensuel** (défaut, rétro) | `1` | Mois en cours |
| 🟡 **Trimestriel** | `3` | Mois courant + 2 suivants |
| 🟠 **Semestriel** | `6` | 6 mois consécutifs |
| 🔴 **Annuel** | `12` | 12 mois consécutifs |

**L'adherent·e ne fait **qu'un** seul paiement Kopar (moins de friction mensuelle, meilleure rétention).**

---

## ✅ **CE QUI N'A PAS CHANGÉ (Rétrocompat 100%)**

Tu peux **tout à fait ne RIEN modifier dans le front existant** :

| Anciens endpoints | Commentaires |
|---|---|
| `GET /paiements/cotisation/etat?adh=UUID` | Toujours OK (retourne l'état du MOIS COURANT uniquement — inchangé) |
| `POST /paiements/cotisation/initier-public-par-adhesion?adh=UUID` | Toujours OK (**défaut = 1 mois mensuel** comme avant) |
| `POST /paiements/cotisation/{cotisation_id}/initier-public` | Toujours OK |
| `POST /paiements/adhesion/{id}/cotisation-du-mois/initier-public` | Toujours OK |
| `POST /paiements/cotisation/{cotisation_id}/initier` (interne JWT) | Toujours OK |

👉 **Si tu n'ajoutes aucun code front → tout continue de fonctionner en "paiement 1 mois mensuel" exactement comme avant.**

---

## 🎁 **CE QUI EST NOUVEAU (à exploiter côté front)**

### 1️⃣ **Endpoints NOUVEAUX : suggestions des 4 options (M/T/S/A)**

Ces endpoints **pré-calculent tout pour toi** (montant total, liste des mois, badges offerts/impayés inclus).

| # | Méthode | URL | Auth | Cas d'usage |
|---|---|---|---|---|
| **S1** | GET | `/api/v1/mon-compte/cotisations/prochaine-suggestion` | 🔒 JWT Adhérent | Page "Mes cotisations" → espace membre |
| **S2** | GET | `/api/v1/paiements/adhesion/{adhesion_id}/cotisation/prochaine-suggestion?email=EMAIL` | ✉️ Email vérifié | Après scan QR (version path param) |
| **S3** ✅ **À PRÉFÉRER** | GET | `/api/v1/paiements/cotisation/prochaine-suggestion?adh=UUID_ADHESION&email=EMAIL` | ✉️ Email vérifié | **Scan QR permanent, TOUS query params (zéro path param variable)** |

---

#### Exemple d'appel S3 après un scan QR `?adh=UUID` :

```js
// adh = UUID récupéré dans l'URL frontend ?adh=
// email = saisi ou pré-rempli (sera vérifié backend vs adhesion.email)
const sug = await fetch(
  `/api/v1/paiements/cotisation/prochaine-suggestion` +
  `?adh=${adh}` +
  `&email=${encodeURIComponent(email)}`,
  { credentials: "omit" }
).then(r => {
  if (!r.ok) throw new Error("Erreur suggestion : " + r.status);
  return r.json();
});
console.log(sug.options); // Tableau de 4 options index 0=Mensuel, 1=Trimestriel, 2=Semestriel, 3=Annuel
```

---

#### Réponse complète `ProchainPaiementSuggestionResponse` :

```jsonc
{
  "adhesionId": "a1b2c3d4-0000-0000-0000-000000000001",
  "adhesionEstValidee": true,
  "paiementAdhesionConfirme": true,

  "options": [
    // Index 0 : MENSUEL (1 mois)
    {
      "periodeMois": 1,
      "label": "Mensuel",
      "montantTotal": 1000,
      "devise": "XOF",
      "premierMoisConcerne": {
        "annee": 2026, "mois": 9,
        "label": "Septembre 2026",
        "statut": "en_attente"
      },
      "listeMois": [
        { "annee": 2026, "mois": 9, "label": "Septembre 2026", "statut": "en_attente" }
      ],
      "nbMoisImpayesInclus": 1,
      "nbMoisOffertsInclus": 0
    },

    // Index 1 : TRIMESTRIEL (3 mois)
    {
      "periodeMois": 3,
      "label": "Trimestriel",
      "montantTotal": 3000,
      "devise": "XOF",
      "premierMoisConcerne": { "annee": 2026, "mois": 9, "label": "Septembre 2026", "statut": "en_attente" },
      "listeMois": [
        { "annee": 2026, "mois": 9, "label": "Septembre 2026", "statut": "en_attente" },
        { "annee": 2026, "mois": 10, "label": "Octobre 2026", "statut": "en_attente" },
        { "annee": 2026, "mois": 11, "label": "Novembre 2026", "statut": "en_attente" }
      ],
      "nbMoisImpayesInclus": 3,
      "nbMoisOffertsInclus": 0
    },

    // Index 2 : SEMESTRIEL (6 mois)
    // ... structure identique, 6 entrées dans listeMois

    // Index 3 : ANNUEL (12 mois)
    // ... structure identique, 12 entrées dans listeMois
  ]
}
```

**Signification des champs "badge"** :
- `nbMoisOffertsInclus > 0` → Badge VERT 🎁 : *« 1 mois OFFERT inclus »* (règle métier : le TOUT PREMIER mois d'une nouvelle adhésion peut être gratuit)
- `nbMoisImpayesInclus > 1` → Badge ROUGE 🔴 : *« +X impayés inclus »* (transparent pour l'adhérent·e : ce qu'il·elle paie = tous ces mois)
- `montantTotal` → **RÉFÉRENCE SÉCURISÉE (ne jamais recalculer en front, voir § sécurité)**

---

### 2️⃣ **Endpoints EXISTANTS étendus : ajoute juste `?periodeMois=`**

**Tous les endpoints d'initiation acceptent MAINTENANT un query param optionnel `periodeMois=ENTIER` (défaut = 1 = comportement ancien).**

| Init paiement | Ajout query |
|---|---|
| `POST /api/v1/paiements/cotisation/initier-public-par-adhesion?adh=UUID&periodeMois=<1|3|6|12>` | ✅ **À PRÉFÉRER (QR permanent)** |
| `POST /api/v1/paiements/adhesion/{id}/cotisation-du-mois/initier-public?periodeMois=<1|3|6|12>` | ✅ |
| `POST /api/v1/paiements/cotisation/{cotisation_id}/initier-public?periodeMois=<1|3|6|12>` | ✅ |
| `POST /api/v1/paiements/cotisation/{cotisation_id}/initier?periodeMois=<1|3|6|12>` (JWT) | ✅ |

**Contraintes** : `periodeMois` DOIT être `1, 3, 6, ou 12`. Toute autre valeur est **normalisée automatiquement à 1 (mensuel)** par le backend (pas d'erreur 422).

---

#### Exemple concret — Scan QR + utilisateur clique « TRIMESTRIEL » :

```js
// sug = réponse de S3 (ci-dessus)
// optionChoisie = sug.options[1]  // → Trimestriel, periodeMois=3

const body = { email: "moustapha.d@example.com" };  // même body qu'avant

const init = await fetch(
  `/api/v1/paiements/cotisation/initier-public-par-adhesion` +
  `?adh=${adh}` +
  `&periodeMois=${optionChoisie.periodeMois}`, // ← SEUL AJOUT !
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }
).then(r => r.json());

// → init contient EXACTEMENT LES MÊMES CHAMPS QU'AVANT :
console.log(init.koparToken);    // à stocker
console.log(init.paymentUrl);    // redirect ou modal Kopar
console.log(init.qrCode);        // Data URL PNG pour afficher QR dans la page
console.log(init.montant);       // DOIT ÊGALER optionChoisie.montantTotal (toujours)
console.log(init.devise);        // "XOF"
```

✅ **Rendu Kopar est inchangé** : le user voit un paiement Kopar normal avec un montant = somme des N mois (pas de mention multi-périodes côté passerelle).

---

### 3️⃣ **Endpoint ADMIN NOUVEAU — Paiement manuel multi-périodes**

Pour back-office (RBAC : admin / `comite_directoire` / `coordinateur_regional`) :

```
POST /api/v1/admin/adhesions/{adhesion_id}/cotisations/paiement-manuel-periode
     ?annee=2026               // optionnel (défaut année courante)
     &mois=9                   // optionnel (défaut mois en cours)
Body :
{
  "periodeMois": 3,            // 1|3|6|12  (OBLIGATOIRE)
  "note": "Paiement chèque #1234",  // optionnel
  "referencePaiement": "CHQ123456"  // optionnel
}
```

Réponse = `CotisationListResponse { data: CotisationMensuelleOut[], total: number }` (les N lignes effectivement marquées payées).

---

### 4️⃣ **Champs NOUVEAUX sur TransactionKoparOut (historique)**

Tous les endpoints qui renvoient `TransactionKoparOut` (liste admin, détails admin, historique adhérent) ont **3 nouveaux champs NULLABLES** (rétro = tous `null` sur vieilles lignes → appliquer `?? 1`) :

| Champ (snake_case) | Alias front (camelCase) | Type | Signification |
|---|---|---|---|
| `periode_mois` | `periodeMois` | `number \| null` | Nb mois payés (1\|3\|6\|12). Null = ancienne tx → mensuel 1 |
| `premiere_annee_couverte` | `premiereAnneeCouverte` | `number \| null` | Année du 1er mois couvert |
| `premier_mois_couverte` | `premierMoisCouverte` | `number \| null` | Mois 1-12 du 1er mois couvert |

**Règle front sûre** (toujours l'appliquer) :
```js
const periode = tx.periodeMois ?? 1;          // null → considérer 1 (mensuel)
```

---

## 🎨 **Suggestion UI : 3 modes d'intégration (minimum → maximum)**

### 🟢 **Niveau 0 — Aucun effort (rétro pur)**
- Tu ne changes **RIEN**. Les utilisateurs paieront toujours 1 mois (mensuel) = comme avant.
- Tous les QRs déjà imprimés continuent de fonctionner à vie.

### 🟡 **Niveau 1 — Rapide (30 min dev)**
Sur l'écran QR `?adh=XXX`, **juste au-dessus du bouton PAYER**, ajoute 4 boutons radio :

```
[Choisir la période :]
☑ Mensuel (par défaut)
☐ Trimestriel
☐ Semestriel
☐ Annuel

[ PAYER (montant renvoyé par init /cotisation/etat) ]
```

1. `const periodeMois = radios.value || 1`
2. Passe juste `&periodeMois=${periodeMois}` au **même endpoint existant** `initier-public-par-adhesion`.
3. Le backend renvoie `response.montant` = somme calculée correcte.

### 🔵 **Niveau 2 — UX premium (recommandé)**
Affiche 4 **cartes cliquables** (style e-commerce abonnement) alimentées par `GET .../prochaine-suggestion` :

```
┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────────┐
│  ◉ Mensuel  │  │  ○ Trimest.  │  │  ○ Semestriel │  │  ○ Annuel      │
│  1 mois     │  │  3 mois      │  │  6 mois       │  │  12 mois       │
│             │  │  +2 impayés 🔴│  │  +5 impayés 🔴│  │  +11 impayés 🔴│
│             │  │  🎁 1 offert │  │               │  │  🎁 1 offert   │
│  ────────   │  │  ────────    │  │  ────────     │  │  ────────      │
│  1.000 CFA  │  │  3.000 CFA   │  │  6.000 CFA    │  │  11.000 CFA    │
└─────────────┘  └──────────────┘  └───────────────┘  └────────────────┘

                              [ PAYER {options[i].montantTotal} FCFA ]
```

---

## 🔒 **RÈGLES DE SÉCURITÉ IMPÉRATIVES (IMPORTANT)**

### ❌ **JAMAIS recalculer `montant = periodeMois × tarifMensuel` côté client**
Le montant **n'est pas toujours** `nbMois × tarifMensuel`. Pourquoi ?
- Certains mois **sont déjà payés** (ils ne DOIVENT PAS être re-facturés → déduit automatiquement par le backend)
- Le **premier mois de l'adhésion** est parfois OFFERT (montant = 0 FCFA sur cette ligne seulement)
- Le tarif référence change avec `ParametrePaiement.date_effet` (début 2027 = tarification nouvelle possible mid-periode)

### ✅ **Utilise UNIQUEMENT ces 2 sources** (par ordre de préférence)
1. **`options[i].montantTotal`** (réponse `GET .../prochaine-suggestion` → référence sûre)
2. **`response.montant`** (réponse `POST /initier-public-par-adhesion` → **référence finale envoyée à Kopar**, cohérence garantie)

### ✅ **Masquer les options si l'adhésion n'est pas valide**
Dès que dans `ProchainPaiementSuggestionResponse` :
- `adhesionEstValidee === false` OU
- `paiementAdhesionConfirme === false`

→ **Ne PAS afficher les sélecteurs M/T/S/A**. Rediriger vers paiement frais d'adhésion obligatoire (règle métier MONCAP : payer adhésion avant les cotisations mensuelles).

---

## 🧪 **Checklist recette Frontend (à cocher)**

- [ ] **Régression Mensuel OK** : sans toucher l'option, je peux payer le mois en cours → monnaie = 1 mois marqué payé
- [ ] **Régression Mensuel (email)** : j'ai reçu un email de confirmation avec **UN SEUL mois listé** (ancien rendu identique)
- [ ] **Suggestion renvoie 4 options** : `/cotisation/prochaine-suggestion` = tableau 4 éléments indexés 0=Mensuel..3=Annuel
- [ ] **Badge impayés s'allume** : avec 2 mois impayés, trimestriel = badge rouge « +2 impayés inclus »
- [ ] **Badge Offert s'allume** : pour une TOUT NOUVELLE adhésion (premier mois), Annuel = badge vert « 1 mois OFFERT »
- [ ] **Montant Trimestriel cohérent** : `options[1].montantTotal === response.init.montant === 3 × tarif (moins déductions)`
- [ ] **Paiement Trimestriel Kopar Success** → après retour webhook (ou CRON réconciliation) : 3 lignes mois = `payee`
- [ ] **Paiement Trimestriel (email)** : un SEUL email, liste `<ul>` des 3 mois + Montant total ligne
- [ ] **Tx historique affichage** : 3 colonnes periodes affichent `3 / 2026 / 9` sur la tx trimestrielle
- [ ] **Tx très anciennes rétro** : une ligne ancienne (avant feature) affiche `periodeMois ?? 1 = 1` (mensuel) dans le tableau admin

---

## 📚 **Références backend associées**

| Document | Chemin |
|---|---|
| Rappel général paiements cotisations (incluant UI multi-périodes § complet) | `FRONTEND_RAPPEL_COTISATIONS_MENSUELLES.md` (même dossier) |
| Guide exhaustif endpoints + contrats JSON détaillés | `GUIDE_FRONTEND_PAIEMENTS_COTISATIONS.md` (même dossier) |
| Changelog dev backend interne | `Update.md` section [F] |
| OpenAPI / Swagger UI (contrats JSON vivants !) | `https://api.moncap.sn/docs` (local : `http://localhost:8000/docs`) → onglets **Paiements** + **Admin** |

---

## 🆘 **Dépannage rapide**

| Symptôme | Cause probable | Solution |
|---|---|---|
| `GET .../prochaine-suggestion` → **HTTP 400 email_invalide** | L'email fourni ne correspond pas à l'`adhesion.email` en base | Vérifier le champ, pré-remplir via `/cotisation/etat` retourné `email` |
| Paiement multi ok mais **historique admin ne montre que 1 mois payé** | Webhook Kopar n'a pas été reçu (jamais atteint / mauvaise signature) | Lancer CRON réconciliation manuel : `python -m app.cli.reconcile_kopar_pending_transactions --apply --once` → il repasse les tx Kopar et marque tous les mois |
| `periodeMois = 2` envoyé → réponse OK mais 1 mois seulement | Valeur hors liste {1,3,6,12} → backend normalise silencieusement à 1 | Limiter ton `<select>` ou boutons radio aux 4 seules valeurs {1,3,6,12} |
| `options[i].montantTotal` != `init.montant` après POST | Un autre admin a modifié `ParametrePaiement` tarif ENTRE le temps d'affichage des cartes et le clic PAYER | Faire confiance **toujours** à `init.montant` (référence finale Kopar). Tu peux aussi recharger la suggestion avant init pour affichage temps réel. |

---

*Document mis à jour le 23/09/2026. Question backend ? Tag @dev-backend ou ouvrir le Swagger `/docs` pour les contrats exacts.* 🚀
