# Pricing & Packaging — Offre Fine-Tuning OS

> Source de vérité ≡ §15 du spec (2026-05-29)
> **Fourchettes indicatives EUR, mai 2026. À ajuster au marché, au positionnement
> et au contexte client.**
> Back: [SKILL.md](../SKILL.md)

---

## 1. Positionnement & différenciateur

**Argument principal :** les FT API managées (Together, Fireworks, OpenAI FT)
exigent l'envoi des données hors de l'infrastructure client → incompatibles
avec les exigences de confidentialité, RGPD, et secret des affaires. Fine-Tuning
OS entraîne en enclave client — la donnée ne sort jamais.

**Premium Zero-Data :** +10-25% justifié vs prestation standard, en échange de :
- Certificat d'audit no-network (`audit_code_no_network`)
- Architecture enclave documentée
- Certificat de destruction irréversible
- Rapport de sécurité livrable

---

## 2. Structure d'offre — jalons facturables

| Phase facturable | Jalon de validation | Fourchette indicative |
|-----------------|--------------------|-----------------------|
| **Cadrage & faisabilité** | Spec validée par client (contrat signé, schéma défini, licence vérifiée) | 2 000 – 5 000 € |
| **Pipeline & preuve synthétique** | Démo pipeline opérationnelle + rapport sécurité | 4 000 – 10 000 € |
| **Entraînement & évaluation** | Approbation des métriques (`request_client_approval`) | 6 000 – 20 000 € |
| **Packaging & livraison** | Bon de livraison + SHA256 acceptés + livrable reçu | 3 000 – 8 000 € |
| **Documentation complète** | Guides + certificat de destruction + contrats signés | Inclus ou 1 000 – 3 000 € |
| **Maintenance / retraining** (option récurrente) | SLA dérive/retraining déclenché | 500 – 3 000 €/mois ou forfait/itération |

### Prestation type — enveloppe totale

| Profil | Fourchette | Hypothèses |
|--------|-----------|------------|
| One-shot 7-13B, LoRA/QLoRA | 15 000 – 40 000 € | 1-2 itérations, données propres |
| 70B QLoRA | 25 000 – 60 000 € | Coût GPU plus élevé, setup complexe |
| MoE (Qwen MoE 235B-A22B) | 40 000 – 100 000 € | Rare en prestation ; infra cliente lourde |
| Maintenance 12 mois | 6 000 – 24 000 €/an | 1 check/mois + 1-2 retrain/an |

---

## 3. Coûts sous-jacents (référence interne)

| Ressource | Coût (ordre de grandeur, mai 2026) |
|-----------|----------------------------------|
| A100 80G cloud | 1 – 2 €/h |
| H100 80G cloud | 2 – 4 €/h |
| H200 / B200 | > 4 €/h (marché tendu) |
| LoRA 7B, 3 epochs, ~10k exemples | 2-6h A100 → 2 – 12 € GPU |
| QLoRA 70B, 1 epoch | 15-30h A100 → 15 – 60 € GPU |
| Stockage livrable (100 Go) | 2 – 5 €/mois |

**Marge opérateur :** les fourchettes ci-dessus intègrent la marge et la valeur
du savoir-faire (pipeline, sécurité, livraison). Le coût GPU pur représente
souvent < 5% du prix de vente.

---

## 4. Modèle commercial recommandé

| Option | Avantages | Risques |
|--------|-----------|---------|
| **Forfait par phase** (recommandé) | Prévisibilité client ; limites de scope claires | Sur-engagement si phases longues |
| Régie (TJM) | Flexible | Dérive de budget ; difficulté à vendre le "résultat" |
| Forfait global + options | Simple à vendre | Risque de dépassement |

**Acompte :** 30% à la signature du contrat, avant tout travail.
**Paiement :** 30% post-validation pipeline, 30% post-validation métriques, 10% post-livraison.

Outils : `generate_invoice` (60) émet la facture PDF. `request_client_approval` (59) matérialise le jalon.

---

## 5. SLA & maintenance

Définir contractuellement (dans `generate_contract`, outil 47) :

| SLA item | Valeur typique | Outil de mesure |
|----------|---------------|-----------------|
| Fréquence de check de dérive | Mensuelle | `check_model_rot` (61) |
| Seuil déclenchant retraining | 5% dégradation accuracy | `check_model_rot` verdict |
| Délai de réponse incident | 2 jours ouvrés | `send_status_update` (56) |
| Délai de livraison retraining | 5-10 jours ouvrés | Nouveau cycle Phase 2-7 |
| Mise à jour modèle de base | Revue trimestrielle | `update_base_model` (63) |
| Support serveur MCP | ≥ 99% disponibilité (si hébergé opérateur) | `mcp_self_update` (64) |

---

## 6. Comparaison avec les alternatives

| Solution | Prix (ordre de grandeur) | Confidentialité données | Zero-Data |
|----------|--------------------------|-------------------------|-----------|
| **Fine-Tuning OS** (nous) | 15-40k€ one-shot | Données en enclave client | **Oui** |
| Together Fine-tuning API | ~$6-12/M tokens train + hosting | Données sur infra Together | Non |
| OpenAI Fine-tuning | ~$8/M tokens train | Données sur infra OpenAI | Non |
| Fireworks Fine-tuning | ~$1-5/M tokens | Données sur infra Fireworks | Non |
| Prestataire GPU brut | Variable + surcoût opérations | Dépend du contrat | Rarement |

**Argument commercial clé :** pour un client ayant des données sensibles
(médical, légal, RH, financier), les alternatives managées sont juridiquement
risquées ou impossibles. Fine-Tuning OS est la seule option compliant.

---

## 7. Outils MCP associés à chaque jalon

| Jalon | Outil de matérialisation |
|-------|--------------------------|
| Spec validée | `generate_contract` (47) + `log_project_event` (58) |
| Pipeline prouvée | `generate_security_report` (37) + `request_client_approval` (59) |
| Métriques approuvées | `generate_performance_report` (49) + `request_client_approval` (59) |
| Livraison acceptée | `generate_delivery_note` (46) + `log_project_event` (58) |
| Destruction certifiée | `generate_destruction_certificate` (52) |
| Facture émise | `generate_invoice` (60) |

---

*Figé au 2026-05-29. À réévaluer chaque trimestre en fonction du marché GPU,
de la concurrence API, et de l'évolution des réglementations.*
