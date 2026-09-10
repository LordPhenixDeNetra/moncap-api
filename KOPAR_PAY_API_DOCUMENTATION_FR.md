# KOPAR PAY - Documentation API Marchand

**Interconnecter l'Afrique avec sa diaspora**

**Contact :** seydou.ba@koparexpress.com — 78 295 43 01

---

## Sommaire

- [Introduction](#introduction)
- [Authentification](#authentification)
- [Points d'accès API (Endpoints)](#points-daccès-api-endpoints)
  - [1. Demande de paiement](#1-demande-de-paiement)
  - [2. Transaction Checkout](#2-transaction-checkout-paiement-sans-redirection-vers-la-page-kopar-pay)
  - [3. Récupérer les détails d'une transaction](#3-récupérer-les-détails-dune-transaction)
  - [4. Remboursement d'une transaction](#4-remboursement-dune-transaction)
- [Intégration Webhook (IPN)](#intégration-webhook-ipn)
  - [Configuration du Webhook](#configuration-du-webhook)
  - [Requête du Webhook](#requête-du-webhook)
  - [Vérification de la signature du Webhook](#vérification-de-la-signature-du-webhook)
  - [Points d'attention Webhook](#points-dattention-webhook)
- [Codes de réponse](#codes-de-réponse)
  - [Codes de statut HTTP](#codes-de-statut-http)
  - [Codes de statut de transaction](#codes-de-statut-de-transaction)
  - [Codes de réponse API](#codes-de-réponse-api)
- [Gestion des erreurs](#gestion-des-erreurs)
  - [Réponses d'erreur courantes](#réponses-derreur-courantes)
- [Exemples](#exemples)
  - [Exemple de flux de paiement complet](#exemple-de-flux-de-paiement-complet)
  - [Exemple de flux Checkout](#exemple-de-flux-checkout)
  - [Exemple de remboursement](#exemple-de-remboursement)
- [Support](#support)
- [Conditions d'utilisation](#conditions-dutilisation)

---

## Introduction

Bienvenue dans la documentation de l'API Kopar Pay. Ce guide fournit toutes les informations nécessaires aux marchands pour intégrer les services de paiement Kopar Pay dans leurs applications ou sites web.

- **URL de base :** `https://koparpay.com`
- **Version de l'API :** `v2`
- **Contact support :** seydou.ba@koparexpress.com, contact@koparexpress.com

---

## Authentification

Toutes les requêtes API nécessitent une authentification via votre clé API marchande. Incluez votre clé API dans le corps de la requête pour les requêtes POST.

> **Notes de sécurité importantes**
> - Gardez votre clé API et votre clé privée en sécurité
> - N'exposez jamais vos clés dans du code côté client
> - Utilisez HTTPS pour toutes les communications avec l'API

---

## Points d'accès API (Endpoints)

### 1. Demande de paiement

Crée une nouvelle demande de paiement et retourne un jeton (token) de paiement pouvant être utilisé pour rediriger les clients vers la page de paiement.

**Endpoint :** `POST /api/v2/transaction/request`

**En-têtes de requête :**
```
Content-Type: application/json
```

**Corps de la requête :**

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `apiKey` | string | Oui | Votre clé API marchande |
| `itemPrice` | number | Oui | Le montant à facturer |
| `commandName` | string | Oui | Description de la transaction/commande |
| `commandRef` | string | Oui | Votre référence unique pour cette transaction |
| `firstName` | string | Non | Prénom du client |
| `lastName` | string | Non | Nom du client |
| `email` | string | Non | Adresse e-mail du client |
| `phoneNumber` | string | Non | Numéro de téléphone du client |
| `countryCode` | string | Non | Code pays du client (ex. : "SN" pour le Sénégal) |
| `currency` | string | Non | Code devise (par défaut : "XOF") |
| `ipnUrl` | string | Oui | URL de votre webhook pour recevoir les notifications de paiement |
| `successUrl` | string | Oui | URL de redirection du client après un paiement réussi |
| `cancelUrl` | string | Oui | URL de redirection du client si le paiement est annulé |
| `editableAmount` | boolean | Non | Indique si le client peut modifier le montant (par défaut : false) |
| `customFields` | string | Non | Données personnalisées additionnelles au format JSON (string) |

**Exemple de requête :**

```json
{
  "apiKey": "your_api_key_here",
  "itemPrice": 10000,
  "commandName": "Achat du produit XYZ",
  "commandRef": "ORDER_12345",
  "firstName": "John",
  "lastName": "Doe",
  "email": "john.doe@example.com",
  "phoneNumber": "771234567",
  "countryCode": "SN",
  "currency": "XOF",
  "ipnUrl": "https://yourwebsite.com/webhook/kopar",
  "successUrl": "https://yourwebsite.com/payment/success",
  "cancelUrl": "https://yourwebsite.com/payment/cancel",
  "editableAmount": false
}
```

**Réponse de succès (200 OK) :**

```json
{
  "message": "Transaction Initiated.",
  "status": "SUCCESS",
  "token": "KOPAR_TOKEN_XXXXXXXX"
}
```

**Paiement avec redirection :** Une fois le token reçu, redirigez votre client vers :

```
https://koparpay.com/payment/orders/{token}
```

---

### 2. Transaction Checkout (paiement sans redirection vers la page Kopar Pay)

Traite le checkout d'une transaction initiée en utilisant un service de paiement spécifique.

**Endpoint :** `POST /api/v2/transaction/:token/checkout`

**Paramètres d'URL :**

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `token` | string | Oui | Le token de transaction reçu lors de la demande de paiement |

**En-têtes de requête :**
```
Content-Type: application/json
```

**Corps de la requête :**

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `service` | string | Oui | Nom du service de paiement (ex. : "orange_money_sn", "wave_checkout"), voir la liste des services de paiement |

**Exemple de requête :**

```json
{
  "service": "orange_money_sn"
}
```

**Réponse de succès (200 OK) :**

```json
{
  "data": {
    "transaction": {
      "koparId": "KOPAR_TOKEN_XXXXXXXX",
      "amount": 10000,
      "amountXof": 10000,
      "currency": "XOF",
      "status": "pending",
      "commandName": "Achat du produit XYZ",
      "commandRef": "ORDER_12345",
      "firstName": "John",
      "lastName": "Doe",
      "email": "john.doe@example.com",
      "phoneNumber": "771234567",
      "countryCode": "SN"
    },
    "message": "Transfert Initié",
    "code": "INIT_TRANSFER",
    "providerResponse": {
      "paymentUrl": "https://payment-provider-url.com/pay",
      "qrCode": "data:image/png;base64,...",
      "...otherProviderData": null
    }
  }
}
```

**Liste des services de paiement :**

| Nom | Description |
|---|---|
| `orange_money_sn` | Orange Money Sénégal |
| `wave_checkout` | Wave Sénégal |
| `wave_checkout_ci` | Wave Côte d'Ivoire |
| `kopar_services_cross` | Paiement par carte |

---

### 3. Récupérer les détails d'une transaction

Récupère les détails et le statut actuel d'une transaction.

**Endpoint :** `GET /api/v2/transaction/:token`

**Paramètres d'URL :**

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `token` | string | Oui | Le token de transaction |

**En-têtes de requête :**
```
Content-Type: application/json
```

**Réponse de succès (200 OK) :**

```json
{
  "status": "SUCCESS",
  "data": {
    "koparId": "KOPAR_TOKEN_XXXXXXXX",
    "amount": 10000,
    "amountXof": 10000,
    "currency": "XOF",
    "status": "success",
    "commandName": "Achat du produit XYZ",
    "commandRef": "ORDER_12345",
    "firstName": "John",
    "lastName": "Doe",
    "email": "john.doe@example.com",
    "phoneNumber": "771234567",
    "countryCode": "SN",
    "ipnUrl": "https://yourwebsite.com/webhook/kopar",
    "successUrl": "https://yourwebsite.com/payment/success",
    "cancelUrl": "https://yourwebsite.com/payment/cancel",
    "customFields": "{\"orderId\": \"12345\"}",
    "service": {
      "id": 1,
      "serviceName": "orange_money_sn",
      "label": "Orange Money Sénégal"
    },
    "merchant": {
      "id": 1,
      "name": "Your Business Name",
      "koparId": "MERCHANT_ID_XXXX"
    }
  },
  "availablesServices": [
    {
      "id": 1,
      "serviceName": "orange_money_sn",
      "label": "Orange Money Sénégal"
    },
    {
      "id": 2,
      "serviceName": "wave_sn",
      "label": "Wave Sénégal"
    }
  ],
  "receptionServices": []
}
```

**Valeurs du statut de transaction :**

| Statut | Description |
|---|---|
| `new` | Transaction créée mais pas encore traitée |
| `pending` | Paiement en cours de traitement |
| `success` | Paiement effectué avec succès |
| `failed` | Le paiement a échoué |
| `cancelled` | Le paiement a été annulé |
| `refunded` | Le paiement a été remboursé |

---

### 4. Remboursement d'une transaction

Demande le remboursement d'une transaction réussie.

**Endpoint :** `POST /api/v2/transaction/:token/refund`

**Paramètres d'URL :**

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `token` | string | Oui | Le token de la transaction à rembourser |

**En-têtes de requête :**
```
Content-Type: application/json
```

**Corps de la requête :**

```json
{ "reason": "" }
```

**Réponse de succès (200 OK) :**

```json
{
  "message": "Refund processing",
  "code": "REFUNDING"
}
```

**Réponse — déjà remboursé (400 Bad Request) :**

```json
{
  "message": "Transaction already refunded",
  "code": "ALREADY_REFUNDED"
}
```

**Réponse — statut invalide (400 Bad Request) :**

```json
{
  "message": "Transaction cannot be refunded in current status",
  "code": "INVALID_STATUS_FOR_REFUND"
}
```

> **Remarques**
> - Seules les transactions au statut `success` peuvent être remboursées
> - Les remboursements sont traités de manière asynchrone
> - Vous recevrez une notification webhook une fois le remboursement terminé

---

## Intégration Webhook (IPN)

Kopar Pay envoie des notifications de paiement instantanées (IPN) à votre serveur lorsque le statut d'une transaction change. Cela vous permet d'être informé en temps réel des résultats de paiement.

### Configuration du Webhook

1. Définissez votre `ipnUrl` lors de la création d'une transaction
2. Assurez-vous que votre endpoint webhook est accessible publiquement via HTTPS
3. Vérifiez la signature du webhook pour garantir son authenticité

### Requête du Webhook

**Méthode :** `POST`

**En-têtes :**
```
Content-Type: application/json
X-KOPAR-SIGNATURE: <signature_hash>
```

**Corps :**

```json
{
  "status": "success",
  "firstName": "John",
  "lastName": "Doe",
  "itemPrice": 10000,
  "itemPriceXof": 10000,
  "email": "john.doe@example.com",
  "phoneNumber": "771234567",
  "customFields": "{\"orderId\": \"12345\"}",
  "currency": "XOF",
  "commandRef": "ORDER_12345",
  "commandName": "Achat du produit XYZ"
}
```

### Vérification de la signature du Webhook

Pour vous assurer que la requête webhook provient bien de Kopar Pay et qu'elle n'a pas été altérée, vérifiez la signature :

**Algorithme de signature :** HMAC-SHA256

**Étapes de vérification :**

1. Extraire la signature de l'en-tête `X-KOPAR-SIGNATURE`
2. Créer un HMAC en utilisant votre clé privée marchande
3. Hacher le corps JSON brut avec le HMAC
4. Comparer le hash calculé avec la signature de l'en-tête

#### Exemple de vérification (Node.js)

```javascript
const crypto = require('crypto');

function verifyKoparSignature(requestBody, signature, privateKey) {
  const hmac = crypto.createHmac('sha256', privateKey);
  const computedSignature = hmac.update(JSON.stringify(requestBody), 'utf8').digest('hex');

  return computedSignature === signature;
}

// Dans votre endpoint webhook
app.post('/webhook/kopar', (req, res) => {
  const signature = req.headers['x-kopar-signature'];
  const isValid = verifyKoparSignature(req.body, signature, YOUR_PRIVATE_KEY);

  if (!isValid) {
    return res.status(401).send('Unauthorized');
  }

  // Traiter le webhook
  const { status, commandRef } = req.body;

  if (status === 'success') {
    // Mettre à jour le statut de la commande
    updateOrderStatus(commandRef, 'paid');
  } else if (status === 'failed') {
    // Gérer le paiement échoué
    updateOrderStatus(commandRef, 'failed');
  }

  // Toujours retourner 200 OK pour accuser réception
  res.status(200).send('OK');
});
```

#### Exemple de vérification (PHP)

```php
<?php
function verifyKoparSignature($requestBody, $signature, $privateKey) {
    $computedSignature = hash_hmac('sha256', $requestBody, $privateKey);
    return hash_equals($computedSignature, $signature);
}

// Dans votre endpoint webhook
$signature = $_SERVER['HTTP_X_KOPAR_SIGNATURE'];
$requestBody = file_get_contents('php://input');
$data = json_decode($requestBody, true);

if (!verifyKoparSignature($requestBody, $signature, YOUR_PRIVATE_KEY)) {
    http_response_code(401);
    exit('Unauthorized');
}

// Traiter le webhook
if ($data['status'] === 'success') {
    // Mettre à jour le statut de la commande
    updateOrderStatus($data['commandRef'], 'paid');
} else if ($data['status'] === 'failed') {
    // Gérer le paiement échoué
    updateOrderStatus($data['commandRef'], 'failed');
}

// Toujours retourner 200 OK
http_response_code(200);
echo 'OK';
?>
```

#### Exemple de vérification (Python)

```python
import hmac
import hashlib
import json

def verify_kopar_signature(request_body, signature, private_key):
    computed_signature = hmac.new(
        private_key.encode('utf-8'),
        request_body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, signature)

# Dans votre endpoint webhook (exemple Flask)
@app.route('/webhook/kopar', methods=['POST'])
def kopar_webhook():
    signature = request.headers.get('X-KOPAR-SIGNATURE')
    request_body = request.get_data(as_text=True)

    if not verify_kopar_signature(request_body, signature, YOUR_PRIVATE_KEY):
        return 'Unauthorized', 401

    data = request.get_json()

    if data['status'] == 'success':
        # Mettre à jour le statut de la commande
        update_order_status(data['commandRef'], 'paid')
    elif data['status'] == 'failed':
        # Gérer le paiement échoué
        update_order_status(data['commandRef'], 'failed')

    # Toujours retourner 200 OK
    return 'OK', 200
```

### Points d'attention Webhook

1. **Toujours vérifier la signature** — Ne jamais faire confiance à un webhook sans vérification de signature
2. **Retourner 200 OK rapidement** — Traiter les webhooks de manière asynchrone si nécessaire
3. **Être idempotent** — Gérer les livraisons dupliquées de webhook correctement
4. **Utiliser HTTPS** — S'assurer que votre endpoint webhook utilise SSL/TLS
5. **Gérer les tentatives de renvoi** — Kopar Pay renverra les webhooks échoués

---

## Codes de réponse

### Codes de statut HTTP

| Code | Description |
|---|---|
| 200 | Succès - Requête traitée avec succès |
| 400 | Bad Request - Paramètres ou format de requête invalide |
| 401 | Unauthorized - Clé API invalide ou échec d'authentification |
| 404 | Not Found - Transaction ou ressource introuvable |
| 406 | Not Acceptable - La requête ne peut pas être traitée |
| 500 | Internal Server Error - Erreur interne du serveur |

### Codes de statut de transaction

| Statut | Description |
|---|---|
| `new` | Transaction créée, en attente d'initiation de paiement |
| `pending` | Paiement en cours |
| `success` | Paiement effectué avec succès |
| `failed` | Le paiement a échoué |
| `cancelled` | Le paiement a été annulé par l'utilisateur |
| `refunded` | Le paiement a été remboursé |

### Codes de réponse API

| Code | Description |
|---|---|
| `SUCCESS` | Opération effectuée avec succès |
| `INIT_TRANSFER` | Transaction initiée |
| `REFUNDING` | Le remboursement est en cours de traitement |
| `ALREADY_REFUNDED` | La transaction a déjà été remboursée |
| `INVALID_STATUS_FOR_REFUND` | Le statut de la transaction ne permet pas le remboursement |
| `TRANSACTION_NOT_EXIST` | Transaction introuvable ou invalide |
| `SERVICE_NOT_ALLOWED` | Service de paiement non disponible |
| `FAILED` | L'opération a échoué |

---

## Gestion des erreurs

Toutes les erreurs suivent un format cohérent :

```json
{
  "status": "ERROR_CODE",
  "message": "Message d'erreur lisible",
  "errorCode": "SPECIFIC_ERROR_CODE",
  "errors": []
}
```

### Réponses d'erreur courantes

**Clé API invalide (401) :**

```json
{
  "status": "UNAUTHORIZED",
  "message": "Invalid API key",
  "errorCode": "INVALID_API_KEY"
}
```

**Transaction introuvable (404) :**

```json
{
  "status": "FAILED",
  "message": "Transaction not found"
}
```

**Transaction dupliquée (400) :**

```json
{
  "status": "DUPLICATE_TRANSACTION",
  "message": "A similar transaction is already pending",
  "errorCode": "DUPLICATE_TRANSACTION"
}
```

**Solde insuffisant (400) :**

```json
{
  "status": "INSUFFICIENT_BALANCE",
  "message": "Merchant balance insufficient",
  "errorCode": "INSUFFICIENT_BALANCE"
}
```

---

## Exemples

### Exemple de flux de paiement complet

**Étape 1 : Créer une demande de paiement**

```bash
curl -X POST https://koparpay.com/api/v2/transaction/request \
  -H "Content-Type: application/json" \
  -d '{
    "apiKey": "your_api_key",
    "itemPrice": 5000,
    "commandName": "Product Purchase",
    "commandRef": "ORD-2024-001",
    "firstName": "Amadou",
    "lastName": "Diallo",
    "email": "amadou@example.com",
    "phoneNumber": "771234567",
    "countryCode": "SN",
    "currency": "XOF",
    "ipnUrl": "https://mystore.com/webhook",
    "successUrl": "https://mystore.com/success",
    "cancelUrl": "https://mystore.com/cancel"
  }'
```

**Réponse :**

```json
{
  "message": "Transaction Initiated.",
  "status": "SUCCESS",
  "token": "KOPAR_ABC123XYZ"
}
```

**Étape 2 : Rediriger le client (si paiement avec redirection)**

```
https://koparpay.com/payment/KOPAR_ABC123XYZ
```

**Étape 3 : Recevoir la notification Webhook**

Votre endpoint webhook reçoit :

```json
{
  "status": "success",
  "firstName": "Amadou",
  "lastName": "Diallo",
  "itemPrice": 5000,
  "itemPriceXof": 5000,
  "email": "amadou@example.com",
  "phoneNumber": "771234567",
  "currency": "XOF",
  "commandRef": "ORD-2024-001",
  "commandName": "Product Purchase"
}
```

**Étape 4 : Vérifier le statut de la transaction**

```bash
curl -X GET https://koparpay.com/api/v2/transaction/KOPAR_ABC123XYZ \
  -H "Content-Type: application/json"
```

**Réponse :**

```json
{
  "status": "SUCCESS",
  "data": {
    "koparId": "KOPAR_ABC123XYZ",
    "status": "success",
    "amount": 5000,
    "commandRef": "ORD-2024-001"
  }
}
```

### Exemple de flux Checkout

**Étape 1 :** Créer la transaction (comme ci-dessus)

**Étape 2 :** Le client sélectionne un mode de paiement sur votre plateforme

**Étape 3 :** Traiter le checkout avec le service sélectionné

```bash
curl -X POST https://koparpay.com/api/v2/transaction/KOPAR_ABC123XYZ/checkout \
  -H "Content-Type: application/json" \
  -d '{
    "service": "orange_money_sn"
  }'
```

**Réponse :**

```json
{
  "data": {
    "transaction": {
      "koparId": "KOPAR_ABC123XYZ",
      "status": "pending"
    },
    "message": "Transfert Initié",
    "code": "INIT_TRANSFER",
    "data": {
      "paymentUrl": "https://payment.orange.sn/...",
      "qrCode": "data:image/png;base64,..."
    }
  }
}
```

### Exemple de remboursement

```bash
curl -X POST https://koparpay.com/api/v2/transaction/KOPAR_ABC123XYZ/refund \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Réponse :**

```json
{
  "message": "Refund processing",
  "code": "REFUNDING"
}
```

---

## Support

Pour toute assistance technique, aide à l'intégration, ou demande générale :

**E-mail :**
- seydou.ba@koparexpress.com
- contact@koparexpress.com

---

## Conditions d'utilisation

En utilisant l'API Kopar Pay, vous acceptez de :
- Garder vos identifiants API en sécurité
- Vous conformer à la réglementation applicable en matière de paiement
- Traiter correctement les données clients
- Mettre en œuvre une gestion des erreurs et des mesures de sécurité appropriées

---

*Version du document : 1.2 — Dernière mise à jour : Octobre 2025 — © 2024 Kopar Express. Tous droits réservés.*
