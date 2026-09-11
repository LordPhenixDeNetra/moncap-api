Utilisateur veut "plus terre à terre" = un workflow ultra concret, pas de jargon, avec des étapes SIMPLES comme on expliquerait à quelqu'un qui utilise l'app.

Je vais faire du pas à pas ultra simple, scenario concret.

# 💸 Workflow Paiement Cotisation — CONCRET (sans blabla)

**Adhérent : Moustapha Diagne (il a déjà payé son adhésion 5 FCFA le mois dernier)**

---

## 🗓️ **Étape 1 : Le 1er SEPTEMBRE (matin)** — **RIEN À FAIRE côté Moustapha**
- Le serveur MONCAP crée automatiquement sa ligne "Cotisation Septembre 2026 = 5 FCFA" dans la BDD.
- Moustapha reçoit un email : *"Votre cotisation du mois est disponible, montant 5 FCFA. Cliquez ici ou scannez votre QR"*.

---

## 📱 **Étape 2 : Le 5 SEPTEMBRE — Moustapha SCANNE son QR Code**
Il ouvre l'appareil photo de son téléphone → scanne le QR Code qu'il a reçu par email (ou qu'il a téléchargé depuis son espace membre) :

**Le QR contient un lien vers la page front :**
```
https://moncap.sn/payer-cotisation?adh=28c3d1b2-5555-4aaa-bbbb-9c0f3d5a7b9c
```

---

## 🌐 **Étape 3 : La page "Payer ma cotisation" s'ouvre sur son téléphone**
La page fait 1 appel API en arrière-plan :
```
GET https://api.moncap.sn/api/v1/paiements/cotisation/etat?adh=28c3d1b2...
```
→ **La page affiche :**
> ✅ Bonjour Moustapha Diagne  
> 📅 Cotisation Septembre 2026  
> 💰 **Montant à payer : 5 FCFA**  
> 🟢 Statut : En attente  
> (Pas de panique si tu n'as pas payé l'adhésion → la page te dira de la payer D'ABORD)

Moustapha voit un **champ "Email"** pré-rempli + un **bouton bleu "PAYER 5 FCFA"**.

---

## 🖱️ **Étape 4 : Moustapha clique sur "PAYER 5 FCFA"**
La page appelle en **POST (SANS mot de passe / SANS connexion)** :
```
POST /api/v1/paiements/cotisation/3f1c...ID_DE_LA_COTISATION.../initier-public
Body : { "email": "moustapha.d@example.com" }
```

Le backend vérifie que l'email correspond bien à son adhésion.  
Puis le backend appelle KOPAR et renvoie :
```json
{ "paymentUrl": "https://koparpay.com/payment/orders/KOPARtk_a1b2c3d4", "montant": 5 }
```

---

## 💳 **Étape 5 : Moustapha paie sur Kopar**
Son téléphone est redirigé automatiquement vers la page Kopar.  
Il choisit : **Wave / Orange Money / Carte bancaire**.  
Il valide → 5 FCFA sont prélevés.

---

## 🔔 **Étape 6 : Kopar prévient le backend MONCAP (instantané)**
Kopar appelle en secret :
```
POST https://api.moncap.sn/api/v1/paiements/webhook/kopar
Signature-HMAC : xxx
Body : { "status":"SUCCESS", "commandRef":"COT-3f1c...", "montant":5 }
```

Le backend MONCAP :
1. ✅ Vérifie la signature HMAC (sécurité)
2. ✅ Marque "Cotisation Septembre = PAYÉE" dans la BDD
3. ✅ Envoie un email à Moustapha : *"Paiement cotisation Septembre confirmé ! Référence : KOPARtk_a1b2c3d4"*

---

## 🎉 **Étape 7 : Retour sur la page MONCAP (5 secondes après)**
La page `/payer-cotisation` rafraîchit automatiquement → affiche :
> ✅ **Merci Moustapha ! Votre paiement de 5 FCFA pour Septembre 2026 a bien été reçu.**  
> Un email de confirmation vient de t'être envoyé.

---

## ✅ **Résumé ultra-court en 1 ligne**
> 📱 **Scan QR** → 📋 Page affiche montant 5 FCFA → 📧 Saisit email → 🖱️ Clique Payer → 💳 Paie Wave/OM sur Kopar → ✅ Email reçu "payé" + BDD marquée payée.

---

## 🔗 Points code (si besoin) :
- **Scan QR → infos :** [etat_cotisation_publique](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py#L88-L189)
- **Clique Payer → Kopar :** [initier_paiement_cotisation_public](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/api/v1/routes/paiements.py#L192-L250)
- **Kopar paye → Webhook :** [processer_webhook_kopar](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/services/paiement_orchestrator.py#L412-L472)
- **Cron 1er du mois → création lignes :** [generate_monthly_dues.py](file:///n:/OneDrive%20-%20Université%20Cheikh%20Anta%20DIOP%20de%20DAKAR/PycharmProjects/moncap-api/app/cli/generate_monthly_dues.py)