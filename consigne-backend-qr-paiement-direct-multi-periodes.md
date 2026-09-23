# Consigne Backend — Modification QR Permanent pour Multi-Périodes M/T/S/A

> Date : 2026-09-23
> Frontend prêt côté React (PayerCotisation 4 cartes Premium M/T/S/A).
> Action demandée au backend : MODIFIER le flux du QR permanent pour que le membre choisisse LA PÉRIODE côté frontend.

---

## 1) Fichier cible backend

```
app/api/v1/routes/paiements.py   →   route  qr_paiement_direct_cotisation
```

Localisation approximative lignes 154 → 250 (`@public_router.get("/cotisation/qr-paiement-direct", …)`).

---

## 2) RÈGLE À CHANGER (IMPORTANT — supprimer l'ancien comportement)

### ❌ Ancien comportement (À SUPPRIMER)
```
SI adhesion_validee == VRAI
ET paiement_adhesion_confirme == VRAI
ET cotisation du mois pas payée
  → backend créait la cotisation + initiait transaction Kopar 1 MOIS
  → 302 Location: https://koparpay.com/payment/orders/{kopar_token}
```

### ✅ Nouveau comportement (À METTRE EN PLACE)
```
SI adhesion_validee == VRAI  ET  paiement_adhesion_confirme == VRAI
  (quelle que soit la situation du mois courant)
  → backend NE FAIT PLUS RIEN D'AUTRE
  → 302 Location: {settings.base_front_url}/payer-cotisation?adh={adhesion.id}
```

⚠️ Ne PLUS appeler dans ce endpoint :
- `CotisationsService(db).creer_cotisation(...)` — ne sert plus ici
- `KoparService(...)` / toute init transaction Kopar
- Parsing mois/annee auto peut être supprimé

---

## 3) Cas qui restent IDENTIQUES (CONSERVER TELS QUELS)

| Condition                                                                 | Redirection 302 actuelle → CONSERVER SANS CHANGEMENT                         |
|---------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| `adhesion is None` (UUID inexistant)                                      | `/payer-cotisation?adh={adh}&erreur=introuvable`                              |
| `statut adhesion != "validee"`                                            | `/payer-cotisation?adh={adh}&erreur=adhesion-en-attente`                      |
| `paiement_adhesion_confirme == False` (frais adhésion 25k non réglés)     | `/payer-cotisation?adh={adh}&erreur=adhesion-impayee`                         |

---

## 4) Bloc de code à SUPPRIMER du endpoint `qr_paiement_direct_cotisation`

Tout le contenu situé APRÈS les 3 premiers checks :

```python
# ————————————————————————————————————————————————————
# ⚠️ TOUT CE BLOC CI-DESSOUS DOIT DISPARAÎTRE :
# ————————————————————————————————————————————————————

today = date.today()
if isinstance(mois, str) and str(mois).strip().lower() == "auto":
    mois_num = today.month
else:
    try:
        mois_num = int(str(mois).strip())
    except (TypeError, ValueError):
        mois_num = today.month
if isinstance(annee, str) and str(annee).strip().lower() == "auto":
    annee_num = today.year
else:
    try:
        annee_num = int(str(annee).strip())
    except (TypeError, ValueError):
        annee_num = today.year
if not (1 <= mois_num <= 12):
    mois_num = today.month
if annee_num < 2024 or annee_num > 2100:
    annee_num = today.year

svc_cot = CotisationsService(db)
cc = await svc_cot.creer_cotisation(adhesion.id, annee_num, mois_num)
await db.commit()
try:
    params_svc = ParametresPaiementService(db)
    montant_ref = await params_svc.get_montant(...)
    # ... + blocs KoparService, RedirectResponse(koparpay.com)
except KoparError:
    # ... + redirect erreur=kopar-indispo
```

---

## 5) Bloc de code à AJOUTER (à la place de ce qui a été supprimé)

```python
    # ————————————————————————————————————————————————————
    # ✅ NOUVEAU : Cas heureux multi-périodes
    # On laisse le FRONTEND (/payer-cotisation) gérer :
    #   - affichage des 4 cartes M/T/S/A
    #   - choix période par l'adhérent·e
    #   - appel à POST …/initier-par-adhesion?periodeMois={1|3|6|12}
    #     pour init Kopar
    # ————————————————————————————————————————————————————
    settings = get_settings()
    from urllib.parse import urlencode
    query = urlencode({"adh": str(adhesion.id)})
    frontend_url = f"{settings.base_front_url.rstrip('/')}/payer-cotisation?{query}"
    return RedirectResponse(url=frontend_url, status_code=302)
```

---

## 6) Nouveau flow complet (diagramme)

```
SCAN QR CARTE PERMANENTE
       ↓
GET  /api/v1/paiements/cotisation/qr-paiement-direct?adh=UUID&mois=auto
       ↓  (302 backend, APRÈS la modif ci-dessus)
FRONT  /payer-cotisation?adh=UUID
       ↓
Affiche 4 cartes période : Mensuel · Trimestriel · Semestriel · Annuel
       ↓  (membre clique « Trimestriel » → PAYER)
POST /api/v1/paiements/cotisation/initier-par-adhesion
     ?adh=UUID
     &service=cotisation_mensuelle
     &periodeMois=3          ← nouveauté, déjà supporté backend d'après livraison 23/09
       ↓
Backend init Kopar (3 mois, montant depuis DB)
       ↓  (302)
https://koparpay.com/payment/orders/{token}
```

---

## 7) Points de contrôle / Checklist QA backend

- [ ] `GET /qr-paiement-direct?adh={UUID_ACHESEE_VALIDE_PAYEE}` → **réponse Location est bien `/payer-cotisation?adh=…`**
- [ ] `GET /qr-paiement-direct?adh={UUID_ACHESEE_VALIDE_PAYEE}` → **réponse Location ne contient JAMAIS `koparpay.com`**
- [ ] `GET /qr-paiement-direct?adh={UUID_ACHESEE_INEXISTANT}` → `erreur=introuvable` (toujours OK)
- [ ] `GET /qr-paiement-direct?adh={UUID_ACHESEE_EN_ATTENTE}` → `erreur=adhesion-en-attente` (toujours OK)
- [ ] `GET /qr-paiement-direct?adh={UUID_ACHESEE_ADHESION_IMPAYEE}` → `erreur=adhesion-impayee` (toujours OK)
- [ ] Query params `mois=auto` / `annee=auto` sont ignorés (ne font plus planter ni changer le flux)

---

## 8) Référence frontend (ne pas modifier côté backend)

Frontend déjà prêt, endpoints backend existants utilisés :
- **S3 suggestion période (utilisé sur `/payer-cotisation`)** :
  `GET  /api/v1/paiements/cotisation/prochaine-suggestion?adh=UUID&email=`
- **S2 initier paiement avec période** :
  `POST /api/v1/paiements/cotisation/initier-par-adhesion?adh=UUID&service=cotisation_mensuelle&periodeMois={1|3|6|12}`
- **Admin paiement manuel période** :
  `POST /api/v1/admin/adhesions/{adhesionId}/cotisations/paiement-manuel-periode`

Ces endpoints ne sont **pas** impactés par la modification demandée.
