# Legal Compliance — Droit français

> Source de vérité ≡ §17 du spec (2026-05-29)
> **AVERTISSEMENT : Ce document est une base sérieuse à adapter au cas d'espèce.
> Il ne constitue pas un conseil juridique. Toute prestation significative doit
> faire l'objet d'une relecture par un juriste du client ou de l'opérateur.**
> Back: [SKILL.md](../SKILL.md)

---

## 1. Contrat de prestation de services

### Base légale

| Article | Objet |
|---------|-------|
| **Code civil art. 1101 s.** | Formation du contrat : consentement, capacité, objet, cause |
| **Code civil art. 1112 s.** | Négociation de bonne foi ; obligations pré-contractuelles d'information |
| **Code civil art. 1193 s.** | Modification par accord des parties |
| **Code civil art. 1231 s.** | Responsabilité contractuelle : mise en demeure, dommages-intérêts, préjudice prévisible |
| **Code civil art. 1302 s.** | Enrichissement injustifié (applicable si prestation livrée sans contrat signé) |

### Clauses obligatoires dans `contract.md.j2`

- **Objet** : description précise de la prestation (fine-tuning du modèle X, sur tâche Y, pour durée Z)
- **Prix et jalons** : montants par phase (cf. [pricing-packaging.md](pricing-packaging.md)), conditions de paiement
- **Clause limitative de responsabilité** : plafonnée au montant total du contrat (art. 1231-3 : préjudice prévisible lors de la formation)
- **Propriété intellectuelle** : voir §2 ci-dessous
- **Données** : voir §4 (RGPD)
- **Confidentialité** : renvoi au NDA ou intégrée (voir §3)
- **Réversibilité** : remise de tous les livrables au client en fin de prestation
- **Non-réutilisation** : l'opérateur ne réutilise pas les données client ni le modèle entraîné à d'autres fins
- **Résiliation** : conditions et préavis

Outil : `generate_contract` (47). Le gabarit `contract.md.j2` cite la base légale de chaque clause.

---

## 2. Propriété intellectuelle

### Base légale

| Article | Objet |
|---------|-------|
| **CPI art. L111-1** | Droit d'auteur de l'auteur d'une œuvre de l'esprit |
| **CPI art. L113-9** | Œuvres créées dans le cadre d'une relation de travail salarié |
| **CPI art. L131-1 s.** | Cession des droits patrimoniaux (doit être explicite et limitée dans son objet) |
| **CPI art. L341-1 s.** | Protection des bases de données (droit sui generis du producteur) |

### Questions à trancher dans le contrat

- **Titularité du modèle fine-tuné** : qui est titulaire du modèle affiné (adaptateur + poids fusionnés) ?
  - Par défaut : le client commande et finance → le client est le destinataire et doit être cessionnaire
  - L'opérateur cède tous les droits patrimoniaux sur le modèle fine-tuné au client, contre paiement complet
- **Licence sur le modèle de base** : l'opérateur ne peut céder que ce qu'il détient → vérifier la licence du modèle de base via `verify_model_license` (36)
  - Apache-2.0 / MIT : cession ou sous-licence possible sans restriction
  - Llama Community / Gemma : restrictions d'usage commercial et de redistribution → auditer avant toute cession
- **Données d'entraînement** : appartiennent au client ; l'opérateur n'en acquiert aucun droit
- **Scripts et code produits** : le client reçoit les sources (train.py, eval.py, Dockerfiles, configs) avec une licence permissive (MIT)

---

## 3. Secret des affaires & confidentialité

### Base légale

| Article | Objet |
|---------|-------|
| **Code de commerce art. L151-1** | Définition du secret des affaires |
| **Code de commerce art. L151-2** | Conditions de la protection (valeur commerciale, mesures raisonnables) |
| **Code de commerce art. L152-1 s.** | Actions en justice ; sanctions |
| **Directive UE 2016/943** | Transposée par ordonnance du 23 octobre 2018 |

### NDA bilatéral — points clés

Le gabarit `nda.md.j2` (outil `generate_nda`, 48) couvre :

- Définition des informations confidentielles : données d'entraînement, architecture, métriques, savoir-faire
- Obligations de protection (mesures raisonnables = chiffrement, accès restreint, journalisation)
- Durée : 3 ans minimum post-prestation (ou durée de la vie commerciale du modèle si supérieure)
- Exceptions légales : domaine public, disclosure par autorité compétente
- Juridiction : Paris, droit français

**Toujours signer le NDA avant de partager tout document technique sur le projet.**

---

## 4. Données personnelles — RGPD + Loi Informatique et Libertés

### Base légale

| Texte | Article | Objet |
|-------|---------|-------|
| **RGPD (UE 2016/679)** | Art. 5-1-c | Minimisation des données |
| RGPD | Art. 6 | Licéité du traitement (base légale) |
| RGPD | Art. 17 | Droit à l'effacement (→ certificat de destruction) |
| RGPD | Art. 28 | Contrat de sous-traitance / DPA obligatoire |
| RGPD | Art. 30 | Registre des activités de traitement |
| RGPD | Art. 32 | Sécurité du traitement (chiffrement, pseudonymisation, intégrité) |
| RGPD | Art. 33-34 | Notification de violation (72h CNIL ; communication aux personnes si risque élevé) |
| **Loi n°78-17** | — | Loi Informatique et Libertés (modifiée) — complète le RGPD en droit français |
| **CNIL** | Lignes directrices IA | Bases légales pour l'utilisation de données en IA/ML |

### Cartographie des obligations par cas

#### Cas A : données d'entraînement ne contiennent PAS de données personnelles

- Pas de DPA requis
- Mentionner explicitement dans le contrat (clause données)
- Architecture Zero-Data : opérateur ne voit jamais les données → minimisation naturelle

#### Cas B : données d'entraînement contiennent des données personnelles (emails clients, conversations, etc.)

Obligations :
1. **Base légale** (art. 6) : le client doit identifier sa base légale pour le traitement (consentement, intérêt légitime, etc.)
2. **DPA / contrat de sous-traitance** (art. 28) : obligatoire entre client (responsable de traitement) et opérateur (sous-traitant). Clauses : finalité limitée, instructions documentées, sécurité (art. 32), sub-traitants notifiés, assistance audit.
3. **Registre** (art. 30) : le client doit enregistrer le traitement dans son registre
4. **Minimisation** (art. 5-1-c) : `anonymize_dataset_preview` (outil 9) + architecture Zero-Data servent directement cet objectif → argument de conformité
5. **Sécurité** (art. 32) : chiffrement AES-256 (`encrypt_deliverable`, 44), audit no-network (`audit_code_no_network`, 33), cloisonnement dans l'enclave
6. **Effacement** (art. 17) : à la fin de la prestation, `generate_destruction_certificate` (52) prouve la destruction irréversible
7. **Violation** (art. 33-34) : si incident → notifier CNIL sous 72h, notifier personnes si risque élevé

#### Certificat de destruction (`generate_destruction_certificate`, outil 52)

Le certificat doit contenir :
- Liste des fichiers/volumes détruits
- Méthode : `shred -u` (GNU), `secure-delete`, purge Docker volume, suppression workspace
- Date et heure de destruction
- Signature de l'opérateur
- SHA256 du certificat lui-même (pour preuve d'intégrité)

**Timing :** émettre APRÈS confirmation écrite que le client a reçu et vérifié le livrable, et AVANT fermeture du projet.

---

## 5. Réflexe Zero-Data comme argument de conformité RGPD

L'architecture Zero-Data n'est pas seulement technique — c'est un argument
juridique fort :

| Exigence RGPD | Comment Zero-Data y répond |
|--------------|---------------------------|
| Minimisation (art. 5-1-c) | L'opérateur ne reçoit jamais les données ; seules des métriques anonymisées circulent |
| Sécurité (art. 32) | Chiffrement AES-256-GCM, audit no-network, enclave client |
| Sous-traitance (art. 28) | Le DPA peut noter que l'opérateur n'accède pas aux données en vertu de l'architecture technique |
| Effacement (art. 17) | La destruction concerne les copies opérateur (synthétiques + logs) ; l'original reste chez le client |

---

## 6. Outils et gabarits correspondants

| Besoin légal | Outil MCP | Gabarit |
|-------------|-----------|---------|
| Contrat de prestation | `generate_contract` (47) | `contract.md.j2` |
| NDA | `generate_nda` (48) | `nda.md.j2` |
| DPA / contrat de sous-traitance | `generate_contract` (47) avec clauses DPA | Extension `contract.md.j2` |
| Certificat de destruction | `generate_destruction_certificate` (52) | `destruction_cert.md.j2` |
| Facture | `generate_invoice` (60) | `invoice.md.j2` |
| Vérification licence modèle | `verify_model_license` (36) | Registre local |

---

*Figé au 2026-05-29. Réévaluer à chaque nouveau projet et lors d'évolutions
législatives (CNIL, Parlement européen, Cour de cassation).*
