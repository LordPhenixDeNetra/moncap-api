---

## 🎯 Rien d'urgence. **3 étapes SIMPLES (moins de 5 min au total).**

---

### ✅ Étape 1 / 3 — **À FAIRE CE SOIR / DEMAIN MATIN : CRON du 1er du mois (OBLIGATOIRE)**

Sans ça, **octobre (mois prochain) n'aura AUCUNE ligne cotisation créée pour les adhérents**, et personne ne pourra payer.

→ **Admin Alwaysdata → CRON → + Nouvelle tâche** :

| Champ | Valeur |
|---|---|
| **Expression** | `0 2 1 * *` (**1er de chaque mois, 02h00 du matin**) |
| **Commande** | `cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.generate_monthly_dues >> /home/thior/logs_generate_monthly_dues.log 2>&1` |
| **Nom** | `MONCAP — Génération cotisations le 1er du mois 02h00` |

→ Valider / Enregistrer.

C'est **la seule tâche vraiment OBLIGATOIRE** aujourd'hui. Tout le reste = déjà OK.

---

### ✅ Étape 2 / 3 — **À FAIRE PLUS TARD QUAND KOPAR RÉPOND AU TICKET :** (pas urgent)

Quand `seydou.ba@koparexpress.com` t'aura répondu **"compte marchand activé"** :

1. **Admin Alwaysdata → Variables d'environnement :**
   Remplacer `KOPAR_BASE_URL=https://koparpay.com` → `KOPAR_BASE_URL=https://koparexpress.com`

2. **Restart** le site Alwaysdata.

3. Paiement test 5 FCFA → webhook direct Kopar appelé immédiatement (logs uvicorn `POST /paiements/webhook/kopar 200 OK`).

→ **PAS À FAIRE MAINTENANT.** On garde `koparpay.com` + CRON 5min qui marche très bien.

---

### ✅ Étape 3 / 3 — **OPTIONNEL, 2 minutes. Nettoyer les 6 transactions fantômes abandonnées :**

Si tu veux que chaque prochaine ligne du CRON affiche « Candidats=0 » (propre) au lieu de 6 pending :

En **SSH Alwaysdata** (copier-coller la ligne entière) :

```bash
cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python - <<'PY'
import asyncio
from app.core.database import AsyncSessionLocal
from app.repositories.paiements import TransactionKoparRepository
from app.models.paiements import StatutTransactionKopar

async def main():
    async with AsyncSessionLocal() as db:
        repo = TransactionKoparRepository(db)
        txs = [t for t in (await repo.list_all()) if t.statut in (StatutTransactionKopar.new, StatutTransactionKopar.pending)]
        for t in txs:
            st_val = t.statut.value if hasattr(t.statut, "value") else str(t.statut)
            ty_val = t.type_transaction.value if hasattr(t.type_transaction,"value") else str(t.type_transaction)
            print(f"[À nettoyer?] {t.id}  type={ty_val}  statut={st_val}  created={t.created_at.isoformat()[:19] if t.created_at else '?'}  kopar_token=…{t.kopar_token[-6:] if t.kopar_token else 'NONE'}")
        print(f"\n→ Total pending/new: {len(txs)}. Si ce sont des tests abandonnés, relance le SCRIPT AVEC --apply (je te donne la commande).")
asyncio.run(main())
PY
```

→ Montre moi l'output. Si ce sont des tests (pas des paiements réels que l'utilisateur a confirmé payer), je te donne une 2e commande pour marquer ces 6 tx en `cancelled` (un tour).

---

## 📋 BILAN FINAL (ce qui est DÉJÀ FAIT, 100% OK) :

| Tâche | Statut |
|---|---|
| .env local `KOPAR_BASE_URL=https://koparpay.com` | ✅ Fait |
| CRON 5 min Reconciliation Kopar (filet) | ✅ **FONCTIONNE** (preuve 2 tours 01:12 / 01:15) |
| Fallback Reconcile (polling anti-régression webhook) | ✅ OK |
| Module paiements (adhésion + cotisation) + QR Permanent + 302 Kopar direct | ✅ OK |
| CORS Allow Origins explicites innovamind + Bearer JWT | ✅ OK |
| Mapping erreur Kopar NO_AUTH/UNAUTHORIZED/INVALID_API_KEY → `kopar-no-auth` | ✅ OK (ce matin) |
| Fallbacks URL `settings.kopar_base_url` (plus `koparpay.com` hardcodé en code) | ✅ OK (ce matin) |

---

Donc pour **aujourd'hui** : tu fais l'**Étape 1** (cron 1er du mois). C'est tout. 👍