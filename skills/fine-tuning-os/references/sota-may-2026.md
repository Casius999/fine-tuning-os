# SOTA Technique — Mai 2026

> Source de vérité ≡ §14 du spec (2026-05-29)
> **Péremption : paysage modèles/outils évoluant vite. Contenu figé au 2026-05-29.
> À réévaluer à chaque trimestre ou nouveau projet.**
> Back: [SKILL.md](../SKILL.md)

---

## 1. Sélection du modèle de base

Ordre de préférence pour une prestation **Zero-Data, usage commercial client**
(licence permissive prioritaire). Toujours exécuter `verify_model_license` (36)
avant tout engagement.

| Modèle | Licence | Profil | Quand choisir |
|--------|---------|--------|---------------|
| **Qwen3.5 / 3.6** (dense 7-35B, MoE 235B-A22B) | Apache-2.0 | Écosystème FT le plus mûr, multilingue, 1M ctx | **Défaut** — meilleur rapport maturité/risque licence |
| **Mistral Small 4** / Medium 3.5 | Apache-2.0 (Small) | FT mûr, tailles déployables, UE-friendly | GPU modeste, déploiement UE |
| **DeepSeek V4 / V4 Pro** | MIT | Roi agentic/coding, perf/coût self-host | Tâches code/agent, gros volume |
| **GLM-5 / 5.1** | MIT | Licence la plus propre | Quand le client exige MIT strict |
| **Gemma 4 (31B)** | Gemma (restrictions) | Bon généraliste | Vérifier compat commerciale avant |
| **Llama 4 Scout** | Llama Community (seuils MAU) | Ultra-long contexte (10M tok) | Besoin extrême de contexte ; **auditer licence** (clauses MAU) |
| **Phi-4-mini** | MIT | Edge/contrainte taille | Contrainte forte latence/taille |

**Règle :** Apache-2.0 / MIT = permissif commercial sûr. Llama 4 + Gemma = lire les clauses.
Frontière open « top index » mai 2026 : Kimi K2.6 (#1 open) — mais privilégier maturité FT + licence vs score brut.

---

## 2. Méthode de fine-tuning — arbre de décision

```
Contrainte VRAM disponible ?
  ├─ < 24 Go → QLoRA (NF4 4-bit + LoRA)
  │              → rank 32-64, alpha = 2×rank, lr 1e-4
  ├─ 24-80 Go → LoRA (défaut production)
  │              → rank 16-32, alpha = 2×rank, lr 2e-4
  └─ > 80 Go  → LoRA ou DoRA (si qualité prioritaire à rank donné)

LoRA sature à rank élevé ?
  └─ OUI → DoRA (direction/magnitude, ICML 2024)
           → surpasse LoRA à rank égal, pas de surcoût inférence
           → bon "qualité+" par défaut

VRAM très serrée + qualité maximale ?
  └─ GaLore (projection gradient low-rank)
     → utiliser 8-bit (pas NF4), intégration Axolotl expérimentale début 2026
     → préférer galore_torch + SFTTrainer TRL

Options avancées (besoin mesuré uniquement) :
  → PiSSA (init SVD), VeRA (vecteurs partagés)

À éviter sauf cas spécifique :
  → LoHA / LoKR (pertes plus fortes)

Full fine-tuning : seulement si LoRA/DoRA insuffisants ET budget GPU le permet (rare)
```

### Hyperparamètres de départ

Affiner avec `optimize_hyperparams` (outil 16) après micro-train.

| Paramètre | LoRA | QLoRA | DoRA |
|-----------|------|-------|------|
| Rank | 16-32 | 32-64 | 16-32 |
| Alpha | 2×rank | 2×rank | 2×rank |
| Dropout | 0.0-0.05 | 0.0 | 0.0 |
| LR | 2e-4 | 1e-4 | 2e-4 |
| Batch size | 2 | 2 | 2 |
| Grad accum | 4-8 | 8-16 | 4-8 |
| Scheduler | cosine | cosine | cosine |
| Warmup | 3-5% | 3-5% | 3-5% |
| Packing | Oui | Oui | Oui |

---

## 3. Quantization — choix par cible de déploiement

Émis via `quantize_model` (40). L'entrée du moteur de quantization = checkpoint
**mergé 16-bit** (base + adaptateur LoRA fusionné via `merge_lora_weights`, 39).

| Cible | Format | Réglage | Moteur |
|-------|--------|---------|--------|
| Universel : CPU, Apple Silicon, AMD, Ollama, LM Studio | **GGUF** | Q4_K_M (défaut) ; Q5_K_M si qualité prioritaire | llama.cpp |
| Service multi-users vLLM/SGLang | **AWQ** | Meilleure qualité que GPTQ à bits égaux (~42% mém., ~1.2% perte) | AutoAWQ |
| Débit max GPU NVIDIA mono-usage | **EXL2** | NVIDIA-only, fastest tok/s | ExLlamaV2 |
| Repli vLLM si AWQ indispo | **GPTQ + Marlin** | Noyaux Marlin pour perf | AutoGPTQ |
| NVIDIA récent (H100/H200), précision aggressive | **FP8 / NVFP4** | Émergent — valider qualité | vLLM natif |

**Guide rapide :**
- Client veut Ollama / LM Studio / laptop → GGUF Q4_K_M
- API multi-users cloud → AWQ (qualité maximale)
- Déploiement NVIDIA dédié perf max → EXL2 ou FP8
- Pas de GPU → GGUF CPU

---

## 4. Évaluation — harnais & benchmarks

### Harnais standards

| Harnais | Usage | Lien |
|---------|-------|------|
| **lm-evaluation-harness** (EleutherAI) | 60+ benchmarks, industrie standard | Résultats via `compare_to_baseline` (31) |
| **LightEval** (HuggingFace) | Big-Bench + HELM, large éventail | Idem |
| Benchmarks tâche-spécifiques | Perplexité, BLEU, ROUGE, F1 | `compute_metrics` (29) |

### Benchmarks clés

| Benchmark | Dimension | Quand prioritaire |
|-----------|-----------|-------------------|
| **MMLU-Pro** | Raisonnement, 10 choix (+ discriminant que MMLU) | Tâche généraliste |
| MMLU | Connaissance générale | Comparaison historique |
| GSM8K / MATH | Raisonnement mathématique | Tâche code/analyse |
| GPQA | Raisonnement scientifique expert | Domaine scientifique |
| **IFEval** | Suivi d'instructions | Chatbot / instruction following |
| TruthfulQA | Factualité | Tâches à risque de hallucination |
| HellaSwag | Compréhension contextuelle | — |
| ARC-Challenge | Raisonnement multi-choix | — |
| WinoGrande | Résolution d'ambiguïté | — |
| BBH | Raisonnement complexe | — |

### Protocole d'évaluation Zero-Data

- Benchmark sur données synthétiques : local, via `evaluate_on_synthetic` (27)
- Benchmark sur données réelles : côté client via `evaluate_on_validation_set` (28) → seules les métriques remontent
- Comparaison : **toujours** `compare_to_baseline` (31) sur le **même harnais** et les **mêmes prompts**
- Scan biais : `bias_fairness_scan` (32) sur prompts synthétiques non-sensibles

---

## 5. Stack d'exécution & serving (mai 2026)

### Fine-tuning

- **Unsloth** : noyaux optimisés LoRA/QLoRA, 2× plus rapide, ~70% moins de VRAM vs HuggingFace natif
  - Routé via unsloth-server MCP (sur infra opérateur ou enclave client)
  - Fine-Tuning OS n'embarque pas torch/unsloth
- **Axolotl** : alternative mature, configuré via YAML, intégration LoRA/QLoRA/GaLore
- **TRL SFTTrainer** : option pour GaLore ou cas custom

### Quantization

- AutoAWQ → AWQ
- llama.cpp (`convert-hf-to-gguf.py`) → GGUF
- ExLlamaV2 → EXL2
- AutoGPTQ → GPTQ + Marlin

### Serving (inférence production)

| Moteur | Forces | Cas d'usage |
|--------|--------|-------------|
| **SGLang** | Prefix caching, ~29% débit + sur petits modèles, ~3.1× sur DeepSeek-V3, fort multi-tour/agent | API multi-users, agentic |
| **vLLM** | Généraliste solide, PagedAttention, large compatibilité | API standard |
| **TensorRT-LLM** | Perf NVIDIA max | Déploiement NVIDIA dédié |
| **llama.cpp server** | CPU / edge | Contrainte GPU absente |

Conteneur d'inférence généré par `build_inference_container` (41) — API compatible OpenAI.

### Déploiement

- Images Docker + docker-compose (généré par outils 11, 41)
- Helm/K8s pour scaling horizontal
- Ray Serve / BentoML / Triton pour orchestration avancée
- Health check : `GET /health` obligatoire

---

## 6. Risques et anti-patterns techniques

| Risque | Symptôme | Outil de détection | Remédiation |
|--------|----------|--------------------|-------------|
| Catastrophic forgetting | Métriques baseline dégradées | `compare_to_baseline` (31) | Regularisation, replay |
| Overfitting | Loss synthétique < loss réelle | `compare_to_baseline` (31) | Réduire epochs, augmenter dropout |
| Tokenizer incompatible | Garbage output | `evaluate_on_synthetic` (27) | Vérifier pad_token, chat_template |
| Licence incompatible | `commercial_ok: false` | `verify_model_license` (36) | Changer de modèle de base |
| Dérive post-déploiement | Métriques baissent dans le temps | `check_model_rot` (61) | `suggest_retraining` (62) |

---

*Figé au 2026-05-29. Réévaluer chaque trimestre. Les classements de modèles
(LMSYS, OpenLLM Leaderboard, LiveBench) évoluent mensuellement.*
