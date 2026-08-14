# MONCAP – Cahier des Charges Plateforme Web
### Mouvement National des Cadres Patriotes

**CAHIER DES CHARGES**
Plateforme Web d'Adhésion en Ligne
Plateforme Numérique Intégrée de Gestion des Cadres du MONCAP
Formulaire d'Adhésion Numérique & Gestion des Membres

| | |
|---|---|
| **Document** | Cahier des Charges v1.0 |
| **Commanditaire** | MONCAP / PASTEF – Patriotes du Sénégal |
| **Date** | Avril 2026 |
| **Statut** | Version initiale – Pour validation |

*Confidentiel – Usage interne MONCAP*

---

## Table des matières

1. [Contexte et présentation du projet](#1-contexte-et-présentation-du-projet)
   - 1.1 Présentation du MONCAP
   - 1.2 Problématique actuelle
   - 1.3 Objectifs du projet
2. [Périmètre fonctionnel](#2-périmètre-fonctionnel)
   - 2.1 Module 1 – Espace Public (Candidat)
   - 2.2 Module 2 – Back-office Administrateur
3. [Référentiel des commissariats scientifiques](#3-référentiel-des-commissariats-scientifiques)
4. [Exigences techniques](#4-exigences-techniques)
5. [Gestion des rôles et accès](#5-gestion-des-rôles-et-accès)
6. [Parcours utilisateur complet](#6-parcours-utilisateur-complet)
7. [Livrables attendus](#7-livrables-attendus)
8. [Planning prévisionnel](#8-planning-prévisionnel)
9. [Critères de réception et validation](#9-critères-de-réception-et-validation)
10. [Contraintes et hypothèses](#10-contraintes-et-hypothèses)
- [Annexe – Champs du formulaire d'adhésion](#annexe--champs-du-formulaire-dadhésion)

---

## 1. Contexte et présentation du projet

### 1.1 Présentation du MONCAP

Le Mouvement National des Cadres Patriotes (MONCAP) est une organisation politique affiliée au parti PASTEF – Patriotes du Sénégal. Il regroupe des cadres (professionnels et doctorants) engagés dans la réflexion et l'action au service du Sénégal, organisés en commissariats scientifiques couvrant tous les secteurs stratégiques du pays.

Le MONCAP a relancé sa campagne d'enrôlement et cherche à moderniser et automatiser le processus d'adhésion de ses membres.

### 1.2 Problématique actuelle

Actuellement, le processus d'adhésion est entièrement manuel :

- Les candidats téléchargent et remplissent un formulaire PDF
- Ils envoient le formulaire + CV + photo + paiement de 25 000 FCFA via WhatsApp (77 636 32 59)
- Le traitement est effectué manuellement par le permanent au siège (MONCAP FINANCE)
- Aucune base de données centralisée des adhérents n'existe
- Le suivi des cotisations mensuelles est difficile à gérer

Ce processus génère des risques de perte de données, d'inefficacité, et ne reflète pas la vocation modernisatrice du mouvement.

### 1.3 Objectifs du projet

Le MONCAP souhaite développer une plateforme web permettant de :

- Digitaliser entièrement le processus d'adhésion
- Centraliser les données des membres dans une base de données sécurisée
- Automatiser la collecte des frais d'adhésion (25 000 FCFA) et des cotisations mensuelles
- Offrir un espace de gestion administratif pour les coordinateurs du MONCAP
- Faciliter la communication avec les membres par commissariat scientifique ou région

---

## 2. Périmètre fonctionnel

### 2.1 Module 1 – Espace Public (Candidat)

#### 2.1.1 Page d'accueil et présentation

La page d'accueil devra présenter :

- La charte graphique du MONCAP (couleurs rouge, vert, noir conformes au logo)
- Le message d'appel à l'enrôlement
- Les conditions d'adhésion clairement affichées
- Un appel à l'action (CTA) vers le formulaire d'adhésion
- Les informations de contact (WhatsApp : 77 636 32 59)

#### 2.1.2 Formulaire d'adhésion en ligne

Le formulaire numérique reprendra fidèlement le formulaire papier officiel (FICHE_ADH.pdf) et sera structuré en 6 sections :

| Section | Champs requis |
|---|---|
| 1 – Informations personnelles | Nom, Prénom(s), Date de naissance, Lieu de naissance, Profession, Tél. fixe, Tél. mobile, E-mail, N° CNI, N° Carte électeur |
| 2 – Adresse domicile | Région, Département, Commune |
| 3 – Adresse militantisme | Région, Département, Commune |
| 4 – Profilage | Fonction professionnelle, Type d'engagement militant (Politique / Syndicalisme / Société civile / Autre) |
| 5 – Commissariat scientifique | Choix parmi les 29 commissariats disponibles (case à cocher unique) |
| 6 – Contribution financière | Mode de paiement (Prélèvement bancaire / Espèces / OM, WAVE, FREE, Carte bancaire) |

**Règles de validation du formulaire :**

- Tous les champs marqués obligatoires doivent être remplis avant soumission
- Format email valide obligatoire
- Numéro de téléphone au Sénégal et à l'international
- Un seul commissariat scientifique sélectionnable
- Téléchargement obligatoire du CV (PDF ou DOCX, max 5 Mo)
- Téléchargement obligatoire d'une photo d'identité (JPG/PNG, max 2 Mo)
- Certification sur l'honneur de l'exactitude des informations (checkbox obligatoire)

#### 2.1.3 Conditions d'éligibilité

Le système devra vérifier (par déclaration du candidat) les conditions minimales d'adhésion :

- Avoir le niveau Bac+4 avec au moins 3 ans d'expérience professionnelle

**OU**

- Être doctorant en 2ème année de thèse dans le domaine du commissariat choisi

En cas de non-conformité déclarée, le formulaire affiche un message d'inéligibilité sans bloquer l'envoi (pour permettre une validation manuelle ultérieure).

#### 2.1.4 Paiement en ligne

Le module de paiement devra intégrer les solutions locales suivantes :

- Wave (API Wave Sénégal)
- Orange Money (API OM Sénégal)
- Free Money
- Carte bancaire (Visa/Mastercard via Stripe ou PayTech Sénégal)

**Montants :**

- Frais d'adhésion unique : 25 000 FCFA
- Cotisation mensuelle : 1 025 000 FCFA/mois *(5% de réduction si prélèvement bancaire automatique)*
- Génération automatique d'un reçu de paiement (PDF téléchargeable)

> ⚠️ *Note : le montant de la cotisation mensuelle indiqué dans le document original (« 1025 000 FCFA/mois ») semble contenir une erreur de frappe à vérifier avec le commanditaire.*

#### 2.1.5 Confirmation et suivi de dossier

Après soumission du formulaire et paiement :

- Envoi d'un e-mail de confirmation automatique au candidat
- Envoi d'un SMS de confirmation au numéro mobile renseigné
- Attribution d'un numéro de dossier unique pour le suivi
- Page de statut en ligne permettant au candidat de vérifier l'avancement de son dossier

### 2.2 Module 2 – Back-office Administrateur

#### 2.2.1 Tableau de bord

Le tableau de bord devra afficher :

- Nombre total d'adhérents actifs
- Évolution mensuelle
- Taux d'activité
- Nouveaux dossiers en attente de validation
- Répartition des membres par commissariat scientifique
- Répartition des membres par profession
- Cartographie nationale des compétences
- Indicateurs par commissariat
- Indicateurs par région
- Répartition géographique (par région/département ou par pays/ville pour la diaspora)
- Statistiques des paiements (adhésions + cotisations du mois en cours)

#### 2.2.2 Gestion des dossiers d'adhésion

- Liste des dossiers avec filtres (statut, commissariat, région, pays, date)
- Visualisation de chaque dossier complet (formulaire + CV + photo)
- Actions disponibles : Valider / Rejeter / Mettre en attente / Demander complément
- Envoi d'e-mail automatique au candidat à chaque changement de statut
- Export des dossiers en CSV ou Excel

#### 2.2.3 Gestion des membres actifs

- Fiche membre complète consultable et modifiable
- Historique des cotisations mensuelles avec statut de paiement
- Relance automatique par SMS/email pour les cotisations impayées
- Désactivation/réactivation d'un membre
- Génération de la carte de membre numérique (PDF)
- Traçabilité complète des cotisations

Au-delà du simple suivi des paiements, il faudrait permettre :

- Un historique complet des cotisations depuis l'adhésion
- Un tableau de bord individuel indiquant les cotisations payées, en retard et à venir
- Une génération automatique des reçus
- Des relances automatiques (SMS, WhatsApp et e-mail)
- Un prélèvement automatique lorsque le membre l'autorise
- Des rapports financiers par région, pays (pour la diaspora), commissariat, profession et période
- Une traçabilité comptable avec numéro unique de transaction et piste d'audit éventuellement

**Gestion du profil des cadres**

Chaque cadre disposerait d'un véritable profil numérique comprenant :

- CV actualisé
- Diplômes
- Certifications
- Domaines d'expertise
- Expériences professionnelles
- Publications
- Langues parlées
- Disponibilité
- Centres d'intérêt

Ainsi, le mouvement disposerait d'une cartographie nationale des compétences.

**Base nationale des compétences**

Cette fonctionnalité permettrait notamment :

- La recherche d'experts par domaine
- L'identification des profils pour les commissions techniques
- La constitution rapide d'équipes de réflexion
- L'identification des experts par région ou département

*Exemple : « Trouver tous les économistes spécialisés en finances publiques dans la région de Thiès. »*

**Gestion des missions et engagements**

Chaque membre pourrait recevoir :

- Des missions
- Des invitations
- Des groupes de travail
- Des consultations
- Des convocations

Le système suivrait :

- Le taux de participation
- Les rapports produits
- Les missions réalisées
- Les responsabilités exercées

**Évaluation de l'engagement**

Un tableau de bord pourrait mesurer :

- La régularité des cotisations
- La participation aux activités
- Les formations suivies
- Les contributions scientifiques
- Les responsabilités assumées

Cela permettrait d'identifier les cadres les plus actifs.

#### 2.2.4 Gestion des commissariats

- Vue par commissariat avec liste des membres rattachés
- Coordinateur de commissariat avec accès restreint à son périmètre
- Outils de communication interne par commissariat (messagerie ou export de liste)
- Donner des missions
- Faire des invitations
- Faire des convocations

#### 2.2.5 Gestion financière

- Tableau de suivi des paiements d'adhésion et cotisations
- Rapports mensuels de trésorerie exportables
- Historique complet des transactions
- Alertes en cas d'échec de paiement

**Gestion des événements**

Pour les assemblées, conférences et formations :

- Inscription en ligne
- QR Code de présence
- Feuille de présence automatique
- Attestations de participation

**Communication interne**

Prévoir :

- Une messagerie interne
- Des sondages
- Des newsletters
- Forums par commissariats

**Coin documentaire**

Créer une bibliothèque numérique contenant :

- Les statuts
- Le règlement intérieur
- Les notes politiques
- Les rapports
- Les comptes rendus
- Les documents de travail
- Les vidéos de formation

**Formation des cadres**

Créer un espace e-learning avec :

- Vidéos
- Documents
- Quiz
- Parcours de formation
- Certifications internes

**Annuaire intelligent des cadres**

Un moteur de recherche multicritère permettrait de retrouver rapidement un membre selon :

- Profession
- Spécialité
- Région
- Département
- Commissariat
- Ancienneté
- Disponibilité

**Gestion des nominations**

Le système pourrait enregistrer :

- Les responsabilités internes
- Les mandats
- Les commissions
- Les nominations
- L'historique des fonctions

**Observatoire des compétences**

Un tableau de bord stratégique mettrait en évidence :

- Les secteurs où le mouvement est fortement représenté
- Les domaines où il manque des compétences
- Les besoins futurs en recrutement de cadres

---

## 3. Référentiel des commissariats scientifiques

Le système devra gérer exactement les 29 commissariats scientifiques suivants (source : formulaire officiel MONCAP) :

| Commissariat | Commissariat |
|---|---|
| Énergie | Environnement et Assainissement |
| Hydraulique | Sport |
| Économie et Planification | Culture |
| Infrastructures et Transports | Tourisme |
| Justice et Questions Juridiques | Artisanat |
| Élevage | Habitat, Urbanisme et Aménagement |
| Pêche | Décentralisation et Réforme Terr. |
| Industries, Mines et Carrières | Numérique et Communication |
| Enseignement Supérieur | Économie Sociale et Solidaire |
| Formation Professionnelle | Agriculture |
| Commerce et Entrepreneuriat | Éducation Nationale |
| Santé et Protection Sociale | Affaires Étrangères et Panaf. |
| Travail, Emploi et Réforme Pub. | Bonne Gouvernance |
| Finances Publiques et Budget | — |

---

## 4. Exigences techniques

### 4.1 Architecture recommandée

| Composant | Technologie recommandée |
|---|---|
| Frontend | React.js ou Vue.js (interface moderne et réactive) |
| Backend | Node.js (Express) ou Django (Python) |
| Base de données | PostgreSQL (données structurées) + S3/Cloudinary (fichiers CV, photos) |
| Authentification | JWT + OAuth2 (connexion sécurisée pour admin) |
| Paiements | Wave API, Orange Money API, PayTech/Stripe |
| Emails/SMS | SendGrid (emails) + Twilio ou Infobip (SMS) |
| Hébergement | VPS Sénégal ou AWS (région africaine) + CDN Cloudflare |
| SSL/HTTPS | Let's Encrypt (obligatoire sur toutes les pages) |

### 4.2 Compatibilité et accessibilité

- Responsive Design obligatoire (mobile-first, priorité au smartphone)
- Compatible avec les navigateurs Chrome, Firefox, Safari, Edge (2 dernières versions)
- Temps de chargement < 3 secondes sur connexion 3G
- Support des navigateurs Android et iOS
- Conformité WCAG 2.1 niveau AA (accessibilité)

### 4.3 Sécurité

- Chiffrement SSL/TLS sur l'ensemble du site
- Protection contre les injections SQL et les attaques XSS/CSRF
- Données personnelles stockées conformément aux réglementations sénégalaises (CDP)
- Authentification à deux facteurs (2FA) pour les comptes administrateurs
- Journalisation de tous les accès et modifications (logs d'audit)
- Sauvegarde automatique quotidienne de la base de données
- Les fichiers (CV, photos) stockés sur serveur sécurisé avec accès restreint

### 4.4 Performance

- Disponibilité cible : 99,5% (SLA)
- Capacité à gérer 500 utilisateurs simultanés minimum
- Temps de réponse API < 500ms pour les opérations courantes
- Pagination des listes (max 50 enregistrements par page)

---

## 5. Gestion des rôles et accès

| Rôle | Droits et accès |
|---|---|
| Super Administrateur | Accès complet : gestion des utilisateurs, configuration système, tous les commissariats, rapports financiers complets, export de données |
| Administrateur MONCAP | Validation/rejet des dossiers, gestion des membres, accès aux rapports nationaux, envoi de communications |
| Commissaire / Coordinateur de Commissariat | Accès limité aux membres de son commissariat, consultation des dossiers en attente de son périmètre, messagerie interne |
| Coordinateur Régional | Vue des membres de sa région, suivi des dossiers de sa région |
| Candidat (public) | Soumission du formulaire, suivi de son dossier avec son numéro unique, téléchargement de son reçu et carte membre |

---

## 6. Parcours utilisateur complet

### 6.1 Parcours Candidat

| Étape | Description |
|---|---|
| 1 – Découverte | Visite de la page d'accueil, lecture des conditions d'adhésion |
| 2 – Saisie du formulaire | Remplissage des 6 sections du formulaire en ligne, upload CV + photo |
| 3 – Paiement | Sélection du mode de paiement, paiement des 25 000 FCFA de frais d'adhésion |
| 4 – Confirmation | Réception d'un email et SMS de confirmation + numéro de dossier |
| 5 – Instruction du dossier | Le MONCAP examine le dossier (délai indicatif : 5-10 jours ouvrables) |
| 6 – Notification de décision | Email/SMS notifiant la validation, le rejet, ou une demande de complément |
| 7 – Activation | Si validé : accès à la carte de membre numérique et profil en ligne |

### 6.2 Parcours Administrateur

- Connexion sécurisée au back-office
- Consultation du tableau de bord et des alertes
- Traitement des dossiers en attente
- Suivi des cotisations et relances automatiques
- Génération de rapports

---

## 7. Livrables attendus

| Livrable | Description |
|---|---|
| L1 – Maquettes UI/UX | Wireframes et maquettes graphiques haute fidélité (desktop + mobile) pour validation avant développement |
| L2 – Base de données | Schéma de base de données complet et documenté |
| L3 – API documentée | Documentation Swagger/OpenAPI de tous les endpoints |
| L4 – Application web | Frontend + Backend déployé sur environnement de recette pour tests |
| L5 – Tests | Rapport de tests fonctionnels, de charge et de sécurité |
| L6 – Mise en production | Déploiement sur l'environnement de production avec SSL configuré |
| L7 – Formation | Session de formation pour les administrateurs MONCAP (2h minimum) |
| L8 – Documentation | Manuel utilisateur (admin + candidat) + documentation technique |
| L9 – Maintenance | Contrat de maintenance corrective 6 mois minimum post-livraison |

---

## 8. Planning prévisionnel

| Phase | Durée estimée |
|---|---|
| Phase 1 – Cadrage & Maquettes | 2 jours |
| Phase 2 – Développement Backend & BDD | 4 jours |
| Phase 3 – Développement Frontend | 3 jours |
| Phase 4 – Intégration paiement | 2 jours |
| Phase 5 – Tests & Recette | 2 jours |
| Phase 6 – Déploiement & Formation | 1 semaine |
| **TOTAL ESTIMÉ** | **~3 semaines** |

---

## 9. Critères de réception et validation

### 9.1 Critères fonctionnels

- Le formulaire en ligne est conforme à 100% au formulaire papier officiel (FICHE_ADH.pdf)
- Les 29 commissariats scientifiques sont correctement listés et sélectionnables
- Les paiements mobile money (Wave, OM) fonctionnent en environnement de production
- Les emails de confirmation sont reçus en moins de 2 minutes
- Le back-office permet de valider/rejeter un dossier en moins de 3 clics

### 9.2 Critères techniques

- Aucune faille de sécurité critique détectée lors du test de pénétration
- Temps de chargement de la page d'accueil < 3 secondes (réseau 3G)
- Disponibilité de 99,5% sur les 30 premiers jours de production
- Conformité RGPD/CDP des données personnelles
- Code source documenté et livré au MONCAP

---

## 10. Contraintes et hypothèses

### 10.1 Contraintes

- La charte graphique du MONCAP (rouge, vert, noir) doit être strictement respectée
- Le formulaire doit être disponible en français uniquement
- Le système doit fonctionner même avec une connexion internet instable (mode offline partiel souhaitable)
- Le prestataire devra assurer une confidentialité stricte des données des adhérents

### 10.2 Hypothèses

- Le MONCAP fournira le logo officiel en haute définition
- Le MONCAP désignera un référent technique disponible pour les questions de validation
- Les accès aux API de paiement (Wave, OM, Free) seront fournis par le MONCAP
- Le nom de domaine moncap.sn ou équivalent sera réservé par le MONCAP

---

## Annexe – Champs du formulaire d'adhésion

Récapitulatif détaillé de tous les champs issus du formulaire officiel FICHE_ADH.pdf :

| Section | Champ | Type | Obligatoire |
|---|---|---|---|
| Infos personnelles | Nom | Texte | Oui |
| Infos personnelles | Prénom(s) | Texte | Oui |
| Infos personnelles | Date de naissance | Date | Oui |
| Infos personnelles | Lieu de naissance | Texte | Oui |
| Infos personnelles | Profession | Texte | Oui |
| Infos personnelles | Tél. fixe | Téléphone | Non |
| Infos personnelles | Tél. mobile | Téléphone | Oui |
| Infos personnelles | E-mail | Email | Oui |
| Infos personnelles | N° CNI | Texte | Oui |
| Infos personnelles | N° Carte électeur | Texte | Non |
| Adresse domicile | Région | Liste déroulante | Oui |
| Adresse domicile | Département | Liste déroulante | Oui |
| Adresse domicile | Commune | Texte | Oui |
| Adresse militantisme | Région | Liste déroulante | Oui |
| Adresse militantisme | Département | Liste déroulante | Oui |
| Adresse militantisme | Commune | Texte | Non |
| Profilage | Fonction professionnelle | Texte | Oui |
| Profilage | Type d'engagement | Radio (4 choix) | Oui |
| Commissariat | Commissariat scientifique | Case à cocher (1 seul) | Oui |
| Contribution | Mode de paiement | Radio (4 choix) | Oui |
| Documents | CV | Upload PDF/DOCX | Oui |
| Documents | Photo d'identité | Upload JPG/PNG | Oui |
| Certification | Engagement sur l'honneur | Checkbox | Oui |

---

*Fin du Cahier des Charges – MONCAP Plateforme Web d'Adhésion*
*Document confidentiel – Propriété du MONCAP / PASTEF – Patriotes du Sénégal*
