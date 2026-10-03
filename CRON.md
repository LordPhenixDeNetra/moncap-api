# CRON MONCAP — Tâches planifiées (Alwaysdata)

Ce document liste **toutes les tâches planifiées** nécessaires au bon fonctionnement de l'API MONCAP en production : à quoi elles servent, quand elles tournent, comment les installer et quoi faire en cas de problème.

---

## 1. Vue d'ensemble

| # | Tâche | Quand | Expression | Obligatoire |
|---|---|---|---|---|
| 1 | Rattrapage des paiements Kopar | Toutes les 5 minutes | `*/5 * * * *` | ✅ Oui |
| 2 | Génération des cotisations du mois | Le 1er du mois à 02h00 | `0 2 1 * *` | ✅ Oui |
| 3 | Radiation automatique (3 mois impayés) | Le 1er du mois à 02h30 | `30 2 1 * *` | ✅ Oui |
| 4 | Email « cotisation du mois disponible » | Le 1er du mois à 08h00 | `0 8 1 * *` | Recommandé |
| 5 | Relance 1 des impayés | Le 10 du mois à 08h00 | `0 8 10 * *` | Recommandé |
| 6 | Relance 2 des impayés | Le 20 du mois à 08h00 | `0 8 20 * *` | Recommandé |

**L'ordre du 1er du mois est important :** génération (02h00) → radiations (02h30) → email (08h00). Les radiations et l'email ont besoin que les cotisations du nouveau mois existent déjà.

---

## 2. Lire une expression CRON

Une expression CRON a toujours **5 cases** séparées par des espaces :

```
 ┌───────── minute         (0 à 59)
 │ ┌─────── heure          (0 à 23)
 │ │ ┌───── jour du mois   (1 à 31)
 │ │ │ ┌─── mois           (1 à 12)
 │ │ │ │ ┌─ jour semaine   (0 à 6, 0 = dimanche)
 │ │ │ │ │
 0 2 1 * *
```

- un **chiffre** = exactement cette valeur ;
- une **étoile `*`** = toutes les valeurs (« peu importe ») ;
- **`*/5`** = toutes les 5 unités.

| Expression | Lecture | En clair |
|---|---|---|
| `*/5 * * * *` | toutes les 5 min · toute heure · tout jour · tout mois | Toutes les 5 minutes, sans arrêt |
| `0 2 1 * *` | minute 0 · heure 2 · jour 1 · tout mois | Le 1er de chaque mois à 02h00 |
| `30 2 1 * *` | minute 30 · heure 2 · jour 1 · tout mois | Le 1er de chaque mois à 02h30 |
| `0 8 1 * *` | minute 0 · heure 8 · jour 1 · tout mois | Le 1er de chaque mois à 08h00 |
| `0 8 10 * *` | minute 0 · heure 8 · jour 10 · tout mois | Le 10 de chaque mois à 08h00 |
| `0 8 20 * *` | minute 0 · heure 8 · jour 20 · tout mois | Le 20 de chaque mois à 08h00 |

---

## 3. Syntaxe crontab complète (à copier-coller)

```cron
# MONCAP — Rattrapage Kopar si le webhook n'arrive pas (toutes les 5 min)
*/5 * * * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.reconcile_kopar_pending_transactions --apply --once >> /home/thior/logs_reconcile_kopar.log 2>&1

# MONCAP — Génération des cotisations du mois (le 1er à 02h00)
0 2 1 * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.generate_monthly_dues >> /home/thior/logs_generate_monthly_dues.log 2>&1

# MONCAP — Radiation automatique 3 mois impayés (le 1er à 02h30)
30 2 1 * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.apply_radiations --apply >> /home/thior/logs_apply_radiations.log 2>&1

# MONCAP — Email "cotisation du mois disponible" (le 1er à 08h00)
0 8 1 * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.send_payment_reminders debut_mois >> /home/thior/logs_reminders.log 2>&1

# MONCAP — Relance 1 des impayés (le 10 à 08h00)
0 8 10 * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.send_payment_reminders relance --niveau 1 >> /home/thior/logs_reminders.log 2>&1

# MONCAP — Relance 2 des impayés (le 20 à 08h00)
0 8 20 * * cd /home/thior/www/moncap-api && /home/thior/www/moncap-api/venv/bin/python -m app.cli.send_payment_reminders relance --niveau 2 >> /home/thior/logs_reminders.log 2>&1
```

---

## 4. Installation sur Alwaysdata

**Choisir UNE seule méthode.** Une tâche installée par les deux méthodes tournerait deux fois.

### Méthode A — Interface web (recommandée)

*Alwaysdata → Avancé → Tâches planifiées → Ajouter une tâche*, une tâche par ligne du tableau :

- **Fréquence** : l'expression (ex. `0 2 1 * *`) ;
- **Commande** : tout ce qui suit l'expression dans la section 3 ;
- **Nom** : le commentaire (ex. `MONCAP — Génération des cotisations du mois`).

### Méthode B — SSH

```bash
crontab -e     # coller le bloc de la section 3 à la fin, enregistrer
crontab -l     # vérifier
```

### Vérifications avant installation

1. Le chemin du projet et du venv existe :
   ```bash
   ls /home/thior/www/moncap-api/venv/bin/python
   ```
   Adapter les commandes si le projet est ailleurs.
2. Le `.env` de production contient bien `MAIL_ENABLED=true` et la configuration SMTP, **sans doublon plus bas dans le fichier** (la dernière valeur l'emporte). Sans cela, les tâches 4 à 6 tournent mais n'envoient rien, et l'OTP d'adhésion ne fonctionne pas.
3. `KOPAR_ENABLED=true` et `RECONCILE_KOPAR_ENABLED=true` (valeur par défaut) pour la tâche 1.
4. `RADIATION_AUTOMATIQUE_ENABLED=true` (valeur par défaut) pour la tâche 3.

**Fuseau horaire :** Dakar est en UTC+0. Si le serveur Alwaysdata est en UTC, les heures ci-dessus sont les heures de Dakar.

---

## 5. Détail de chaque tâche

### Tâche 1 — Rattrapage des paiements Kopar (toutes les 5 min)

**Module :** `app.cli.reconcile_kopar_pending_transactions`

**Pourquoi :** quand un adhérent paie, Kopar prévient l'API par un **webhook**. Si ce webhook n'arrive pas (serveur indisponible, mauvaise URL, signature refusée…), le paiement resterait « en attente » alors que l'adhérent a payé.

**Ce qu'elle fait :**
1. Prend les transactions encore `new` / `pending` créées il y a au moins 5 minutes (le temps de laisser une chance au webhook).
2. Demande à Kopar leur statut réel.
3. Si Kopar répond « payé », applique **exactement le même traitement que le webhook** :
   - frais d'adhésion → adhésion marquée payée ;
   - cotisation mensuelle, trimestrielle (3 mois), semestrielle (6 mois) ou annuelle (12 mois) → tous les mois couverts marqués payés ;
   - email de confirmation envoyé à l'adhérent.
4. Si Kopar répond « échec », « annulé » ou « remboursé », enregistre ce statut final.

**Garanties :**
- aucun double traitement si le webhook arrive en même temps que la tâche ;
- un paiement validé n'est jamais « dé-validé » par un webhook en retard ;
- une erreur sur une transaction n'empêche pas les autres d'être rattrapées ;
- relancer la tâche ne remarque rien en double et ne renvoie pas d'email.

**Options utiles :**

| Option | Effet |
|---|---|
| *(aucune)* | Dry-run : affiche ce qui serait fait, **ne modifie rien** |
| `--apply` | Applique réellement les changements |
| `--once` | Un seul passage (mode CRON) |
| `--daemon` | Boucle infinie (alternative au CRON, période `RECONCILE_KOPAR_POLL_SECONDS`) |
| `--older-minutes N` | Ne traite que les transactions de plus de N minutes (défaut 5) |
| `--force` | Ignore `RECONCILE_KOPAR_ENABLED=false` |

**Code de sortie :** `0` si tout s'est bien passé, `1` si au moins une transaction a échoué (elle sera retentée au passage suivant).

### Tâche 2 — Génération des cotisations du mois (le 1er à 02h00)

**Module :** `app.cli.generate_monthly_dues`

Crée une ligne de cotisation « en attente » pour chaque adhérent validé, pour le mois en cours. **Sans cette tâche, personne ne peut payer la cotisation du mois.** Les mois déjà payés à l'avance (paiement trimestriel, semestriel ou annuel) ne sont pas recréés.

**Options :** `--annee 2026 --mois 11` pour générer un mois précis (rattrapage) ; `--seed-defaults` pour créer les tarifs par défaut si la table des paramètres est vide.

### Tâche 3 — Radiation automatique (le 1er à 02h30)

**Module :** `app.cli.apply_radiations`

Radie les membres ayant **3 mois impayés consécutifs** (réglable par `RADIATION_DELAI_MOIS_IMPAYES_CONSECUTIFS`).

⚠️ **Dry-run par défaut : sans `--apply`, rien n'est modifié.** La commande de la section 3 contient bien `--apply`.

**Options :** `--as-of 2026-05-15T00:00:00Z` ou `--annee / --mois` pour recalculer sur un mois passé (si la tâche n'a pas tourné) ; `--limit N` pour radier progressivement ; `--delai-mois N` pour changer le seuil ponctuellement.

### Tâches 4, 5 et 6 — Emails de cotisation

**Module :** `app.cli.send_payment_reminders`

| Tâche | Commande | Destinataires |
|---|---|---|
| 4 (le 1er) | `debut_mois` | Tous les adhérents ayant une cotisation du mois en attente |
| 5 (le 10) | `relance --niveau 1` | Ceux qui n'ont toujours pas payé |
| 6 (le 20) | `relance --niveau 2` | Ceux qui n'ont toujours pas payé (dernière relance) |

Le script **ne regarde pas la date** : il fait uniquement l'action demandée. Il faut donc bien **3 tâches séparées** (et non une tâche quotidienne). Un adhérent déjà relancé ne reçoit pas deux fois la même relance.

**Option :** `--dry-run` pour compter les emails sans les envoyer.

---

## 6. Logs et surveillance

| Tâche | Fichier de log |
|---|---|
| 1 | `/home/thior/logs_reconcile_kopar.log` |
| 2 | `/home/thior/logs_generate_monthly_dues.log` |
| 3 | `/home/thior/logs_apply_radiations.log` |
| 4, 5, 6 | `/home/thior/logs_reminders.log` |

```bash
tail -n 50 /home/thior/logs_reconcile_kopar.log    # derniers passages
grep ERROR /home/thior/logs_reconcile_kopar.log    # transactions en échec
```

Dans le log du rattrapage, chaque passage se termine par une ligne du type :
`Candidats=… ; marqués SUCCESS=… ; autres statuts=… ; ERREURS=…`

---

## 7. En cas de problème : solutions manuelles

| Problème | Solution |
|---|---|
| Une tâche n'a pas tourné | La relancer à la main en SSH avec la même commande |
| Cotisations d'un mois non générées | `POST /api/v1/admin/cotisations/generer-mois?annee=2026&mois=11` (admin / comité directoire), ou tâche 2 avec `--annee --mois` |
| Radiations du mois non appliquées | `GET /api/v1/admin/radiations/candidats` pour voir la liste, puis `POST /api/v1/admin/radiations/apply-massive` |
| Paiement non détecté (même après rattrapage) | Paiement manuel admin : `POST /api/v1/admin/adhesions/{id}/cotisations/paiement-manuel-periode` |
| Voir les paiements bloqués « en attente » sans rien modifier | En SSH, lancer la tâche 1 **sans** `--apply` (dry-run) |

---

## 8. Après le déploiement de la correction du rattrapage

Avant cette correction, le rattrapage ne traitait que les frais d'adhésion : **aucune cotisation** (mensuelle, trimestrielle, semestrielle ou annuelle) n'était rattrapée. Après déploiement :

1. Lancer une fois en dry-run pour voir les paiements bloqués :
   ```bash
   cd /home/thior/www/moncap-api && venv/bin/python -m app.cli.reconcile_kopar_pending_transactions --once
   ```
2. Si la liste est correcte, appliquer :
   ```bash
   cd /home/thior/www/moncap-api && venv/bin/python -m app.cli.reconcile_kopar_pending_transactions --apply --once
   ```
   Les adhérents concernés reçoivent leur email de confirmation.

Les transactions qui restent « en attente » après ce passage sont celles que Kopar considère toujours en cours (souvent des paiements abandonnés). Elles sont simplement réinterrogées à chaque passage, sans effet de bord.

---

## Annexe — Passage de Kopar en compte marchand

Pas une tâche CRON, mais lié aux paiements. Quand Kopar Express confirme l'activation du compte marchand :

1. *Alwaysdata → Variables d'environnement* : remplacer `KOPAR_BASE_URL=https://koparpay.com` par `KOPAR_BASE_URL=https://koparexpress.com`.
2. Redémarrer le site.
3. Faire un paiement test et vérifier dans les logs `POST /api/v1/paiements/webhook/kopar 200`.

La tâche 1 reste active ensuite : elle sert de filet de sécurité si un webhook se perd.
