# Fine-Tuning OS — Spécification de conception

- **Date** : 2026-05-29
- **Statut** : Validé (design approuvé), prêt pour planification d'implémentation
- **Auteur** : Claude Code + bojac
- **Cible** : (1) serveur MCP Python exposant 64 outils + (2) skill Claude Code compagnon (manuel métier) pour une prestation de fine-tuning « Zero-Data »

---

## 1. Objectif & contexte

Fine-Tuning OS est un serveur MCP (Model Context Protocol) qui transforme Claude Code en **chef d'orchestre exécutant** d'une prestation professionnelle de fine-tuning de LLM. Il expose 64 outils atomiques que Claude combine pour couvrir tout le cycle de vie : préparation, données synthétiques, construction de pipeline, exécution d'entraînement, évaluation, sécurité/audit, packaging/livraison, documentation/contrats, relation client, maintenance.

Le serveur suit **exactement le même pattern** que les serveurs MCP existants de l'utilisateur (`crypto-mining-mcp`, `souverain/agent/mining-mcp`) : Python, SDK officiel `mcp` avec `FastMCP`, `pydantic`, build `hatchling`, layout `src/<pkg>/`, transport stdio, un module par domaine.

### Non-objectifs (hors périmètre v1)

- Aucun entraînement de modèle **dans** le processus du serveur (pas de `torch`/`unsloth`/`transformers` en dépendance du serveur).
- Aucun accès aux données réelles du client par Claude ou par le serveur.
- Pas d'interface graphique. Pas de base de données externe (état sur disque, JSON).

---

## 2. Principe Zero-Data (cœur de l'architecture)

**Règle absolue : ni Claude, ni le serveur, ne voient jamais les données réelles du client ni les poids entraînés en clair sortis de l'enclave.**

Conséquences architecturales :

1. Les outils qui **manipulent des données réelles** (ex. `trigger_remote_training`, `evaluate_on_validation_set`) ne s'exécutent **jamais** côté serveur : ils produisent la commande/artefact exact à lancer dans l'enclave client, et ne reçoivent en retour que des **métriques/logs assainis**.
2. Les outils de **préparation** (ex. `generate_synthetic_dataset`, `create_training_config`) travaillent **exclusivement sur des spécifications abstraites** (schémas, types, paramètres) — jamais sur du contenu réel.
3. Les outils de **sécurité** (ex. `sanitize_logs_for_claude`, `scan_data_leakage_risk`) vérifient en permanence l'absence de fuite et alimentent un rapport de sécurité livrable.

Toute donnée entrant dans le serveur depuis l'extérieur (logs, échantillons de debug) **doit** passer par `sanitize.py` avant d'être renvoyée à Claude.

---

## 3. Les 3 classes d'outils

Chaque outil appartient à exactement une classe. La classe détermine son contrat Zero-Data.

| Classe | Nom | Comportement | Données réelles ? |
|---|---|---|---|
| **C1** | CODEGEN / PURE | Calcul ou génération de fichiers locaux à partir de specs abstraites. 100% déterministe, hors-ligne. | Jamais |
| **C2** | EMIT / INGEST | Produit la commande/artefact exact à exécuter côté client. Exécute en réel **si** une cible + identifiants sont configurés (env). Sinon : renvoie la commande + un résultat `dry_run`. Tout retour est assaini. | Seulement côté client ; le serveur ne reçoit que de l'assaini |
| **C3** | AUDIT / SECURITY | Analyse statique du code/artefacts produits + filtrage des logs. | Jamais (analyse nos propres artefacts) |

**Contrat C2 (gating d'action externe)** — helper partagé `targets.py::resolve_target()` :
- Si la cible (host SSH, registry, SFTP, SMTP, webhook Slack, clé API Calendly…) est configurée via variables d'environnement → exécution réelle.
- Sinon → `meta.executed = false`, `meta.dry_run = true`, `data.command` = commande exacte exécutable par l'humain. **Jamais de faux succès.**

---

## 4. Architecture & arborescence

```
fine-tuning-os/
├── pyproject.toml                # mcp, pydantic, httpx, jinja2, pyyaml, paramiko, markdown, weasyprint, cryptography
├── README.md
├── docs/superpowers/specs/2026-05-29-fine-tuning-os-design.md
├── src/fine_tuning_os/
│   ├── __init__.py
│   ├── server.py                 # FastMCP("fine-tuning-os"); enregistre les 64 outils (wrappers fins)
│   ├── models.py                 # DTO pydantic partagés + enveloppe de réponse
│   ├── envelope.py               # Result{success,data,error,meta} (cf. patterns.md)
│   ├── store.py                  # workspace projet, état JSON, journal d'événements
│   ├── sanitize.py               # filtres Zero-Data (PII, IP, blobs, quotes longues)
│   ├── render.py                 # Markdown -> PDF (weasyprint), SHA256, util fichiers
│   ├── crypto.py                 # AES-256-GCM (chiffrement livrable), génération/gestion de clé
│   ├── targets.py                # resolve_target(): gating C2 (SSH/HTTP/SFTP/SMTP/Slack)
│   ├── templates/                # gabarits Jinja2
│   │   ├── configs/              # unsloth.yaml.j2, axolotl.yaml.j2, custom.yaml.j2
│   │   ├── docker/               # Dockerfile.train.j2, Dockerfile.infer.j2, compose.yaml.j2
│   │   ├── train/               # train.py.j2, eval.py.j2, split.py.j2
│   │   ├── docs/                 # user_guide.md.j2, deployment_guide.md.j2, perf_report.md.j2
│   │   ├── legal/               # contract.md.j2, nda.md.j2, destruction_cert.md.j2, delivery_note.md.j2
│   │   └── business/            # invoice.md.j2, status_update.md.j2
│   └── tools/
│       ├── prep.py               # outils 1-5
│       ├── synthetic.py          # outils 6-10
│       ├── pipeline.py           # outils 11-17
│       ├── execution.py          # outils 18-25
│       ├── evaluation.py         # outils 26-32
│       ├── security.py           # outils 33-38
│       ├── packaging.py          # outils 39-46
│       ├── docs.py               # outils 47-54
│       ├── client.py             # outils 55-60
│       └── maintenance.py        # outils 61-64
└── tests/
    ├── conftest.py               # workspace temporaire, fixtures synthétiques
    ├── test_prep.py … test_maintenance.py   # un fichier par module
    └── test_zero_data.py         # garde-fou : aucun outil C1/C3 ne fait de réseau
```

**Enveloppe de réponse unique** (`envelope.py`), conforme à `patterns.md` :

```python
@dataclass(frozen=True)
class Result:
    success: bool
    data: dict | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)   # ex. {executed, dry_run, command, sha256, warnings}
```

Tous les outils renvoient `Result` sérialisé en JSON. `server.py` contient des wrappers fins : validation pydantic → appel fonction de module → `Result`.

---

## 5. Modèle de persistance

- **Workspace** : racine configurable `FTOS_WORKSPACE` (défaut `./ftos-workspace`).
- **Projet** : `FTOS_WORKSPACE/<project_id>/` contenant :
  - `project.json` — état (client, modèle de base, statut, schéma de données attendu, checkpoints connus, jalons).
  - `events.jsonl` — journal append-only horodaté (`log_project_event`).
  - `config/`, `data/synthetic/`, `src/`, `docker/`, `outputs/`, `reports/`, `deliverables/`, `docs/`.
- `store.py` expose des opérations immuables (lecture → nouvel état → écriture atomique). Pas de mutation en place (cf. coding-style.md).
- Aucun secret n'est écrit dans `project.json` ni dans les logs. Les secrets viennent uniquement des variables d'environnement.

---

## 6. Catalogue des 64 outils

Format : `nom_outil` **[classe]** — description. **In:** entrées clés. **Out:** sortie clé.

### Module `prep.py` — Préparation & Configuration (1-5)

1. `create_training_config` **[C1]** — Génère un fichier de config complet (Unsloth/Axolotl/custom) depuis des paramètres. **In:** base_model, framework, lora_rank, lr, batch_size, epochs, scheduler, max_seq_len, project_id. **Out:** chemin config + contenu rendu.
2. `cache_base_model` **[C2]** — Émet la commande `huggingface-cli download` + vérification de hash pour mise en cache hors-ligne. Exécute si `HF_HOME`/token configurés. **In:** repo_id, revision, dest. **Out:** command, dry_run|résultat, hash attendu.
3. `generate_requirements` **[C1]** — Génère `requirements.txt`/`environment.yml` versionné selon framework + tâche. **In:** framework, cuda, extras. **Out:** chemin + contenu.
4. `create_project_structure` **[C1]** — Crée l'arborescence projet (data/, src/, config/, tests/, outputs/). **In:** project_id, nom client. **Out:** liste des dossiers créés.
5. `load_project_template` **[C1]** — Charge un template projet prédéfini (ex. « LoRA Mistral v3 ») avec fichiers de base. **In:** template_name, project_id. **Out:** fichiers instanciés.

### Module `synthetic.py` — Données synthétiques (6-10)

6. `describe_expected_data_format` **[C1]** — Enregistre la structure attendue des données réelles (colonnes, types, format chat/instruct) **sans contenu réel**. **In:** schema (colonnes/types), task_type. **Out:** schéma normalisé persisté.
7. `generate_synthetic_dataset` **[C1]** — Crée 10-50 exemples synthétiques respectant le schéma, pour tester le pipeline. **In:** project_id, n, seed. **Out:** chemin JSONL synthétique.
8. `validate_data_schema` **[C1]** — Vérifie qu'un fichier respecte le schéma attendu **sans lire le contenu réel** (n'inspecte que clés/types/longueurs, pas les valeurs textuelles). **In:** file_path, schema. **Out:** rapport conformité.
9. `anonymize_dataset_preview` **[C1]** — Pseudonymise localement un échantillon fourni pour debug (jamais envoyé à l'IA en clair ; passe par `sanitize.py`). **In:** file_path. **Out:** chemin pseudonymisé + compte d'entités masquées.
10. `split_dataset_config` **[C1]** — Définit ratios train/val/test et génère le script de split (appliqué côté client). **In:** ratios, seed, stratify. **Out:** `split.py` rendu.

### Module `pipeline.py` — Construction & Test du pipeline (11-17)

11. `build_docker_image` **[C2]** — Génère `Dockerfile.train` + émet `docker build`. Exécute si Docker dispo. **In:** project_id, base_image, cache_models. **Out:** Dockerfile + command/résultat.
12. `test_docker_build` **[C2]** — Vérifie que l'image se construit et que les tests internes passent. **In:** image_tag. **Out:** statut build + sortie tests assainie.
13. `run_local_synthetic_train` **[C2]** — Génère `train.py` + émet un micro-entraînement (10 steps) sur dataset synthétique. Exécute en sous-processus si un Python local est configuré (`FTOS_LOCAL_PYTHON`). **In:** project_id, steps. **Out:** métriques (loss, temps/step, VRAM) ou command.
14. `get_local_metrics` **[C1]** — Parse les métriques du dernier run synthétique. **In:** project_id. **Out:** métriques structurées.
15. `dry_run_remote_config` **[C1]** — Simule l'exécution distante : vérifie variables d'env, points de montage, chemins. **In:** deployment spec. **Out:** rapport de pré-vol (manquants/ok).
16. `optimize_hyperparams` **[C1]** — Suggère des hyperparamètres améliorés selon les métriques du test local (heuristiques : lr/batch/grad_accum/rank). **In:** métriques locales. **Out:** config proposée + justification.
17. `generate_unit_tests` **[C1]** — Produit des tests unitaires pour les fonctions critiques du script d'entraînement. **In:** project_id, cibles. **Out:** fichiers de test rendus.

### Module `execution.py` — Exécution de l'entraînement (18-25)

18. `push_docker_to_registry` **[C2]** — Émet `docker push` vers registre privé/temporaire. Exécute si registry+creds configurés. **In:** image_tag, registry. **Out:** command/résultat + digest.
19. `generate_deployment_command` **[C1]** — Produit la commande exacte (`docker run …`/`docker compose up`) côté client. **In:** image, mounts, env, gpus. **Out:** commande + compose rendu.
20. `trigger_remote_training` **[C2]** — Lance l'entraînement distant (SSH bastion / API cloud / enclave) si autorisé. **In:** target, command. **Out:** job_id ou command (dry_run).
21. `stream_remote_logs` **[C2]** — Récupère les logs distants en filtrant toute donnée sensible (via `sanitize.py`). **In:** job_id/target, n_lines. **Out:** logs assainis.
22. `monitor_training_metrics` **[C2]** — Agrège loss/lr/GPU dans le temps depuis les logs assainis. **In:** job_id/source. **Out:** séries temporelles + courbes (données pour tracé).
23. `detect_anomalies` **[C1]** — Analyse les logs (déjà assainis) : divergence, NaN, plateau, signe de fuite de données. **In:** logs/métriques. **Out:** liste d'alertes + sévérité.
24. `pause_resume_training` **[C2]** — Met en pause/reprend un entraînement distant si l'infra le supporte. **In:** job_id, action. **Out:** statut ou command.
25. `early_stopping_check` **[C1]** — Évalue les critères d'arrêt précoce et notifie/recommande l'arrêt. **In:** métriques, patience, min_delta. **Out:** décision (continue/stop) + raison.

### Module `evaluation.py` — Évaluation & Validation (26-32)

26. `download_checkpoint_metadata` **[C2]** — Récupère les métadonnées du checkpoint (step, loss…) sans télécharger les poids. **In:** target, checkpoint. **Out:** métadonnées ou command.
27. `evaluate_on_synthetic` **[C1]** — Exécute le script d'éval sur le dataset synthétique pour vérifier le fonctionnement. **In:** project_id. **Out:** métriques synthétiques.
28. `evaluate_on_validation_set` **[C2]** — Lance l'éval sur le set de validation client (exécuté côté client). **In:** target, eval_spec. **Out:** métriques assainies ou command.
29. `compute_metrics` **[C1]** — Calcule perplexité, BLEU, ROUGE, accuracy, F1 selon la tâche, depuis des prédictions/références fournies (non sensibles ou assainies). **In:** preds, refs, task. **Out:** métriques.
30. `generate_predictions_sample` **[C1]** — Génère le harnais pour produire quelques prédictions sur prompts synthétiques non sensibles (inspection humaine). **In:** prompts synthétiques. **Out:** script + (si local) sorties.
31. `compare_to_baseline` **[C1]** — Compare le modèle fine-tuné au modèle de base sur les mêmes métriques. **In:** métriques_ft, métriques_base. **Out:** delta + tableau comparatif.
32. `bias_fairness_scan` **[C1]** — Scan rapide de biais sur prompts types. **In:** prompts de test, catégories. **Out:** rapport de biais.

### Module `security.py` — Sécurité & Audit (33-38)

33. `audit_code_no_network` **[C3]** — Analyse statique (AST) du code d'entraînement : aucun appel réseau hors exceptions autorisées. **In:** chemin code, allowlist. **Out:** findings + verdict.
34. `audit_dockerfile_security` **[C3]** — Vérifie bonnes pratiques (user non-root, pas de secrets, pin de versions, pas de `curl|sh`). **In:** Dockerfile. **Out:** findings + sévérité.
35. `scan_data_leakage_risk` **[C3]** — Analyse les logs/artefacts pour détecter toute fuite de texte réel (heuristiques `sanitize.py`). **In:** chemin logs. **Out:** risques détectés.
36. `verify_model_license` **[C3]** — Vérifie la licence du modèle de base (registre local de licences) pour conformité usage commercial. **In:** repo_id. **Out:** licence + compatibilité commerciale.
37. `generate_security_report` **[C1]** — Agrège tous les contrôles d'audit en un rapport Markdown/PDF livrable. **In:** project_id. **Out:** rapport (md+pdf) + SHA256.
38. `sanitize_logs_for_claude` **[C3]** — Filtre un flux de logs pour retirer toute donnée sensible avant transmission à Claude. **In:** texte/chemin. **Out:** texte assaini + compte de masquages.

### Module `packaging.py` — Packaging & Livraison (39-46)

39. `merge_lora_weights` **[C2]** — Émet la commande de fusion adaptateur LoRA + modèle de base (peut router vers unsloth-server / sous-processus local). **In:** base, adapter, out. **Out:** command/résultat.
40. `quantize_model` **[C2]** — Émet la quantization GGUF/GPTQ/AWQ selon besoin. **In:** model_path, format, bits. **Out:** command/résultat.
41. `build_inference_container` **[C2]** — Génère `Dockerfile.infer` (serveur API compatible OpenAI) + émet build. **In:** model_path, engine. **Out:** Dockerfile + command.
42. `generate_inference_config` **[C1]** — Produit la config du serveur d'inférence (port, clé API, limites, contexte). **In:** params. **Out:** fichier config.
43. `test_inference_api` **[C2]** — Envoie des requêtes de test au conteneur d'inférence et vérifie les réponses. Exécute si endpoint configuré. **In:** base_url, prompts. **Out:** résultats ou command curl.
44. `encrypt_deliverable` **[C1]** — Chiffre le livrable (modèle/conteneur/doc) en AES-256-GCM avec clé générée. **In:** chemin(s). **Out:** archive chiffrée + clé (affichée une fois) + SHA256.
45. `upload_deliverable` **[C2]** — Dépose le livrable chiffré sur le canal convenu (SFTP/cloud client). **In:** chemin, destination. **Out:** résultat ou command.
46. `generate_delivery_note` **[C1]** — Crée un bon de livraison : liste fichiers, SHA256, procédure de déchiffrement. **In:** project_id, fichiers. **Out:** note (md+pdf).

### Module `docs.py` — Documentation & Contrats (47-54)

47. `generate_contract` **[C1]** — Remplit le template de contrat (prestation, clauses sécurité, prix) avec les données projet. **In:** project_id, montant, clauses. **Out:** contrat (md).
48. `generate_nda` **[C1]** — Génère un NDA personnalisé. **In:** parties, durée, juridiction. **Out:** NDA (md).
49. `generate_performance_report` **[C1]** — Rapport complet : métriques, courbes, comparaison baseline, captures. **In:** project_id, métriques. **Out:** rapport (md+pdf).
50. `generate_user_guide` **[C1]** — Guide d'utilisation du modèle (endpoints API, exemples de code, paramètres). **In:** inference config. **Out:** guide (md).
51. `generate_deployment_guide` **[C1]** — Procédure de déploiement pour l'équipe IT du client. **In:** déploiement spec. **Out:** guide (md).
52. `generate_destruction_certificate` **[C1]** — Certificat de destruction des données (suppression irréversible). **In:** project_id, date, méthode. **Out:** certificat (md+pdf) + SHA256.
53. `export_document_pdf` **[C1]** — Convertit un document Markdown généré en PDF. **In:** chemin md. **Out:** chemin pdf + SHA256.
54. `sign_document` **[C2]** — Applique une signature électronique (clé locale détachée par défaut ; API e-sign si configurée). **In:** chemin doc. **Out:** signature/horodatage ou command.

### Module `client.py` — Relation client & Suivi (55-60)

55. `onboard_client` **[C1]** — Collecte les infos client (entreprise, contacts, besoins) via formulaire structuré ; crée le projet. **In:** champs client. **Out:** project_id + état initial.
56. `send_status_update` **[C2]** — Envoie l'avancement par email/Slack (rendu Markdown). Exécute si SMTP/webhook configuré, sinon renvoie le message prêt à envoyer. **In:** project_id, contenu. **Out:** message + résultat/dry_run.
57. `schedule_meeting` **[C2]** — Propose des créneaux (API Calendly) pour validations intermédiaires. **In:** durée, fenêtre. **Out:** liens/créneaux ou command.
58. `log_project_event` **[C1]** — Enregistre un événement horodaté dans `events.jsonl`. **In:** project_id, type, payload. **Out:** event_id.
59. `request_client_approval` **[C1]** — Crée une demande de validation formelle (ex. « Approuvez-vous les métriques ? ») persistée, statut en attente. **In:** project_id, question, artefacts. **Out:** approval_id + statut.
60. `generate_invoice` **[C1]** — Crée une facture (md+pdf) : détails prestation, conditions de paiement. **In:** project_id, lignes, montants. **Out:** facture + SHA256.

### Module `maintenance.py` — Maintenance & Mise à jour (61-64)

61. `check_model_rot` **[C1]** — Compare des métriques d'éval dans le temps pour détecter une dérive. **In:** historique métriques. **Out:** verdict dérive + ampleur.
62. `suggest_retraining` **[C1]** — Analyse des logs de prod (si fournis, assainis) pour recommander un nouveau fine-tuning. **In:** signaux/métriques. **Out:** recommandation + justification.
63. `update_base_model` **[C1]** — Met à jour le pipeline pour une version plus récente du modèle de base (config + requirements). **In:** project_id, nouveau repo/rev. **Out:** diff config.
64. `mcp_self_update` **[C2]** — Met à jour le serveur MCP depuis un dépôt Git sécurisé. Exécute si remote configuré. **In:** ref. **Out:** command/résultat.

---

## 7. Définition de « fonctionnel à 100% »

- **Outils C1/C3** (majorité) : pleinement réels, déterministes, hors-ligne. Testés avec entrées synthétiques. Aucune dépendance externe à l'exécution.
- **Outils C2** : pleinement réels **dans leur contrat** — ils font un vrai travail (validation des entrées, génération de la commande/artefact exact, journalisation) et exécutent l'action live **quand la cible/les identifiants sont configurés** via variables d'environnement. À défaut, ils renvoient `dry_run=true` + la commande exacte. **Jamais de faux succès.**

Ce contrat est explicite dans chaque réponse via `meta.executed` / `meta.dry_run` / `meta.command`.

---

## 8. Sécurité & secrets

- Secrets **uniquement** via variables d'environnement (cf. security.md). Jamais écrits sur disque ni dans les logs.
- Variables d'env reconnues (toutes optionnelles ; absence ⇒ mode dry_run du C2 concerné) : `FTOS_WORKSPACE`, `FTOS_LOCAL_PYTHON`, `HF_TOKEN`, `FTOS_SSH_HOST`/`FTOS_SSH_KEY`, `FTOS_REGISTRY`/`FTOS_REGISTRY_TOKEN`, `FTOS_SFTP_*`, `FTOS_SMTP_*`, `FTOS_SLACK_WEBHOOK`, `FTOS_CALENDLY_TOKEN`, `FTOS_GIT_REMOTE`.
- `sanitize.py` masque : emails, IP, URLs avec credentials, blocs base64 longs, chaînes citées > N caractères, motifs configurables. Utilisé par tout C2 ingérant des logs + tous les C3.
- `audit_code_no_network` (AST) et `audit_dockerfile_security` appliquent les contrôles avant tout packaging.
- Chiffrement livrable : AES-256-GCM, clé aléatoire 256 bits, intégrité SHA256.

---

## 9. Dépendances

`mcp>=1.2.0`, `pydantic>=2.6`, `httpx>=0.27`, `jinja2>=3.1`, `pyyaml>=6`, `paramiko>=3` (SSH), `markdown>=3.6` + `weasyprint>=62` (PDF), `cryptography>=42`. Dev : `pytest`, `pytest-cov`, `black`, `ruff`. **Aucune lib ML lourde** (`torch`/`unsloth`/`transformers`) dans le serveur.

---

## 10. Tests

- `pytest`, déterministes, **hors-ligne**, ≥80% de couverture (cf. testing.md).
- Un fichier de test par module ; chaque outil testé sur entrées synthétiques (chemin nominal + ≥1 cas d'erreur).
- `test_zero_data.py` : garde-fou prouvant qu'aucun outil C1/C3 n'effectue d'I/O réseau (monkeypatch socket → lève) et que les C2 sans config renvoient `dry_run=true` sans réseau.
- Tests de `sanitize.py` : jeux d'entrées contenant des motifs sensibles ⇒ vérifier masquage complet.

---

## 11. Critères d'acceptation

1. Les 64 outils sont enregistrés dans `server.py` et listés par le client MCP.
2. Chaque outil renvoie l'enveloppe `Result` ; chaque C2 expose `meta.executed`/`meta.dry_run`/`meta.command`.
3. Le serveur démarre en stdio sans aucune variable d'env (tous les C2 basculent proprement en dry_run).
4. `pytest` passe, couverture ≥80%, `test_zero_data.py` vert.
5. `black`/`ruff` propres ; annotations de type sur toutes les signatures.
6. Un parcours bout-en-bout sur projet synthétique fonctionne : `onboard_client` → `describe_expected_data_format` → `generate_synthetic_dataset` → `create_training_config` → `run_local_synthetic_train` (ou émission) → `compute_metrics` → `generate_security_report` → `encrypt_deliverable` → `generate_delivery_note`.
7. Le **skill compagnon** existe (cf. §13) : `SKILL.md` valide (frontmatter `name`+`description`), 10 références de phase + 6 références transverses, mappe chaque phase aux outils MCP, et passe `skill-create`/`skill-health` (ou équivalent de validation).
8. **Bundle livrable de référence (preuve de vente)** : un projet de démonstration **100% synthétique** exécuté bout-en-bout produit un dossier montrable à un prospect — rapport de sécurité, rapport de performance (avec comparaison baseline), bon de livraison + SHA256, livrable chiffré (+ procédure de déchiffrement), contrat/NDA, certificat de destruction, guides utilisateur/déploiement. Généré sous `ftos-workspace/demo-project/deliverables/` (non commité, cf. `.gitignore`) et reproductible par un script/recette documentée.
9. **Référentiels synchronisés** : `references/sota-may-2026.md` ≡ §14, `references/pricing-packaging.md` ≡ §15, `references/legal-compliance.md` ≡ §17 (mêmes faits, daté mai 2026 avec note de péremption). La frontière d'exécution §16 est reflétée dans `SKILL.md` et `references/04-execution.md`/`07-packaging-delivery.md`.

---

## 12. Découpage de l'implémentation (indicatif, pour le plan)

Ordre recommandé (chaque lot livrable + testé) :
1. Socle : `pyproject`, `envelope`, `models`, `store`, `sanitize`, `render`, `crypto`, `targets`, `server` (bootstrap), `conftest`.
2. `prep` + `synthetic` (C1, fondations).
3. `pipeline` + `execution` (C2, contrat émetteur).
4. `evaluation` + `security`.
5. `packaging` + `docs` (templates Jinja2 + PDF).
6. `client` + `maintenance`.
7. `test_zero_data` + passe couverture + README.
8. **Skill compagnon** (cf. §13) : `SKILL.md` + 16 références + validation `skill-health`. Les références `sota-may-2026`/`pricing-packaging`/`legal-compliance` rendent §14/§15/§17.
9. **Bundle livrable de référence** (cf. critère #8) : recette + projet démo synthétique générant le dossier de vente complet (PDF/MD + archive chiffrée + SHA256), reproductible.

---

## 13. Compagnon : skill métier (operator playbook)

Le MCP donne les **outils** ; le skill donne le **savoir-faire**. But : conférer à l'opérateur (et à Claude pilotant le MCP) les instructions parfaites du métier, sans angle mort — dense, exhaustif, multidimensionnel, grade élite pro SOTA mai 2026.

### 13.1 Emplacement & forme

```
fine-tuning-os/skills/fine-tuning-os/
├── SKILL.md                       # frontmatter + playbook noyau (progressive disclosure, ≤ ~500 lignes)
└── references/
    ├── 01-preparation.md          # phase 1 ↔ outils 1-5
    ├── 02-synthetic-data.md       # phase 2 ↔ outils 6-10
    ├── 03-pipeline.md             # phase 3 ↔ outils 11-17
    ├── 04-execution.md            # phase 4 ↔ outils 18-25
    ├── 05-evaluation.md           # phase 5 ↔ outils 26-32
    ├── 06-security-audit.md       # phase 6 ↔ outils 33-38
    ├── 07-packaging-delivery.md   # phase 7 ↔ outils 39-46
    ├── 08-docs-contracts.md       # phase 8 ↔ outils 47-54
    ├── 09-client-relations.md     # phase 9 ↔ outils 55-60
    ├── 10-maintenance.md          # phase 10 ↔ outils 61-64
    ├── zero-data-invariants.md    # règles d'or Zero-Data, frontières, anti-fuite
    ├── legal-compliance.md        # NDA, clauses contrat, RGPD/GDPR, cert. destruction, licences modèles
    ├── sota-may-2026.md           # modèles, QLoRA/LoRA, formats quant, harnais d'éval, infra
    ├── pricing-packaging.md       # structure d'offre, jalons, facturation, SLA
    ├── checklists.md              # go/no-go par phase (gates)
    └── troubleshooting.md         # divergence, NaN, OOM, fuite, échec build, recours
```

- `SKILL.md` frontmatter : `name: fine-tuning-os`, `description:` déclenchant sur « prestation/livraison de fine-tuning LLM en mode Zero-Data via le MCP fine-tuning-os ». Le corps : vue d'ensemble, **carte des 10 phases ↔ 64 outils**, invariants Zero-Data, arbre de décision (quel outil quand), et renvois vers les références (chargées à la demande).
- Progressive disclosure : SKILL.md reste court et navigable ; la profondeur vit dans `references/`.

### 13.2 Couverture obligatoire (toutes dimensions)

1. **Process bout-en-bout** : les 10 phases dans l'ordre, entrée/sortie de chaque phase, gate go/no-go avant de passer à la suivante, et l'outil MCP exact à appeler à chaque étape.
2. **Invariants Zero-Data** : ce que l'opérateur ne doit jamais faire (voir données réelles, sortir des poids en clair de l'enclave, logguer du brut), comment chaque classe d'outil (C1/C2/C3) préserve la frontière, réflexe `sanitize` systématique.
3. **Sécurité & audit** : checklist pré-livraison, contenu du rapport de sécurité, réponse incident fuite, durcissement Docker, gestion des secrets par variables d'env.
4. **Juridique & conformité (droit français, cf. §17)** : NDA et clauses contractuelles ancrées dans le **Code civil** (art. 1101 s. : formation/obligations ; art. 1231 s. : responsabilité) et le **Code de la propriété intellectuelle** (titularité du modèle/adaptateur, cession de droits, licence) ; **secret des affaires** (art. L151-1 s. **Code de commerce**) ; **RGPD** (Règlement UE 2016/679) + **Loi Informatique et Libertés** (Loi n°78-17 mod.) : minimisation (art. 5), base légale (art. 6), sous-traitance (art. 28 → contrat de sous-traitance/DPA obligatoire), registre des traitements (art. 30), durée/effacement (art. 17) matérialisé par le **certificat de destruction irréversible**, lignes directrices **CNIL** sur l'IA ; **vérification de licence** du modèle de base (usage commercial, redistribution, attribution — cf. §14.1). Les gabarits citent la base légale ; pas de conseil juridique externe requis (la donnée est dans la littérature juridique française).
5. **Technique SOTA mai 2026** : sélection modèle de base, LoRA vs QLoRA vs full-FT, rank/alpha/dropout, schedulers, packing, longueur de contexte, formats de quantization (GGUF/GPTQ/AWQ) et quand les choisir, harnais d'évaluation, détection de régression/dérive. Daté mai 2026 et signalé comme à réévaluer.
6. **Relation client** : protocole de communication (cadence des updates, demandes d'approbation tracées), onboarding, jalons, gestion des attentes, escalade.
7. **Packaging & livraison** : conteneur d'inférence compatible OpenAI, chiffrement AES-256, bon de livraison + SHA256, procédure de déchiffrement, guides utilisateur/déploiement.
8. **Pricing & offre** : structure de la prestation, jalons facturables corrélés aux validations, SLA, maintenance/retraining.
9. **Anti-oubli** : checklists exhaustives par phase (`checklists.md`) — chaque item mappé à l'outil qui le réalise, pour qu'aucune étape (audit, cert. destruction, licence, guide) ne soit omise.
10. **Dépannage** : table symptôme → cause → outil/action de remédiation (divergence, NaN, OOM, plateau, fuite détectée, build Docker KO, inférence KO).

### 13.3 Barre de qualité

- Chaque référence : actionnable (pas de remplissage), avec checklists, exemples de commandes/outils, et renvois croisés vers les outils MCP par nom.
- Cohérence stricte avec le catalogue §6 : tout outil cité existe ; toute phase mappe ses outils.
- Validation par `everything-claude-code:skill-create` / `skill-health` (ou équivalent) : frontmatter correct, description déclenchante, pas de lien mort.
- Daté « SOTA mai 2026 » là où le contenu est sensible au temps, avec note de péremption.

---

## 14. Référentiel technique SOTA — mai 2026 (source de vérité de `sota-may-2026.md`)

> **Péremption** : paysage modèles/outils évoluant vite. Contenu **figé au 2026-05-29**. À réévaluer à chaque trimestre ou nouveau projet. Le skill `references/sota-may-2026.md` est le rendu opérationnel de cette section ; les deux restent synchronisés.

### 14.1 Modèles de base — sélection & licence

Ordre de préférence pour une prestation **Zero-Data, usage commercial client** (licence permissive prioritaire) :

| Modèle | Licence | Profil | Quand le choisir |
|---|---|---|---|
| **Qwen3.5 / 3.6** (dense 27-35B, MoE 235B-A22B) | Apache-2.0 | Écosystème fine-tuning le plus mûr, multilingue, 1M ctx | **Défaut** prestation commerciale ; meilleur rapport maturité/risque licence |
| **Mistral Small 4** / Medium 3.5 | Apache-2.0 (Small) | FT mûr, tailles déployables | Cible CPU/GPU modeste, UE-friendly |
| **DeepSeek V4 / V4 Pro** | MIT | Roi agentic/coding, meilleur perf/coût self-host | Tâches code/agent, gros volume self-host |
| **GLM-5 / 5.1** | MIT | Licence la plus propre | Quand le client exige MIT strict |
| **Gemma 4 (31B)** | Gemma (restrictions) | Bon généraliste | Vérifier compat licence avant commercial |
| **Llama 4 Scout** | Llama Community (seuils MAU) | Ultra-long contexte (10M tok) | Besoin contexte extrême ; **auditer la licence** (clauses MAU/usage) |
| **Phi-4-mini** | MIT | Petit, edge | Contrainte forte de taille/latence |

Règle : `verify_model_license` (outil 36) **avant** tout engagement. Permissif commercial sûr = **Apache-2.0 / MIT**. Llama 4 et Gemma = clauses à lire (seuils d'usage, attribution, restrictions). Frontière open « top index » mai 2026 : Kimi K2.6 (#1 open) — mais privilégier maturité FT + licence plutôt que score brut.

### 14.2 Méthode de fine-tuning — arbre de décision

- **LoRA** = défaut production. Reste le bon choix pour la majorité des cas (simple, robuste, zéro surcoût d'inférence).
- **QLoRA** (NF4 4-bit + LoRA) = défaut **sous contrainte VRAM**. 33B sur 24 Go ; qualité ≈ full-FT. Meilleur équilibre accuracy/efficacité.
- **DoRA** (décomposition direction/magnitude, ICML 2024) = quand LoRA sature à rank donné ; surpasse LoRA à rank égal, **pas de surcoût d'inférence**. Bon défaut « qualité+ ».
- **GaLore** (projection gradient low-rank) = VRAM très serrée tout en cherchant qualité ; préférer **8-bit** (pas NF4 4-bit) ; intégration Axolotl **expérimentale** début 2026 → privilégier `galore_torch` + `SFTTrainer` TRL.
- **PiSSA / VeRA** = options avancées (init SVD / vecteurs partagés) ; à n'utiliser que sur besoin mesuré.
- **Éviter** LoHA/LoKR (pertes plus fortes) sauf cas spécifique.
- **Full fine-tuning** : seulement si LoRA/DoRA insuffisants ET budget GPU le permet (rare en prestation).

Hyperparamètres de départ (à régler via `optimize_hyperparams`, outil 16) : rank 16-64, alpha = 2×rank, dropout 0-0.1, lr 1e-4→2e-4 (LoRA/QLoRA), cosine + warmup 3-5%, packing activé, max_seq_len selon tâche.

### 14.3 Quantization — choix par cible de déploiement

| Cible | Format | Réglage |
|---|---|---|
| Universel (CPU/Apple/AMD/NVIDIA), Ollama/LM Studio | **GGUF** | `Q4_K_M` défaut ; `Q5_K_M` si qualité prioritaire |
| Service multi-utilisateurs vLLM/SGLang | **AWQ** | Meilleure qualité que GPTQ à bits égaux (~42% mém., ~1.2% perte) |
| Débit max GPU NVIDIA (mono-usage) | **EXL2** | NVIDIA-only, fastest tok/s |
| Repli vLLM si AWQ indispo | **GPTQ** | + noyaux **Marlin** |
| NVIDIA récent, précision agressive | **FP8 / NVFP4** | émergent ; valider qualité |

Émetteur via `quantize_model` (outil 40). Export pour serving = **checkpoint mergé 16-bit** (base+LoRA) consommé par le moteur.

### 14.4 Évaluation — harnais & benchmarks

- **Standard industrie** : EleutherAI **lm-evaluation-harness** (60+ benchmarks). **LightEval** (HF) pour la largeur (Big-Bench + HELM).
- **Benchmarks clés** : **MMLU-Pro** (10 choix, raisonnement, plus discriminant que MMLU), MMLU, GSM8K/MATH, GPQA, IFEval (suivi d'instructions), TruthfulQA, HellaSwag, ARC, WinoGrande, BBH.
- **Tâche-spécifique** : perplexité, BLEU/ROUGE (génération), accuracy/F1 (classif) via `compute_metrics` (outil 29) ; toujours `compare_to_baseline` (31) modèle base vs fine-tuné sur le **même** harnais.
- Éval sur données réelles = **côté client** (`evaluate_on_validation_set`, 28) → ne remontent que des métriques assainies.

### 14.5 Stack d'exécution & serving (mai 2026)

- **Fine-tuning** : Unsloth (noyaux optimisés LoRA/QLoRA) — routé hors-serveur (cf. §16).
- **Quantization** : AutoAWQ / llama.cpp (GGUF) / ExLlamaV2 (EXL2).
- **Serving** : **SGLang** (prefix-caching, fort sur multi-tour/agent ; ~29% débit sur petits modèles, ~3.1× sur DeepSeek-V3) **ou vLLM** (généraliste solide) ; TensorRT-LLM pour perf NVIDIA max. Conteneur d'inférence **API compatible OpenAI** (`build_inference_container`, 41).
- **Déploiement** : images Docker + Helm/K8s, Ray Serve / BentoML / Triton ; health checks + scaling horizontal.

---

## 15. Pricing & offre — chiffres marché 2026 (source de vérité de `pricing-packaging.md`)

> Fourchettes indicatives **EUR, mai 2026**, à ajuster au marché/positionnement. Ancrées sur le coût GPU réel et la concurrence des FT API managées (Together, Fireworks, OpenAI FT). Le différenciateur **Zero-Data + livraison en enclave** justifie un premium vs API managée (qui exige d'envoyer la donnée).

### 15.1 Coûts sous-jacents (référence)

- **GPU cloud** (mai 2026, ordre de grandeur/h) : A100 80G ~1-2 €/h, H100 ~2-4 €/h, H200/B200 supérieurs. Un fine-tuning LoRA 7-13B = quelques heures GPU ; 70B QLoRA = dizaines d'heures.
- **FT API managées** (repère concurrence) : facturées au token d'entraînement + hébergement ; imposent l'envoi de la donnée hors enclave → **incompatibles Zero-Data** (notre angle de vente).

### 15.2 Structure d'offre (jalons facturables, corrélés aux validations)

| Phase facturable | Jalon de validation | Fourchette indicative |
|---|---|---|
| **Cadrage & faisabilité** (onboarding, schéma données, choix modèle, audit licence) | Spec validée par client | 2 000 – 5 000 € |
| **Pipeline & preuve synthétique** (config, Docker, micro-train synthétique, tests, audit sécu) | Démo pipeline + rapport sécu | 4 000 – 10 000 € |
| **Entraînement & éval** (exécution enclave, métriques, comparaison baseline) | Approbation des métriques (`request_client_approval`) | 6 000 – 20 000 € (selon taille modèle/itérations) |
| **Packaging & livraison** (merge, quant, conteneur inférence, chiffrement, guides) | Bon de livraison + SHA256 acceptés | 3 000 – 8 000 € |
| **Maintenance / retraining** (option, récurrent) | SLA dérive/retraining | 500 – 3 000 €/mois ou forfait/itération |

- **Prestation type (one-shot, 7-13B, LoRA/QLoRA)** : ~15 000 – 40 000 € selon complexité.
- **Premium Zero-Data** : +10-25% justifié (jamais d'exfiltration de données, certificat de destruction, audit no-network).
- **Modèle commercial** : forfait par phase (recommandé) > régie ; acompte 30% au cadrage, solde aux jalons.

### 15.3 SLA & maintenance

- Définir : fenêtre de support, délai de réponse incident, seuil de dérive déclenchant un retraining (`check_model_rot` 61, `suggest_retraining` 62), périmètre des mises à jour modèle de base (`update_base_model` 63).

---

## 16. Frontière d'exécution & dépendance `unsloth-server` (récit de vente explicite)

**Où s'entraîne réellement le modèle ?** Fine-Tuning OS est l'**usine de pilotage** (génère configs/scripts/Docker/commandes, audite, package, documente — classes C1/C3) ; le **gros œuvre GPU** (train SFT/DPO, merge LoRA, quantize) s'exécute :

1. **Côté client / enclave** (cas Zero-Data nominal) : les outils C2 émettent la commande/conteneur exact ; l'entraînement tourne sur l'infra cliente ; seules des métriques/logs **assainis** reviennent.
2. **Sur l'infra de l'opérateur via le MCP `unsloth-server`** (~200 outils ML live : `train_sft`, `train_dpo`, `merge_lora`, `save_gguf`, `quantize_awq`…) **uniquement** sur données **synthétiques** (preuve de pipeline) ou si le client autorise explicitement l'entraînement sur l'infra opérateur.

Conséquences :

- Fine-Tuning OS **n'embarque pas** torch/unsloth (serveur léger, installable, frontière Zero-Data préservée). Les outils C2 lourds (`merge_lora_weights` 39, `quantize_model` 40, `run_local_synthetic_train` 13) **routent** vers `unsloth-server` ou un sous-process Python local (`FTOS_LOCAL_PYTHON`), sinon `dry_run` + commande.
- **Argument commercial** : pas de trou entre « 64 outils » et « où s'entraîne le modèle » — la prestation = Fine-Tuning OS (orchestration/sécurité/livraison) **+** un moteur d'exécution (enclave client *ou* unsloth-server opérateur). Le client choisit le lieu d'exécution ; la frontière Zero-Data est tenue dans les deux cas.

---

## 17. Référentiel juridique — droit français (source de vérité de `legal-compliance.md`)

> Base légale citée dans les gabarits (`contract.md.j2`, `nda.md.j2`, `destruction_cert.md.j2`). Pas de conseil juridique externe : ces références figurent dans la littérature juridique française et suffisent à instruire les gabarits. **Avertissement** : gabarits = base sérieuse à adapter au cas ; ils citent leur fondement, ils ne remplacent pas une relecture par le client.

- **Contrat de prestation** : Code civil art. 1101 s. (contrat, consentement, objet), art. 1112 s. (négociation/bonne foi), art. 1231 s. (responsabilité contractuelle, mise en demeure, dommages-intérêts), clause limitative de responsabilité (plafond), réversibilité/livrables.
- **Propriété & PI** : Code de la propriété intellectuelle — titularité de l'adaptateur/modèle entraîné, cession ou licence des droits au client, sort des données d'entraînement (restent au client), absence de réutilisation par l'opérateur.
- **Confidentialité** : NDA bilatéral ; **secret des affaires** art. L151-1 s. Code de commerce (définition, mesures de protection raisonnables, sanctions).
- **Données personnelles** : **RGPD** (Règl. UE 2016/679) + **Loi n°78-17** (Informatique et Libertés mod.). Points obligatoires : licéité/base légale (art. 6), minimisation (art. 5-1-c), **contrat de sous-traitance / DPA** (art. 28) si l'opérateur traite des données pour le client, registre (art. 30), durée de conservation + **droit à l'effacement** (art. 17) → **certificat de destruction irréversible** (`generate_destruction_certificate`, 52), sécurité du traitement (art. 32 — chiffrement AES-256, audit no-network), notification de violation (art. 33-34). Lignes directrices **CNIL** sur l'IA et la base de données d'apprentissage.
- **Réflexe Zero-Data** : l'architecture (données restent en enclave, jamais vues par l'opérateur/Claude) **sert directement** la minimisation et la sécurité RGPD → argument de conformité, pas seulement technique.
