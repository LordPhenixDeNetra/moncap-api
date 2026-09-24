# Consigne BACKEND — Ajout des « Acteurs de validation » dans les réponses API

**Émetteur** : Dev Frontend MONCAP  
**Date** : 24/09/2026  
**Priorité** : P1 (affichage audit trail / traçabilité obligatoire dans les espaces admin)  
**Frontend cible** : `/admin/adhesions`, `/admin/articles/moderation`, `/admin/cotisations/radiations`

---

## ❌ Situation actuelle (problème)

Le frontend reçoit des UUID d'acteurs (ou parfois rien du tout) mais **pas leurs noms/prénoms/coordonnées**, donc **impossible d'afficher** dans l'UI :
- *« Validé Niveau 1 (accueil) par **Fatou Ndiaye** le 12/09 »*
- *« Rejeté par **Aly Diop** motif : CNI illisible »*
- *« Modéré / publié par **Mamadou Ba** (modérateur) »*
- *« Radié manuellement par **Admin Principal** »*

Référence schémas frontend actuels (ce qui est déjà reçu) :
- [types.ts — AdhesionDetailOut](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L213-L269)
- [types.ts — ArticleOut](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L435-L458)
- [types.ts — AdminAdhesionItem](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L188-L196)

---

## ✅ Ce qu'on a besoin (contrats à étendre)

### Règle générale appliquée partout
> Pour **tous** les champs `*_user_id: UUID`, ajouter **aussi** un objet **embedded** `*_user: UserOut | null` (et `*_at: datetime | null`).  
> Pas de jointure côté front : c'est **backend seul** qui sait faire la jointure SQL.  
> Le pattern existe déjà : **`ArticleOut.author: ArticleAuthorOut`** → reproduire ce pattern pour les validateurs.

### Objet commun de référence : `UserOut` (nouveau type à exposer)

Type commun à **tous** les acteurs embedded (réutilisable sur tous les endpoints) :

```ts
export interface UserOut {
  id: string;                       // UUID auth_user
  email: string;                    // email de connexion
  prenom: string | null;            // depuis militant lié
  nom: string | null;               // depuis militant lié
  tel_mobile: string | null;        // depuis militant lié
  commissariat: string | null;      // depuis militant lié
  roles: string[];                  // ["comite_accueil", "admin", "moderateur", ...]
  profile_photo_url: string | null;
}
```
> Si user n'a pas de `militant` lié (ex: superadmin pur), remplir au minimum `id, email, roles` + `prenom=null, nom=null`. Ne **jamais** renvoyer de hash mdp ou d'autres infos sensibles.

---

### 1. Modèles Adhésion — 2 niveaux de validation
Endpoint impactés :
- `GET /api/v1/admin/adhesions` (listing) → étendre `AdminAdhesionItem`
- `GET /api/v1/admin/adhesions/:id` (détail) → étendre `AdhesionDetailOut`
- `GET /api/v1/adhesions/mien` si membre voit son statut (optionnel)

**Champs à AJOUTER** (dans `AdminAdhesionItem` **et** `AdhesionDetailOut`) :

| Ancien état (manquant) | Nouveau champ (à créer) | Description |
|---|---|---|
| (statut=`validee_accueil` mais PAS qui a validé) | `valide_niveau1_par_user: UserOut \| null` | Membre du **Comité d'accueil** qui a cliqué « Valider niveau 1 » |
| (même) | `valide_niveau1_at: string \| null` | Timestamp de validation N1 |
| (statut=`validee` mais PAS qui a validé) | `valide_niveau2_par_user: UserOut \| null` | Membre du **Comité directoire** qui a cliqué « Valider niveau 2 » |
| (même) | `valide_niveau2_at: string \| null` | Timestamp de validation N2 |
| `motifRejet: string \| null` (sans qui a rejeté) | `rejete_par_user: UserOut \| null` | Celui qui a cliqué « Rejeter » (N1 ou N2) |
| (même) | `rejete_at: string \| null` | Heure du rejet |
| (même motif) | `en_complement_par_user: UserOut \| null` | Celui qui a demandé compléments d'infos |
| (même motif) | `en_complement_at: string \| null` | |

> **Note** : `statut` existant reste inchangé (`AdhesionStatus`), les nouveaux champs sont des **méta-données d'audit** supplémentaires, pas de rupture.

---

### 2. Modèle Article — validation / publication Modérateur
Endpoint impactés :
- `GET /api/v1/admin/articles` + `GET /api/v1/articles` (listing public ?)
- `GET /api/v1/admin/articles/:id` / `GET /api/v1/articles/:id` (détail)
- `GET /api/v1/admin/articles/moderation` (file d'attente modération)

**État actuel** dans [ArticleOut](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L435-L458) :
```ts
author_id: string;
author: ArticleAuthorOut | null;            // ✅ BON pattern (déjà jointure embedded)
validated_by_user_id: string | null;        // ❌ UUID SEUL, pas d'objet
validated_at: string | null;
validation_motif: string | null;
```

**Champs à AJOUTER** :

| Ancien | Nouveau (et conserver aussi les anciens `_id` pour rétro) |
|---|---|
| `validated_by_user_id` | ➕ **`validated_by_user: ArticleAuthorOut \| null`** (même type que `author`) |
| ❌ manquant | ➕ `rejected_by_user_id: string \| null` |
| ❌ manquant | ➕ `rejected_by_user: ArticleAuthorOut \| null` |
| ❌ manquant | ➕ `rejected_at: string \| null` |
| ❌ manquant | ➕ `rejected_motif: string \| null` |
| ❌ manquant | ➕ `closed_by_user: ArticleAuthorOut \| null` |
| ❌ manquant | ➕ `closed_at: string \| null` |

> **Important** : Utiliser le **même type `ArticleAuthorOut`** que `author` (déjà défini `{id,nom,prenom,photo_url?}`). Pas besoin d'un nouveau type. Ça nous évite d'ajouter `roles` etc. sur un article — pour les articles, on veut juste afficher le **nom/prénom** du modérateur.

---

### 3. Modèle Radiation Adhésion — acteur radiation manuel
Endpoint impactés : `GET /api/v1/admin/cotisations/radiations/*` + `AdhesionDetailOut` déjà cité.

**État actuel** ([AdhesionDetailOut](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L265-L269)) :
```ts
radieAt: string | null;
radieParUserId: string | null;          // ❌ UUID SEUL
radiationReasonCode: DisabledReasonCode | null;
radiationMotif: string | null;
```
**Champs à AJOUTER** :
| Nouveau |
|---|
| ➕ `radie_par_user: UserOut \| null` (objet embedded avec nom/prénom/email/roles) |

> **Conserver** `radieParUserId` existant pour rétrocompatibilité — on ajoute **en plus** l'objet, pas de rupture.

---

### 4. (Bonus P2) Modèle Paiements / Transactions Kopar — « Qui a saisi paiement manuel ? »
Si tu as le temps, même pattern sur `TransactionKoparOut` ([types.ts](file:///n:/OneDrive%20-%20Universit%C3%A9%20Cheikh%20Anta%20DIOP%20de%20DAKAR/React_Project/moncap/src/integrations/api/types.ts#L762-L832)) :
```ts
saisi_manuel_par_user: UserOut | null;
saisi_manuel_at: string | null;
```
Utile pour audit « un admin a enregistré un paiement cash » — MAIS c'est du P2, **pas urgent** maintenant.

---

## 🧪 Tests QA backend à vérifier avant livraison

| Test | OK ? |
|---|---|
| Une adhésion `en_attente` **ne doit pas** avoir de `valide_niveau1_par_user` ni `valide_niveau2_par_user` (tous null) | |
| Après appel `POST /admin/adhesions/:id/valider-niveau1` (endpoint existant) → `valide_niveau1_par_user` = **l'user JWT du token** et non un autre | |
| Après appel `POST /admin/adhesions/:id/valider-niveau2` → `valide_niveau2_par_user` bien le bon user et `valide_niveau1_par_user` NON écrasé | |
| `GET /admin/articles/moderation` sur un article `approved` → `validated_by_user.nom/prénom` NON null et non vide | |
| `validated_by_user_id` et `validated_by_user.id` sont **cohérents** (même UUID) | |
| Un article `rejected` a bien `rejected_by_user` NON null + `rejected_motif` | |
| Aucun `null reference error` si un user a été **supprimé** (valide_par_user = null mais valide_par_user_id reste l'UUID historisé) | |

---

## 📅 Livrable & Communication

- **Quand c'est prêt** : Mettre à jour ce fichier `.md` + faire un git push du backend, puis ping sur Teams.
- **Endpoint `/openapi.json` ou le schéma Pydantic mis à jour** — le frontend va alors :
  1. Mettre à jour `types.ts` (ajouter `UserOut`, nouveaux champs)
  2. Ajouter dans l'UI des Badges / InfoRow « Validé par X le Y » (déjà prévu côté front structurellement).

**Urgence** : Cette implémentation est un **prérequis** pour livrer la V1 du Backoffice Admin (traçabilité de qui fait quoi, obligatoire RGPD interne + gestion des litiges).
