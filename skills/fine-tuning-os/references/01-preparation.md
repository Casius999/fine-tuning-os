# Phase 1 — Preparation & Configuration

> Tools 1-5 | Class: C1 (tools 1,3,4,5) + C2 (tool 2)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Establish the project structure, training configuration, environment, and model
cache before any data or pipeline work begins. This phase is entirely offline
(C1) except for `cache_base_model` (C2 — emits the HF download command).

---

## Inputs

- Client brief: target task, volume estimate, latency/cost constraints
- Choice of base model (see [sota-may-2026.md](sota-may-2026.md) §Model Selection)
- Framework preference: `unsloth` | `axolotl` | `custom`
- LoRA parameters (rank, alpha, dropout) or template name

## Outputs

- `<project_id>/project.json` — project state
- `<project_id>/config/training.yaml` — rendered config
- `<project_id>/requirements.txt` — pinned dependencies
- Scaffolded directory tree: `config/`, `data/synthetic/`, `src/`, `docker/`,
  `outputs/`, `reports/`, `deliverables/`, `docs/`
- HF download command (dry_run or executed)

---

## Tool Sequence

### Step 1 — Initialize project

```
create_project_structure(project_id="acme-ft-001", client_name="Acme Corp")
```
Creates the workspace tree and `project.json`. **Must be first.**

### Step 2 — Apply template or configure manually

**If using a preset** (fastest):
```
load_project_template(template_name="lora-mistral-v3", project_id="acme-ft-001")
```
Available presets: `lora-mistral-v3`, `lora-llama3-8b`, `axolotl-llama3`,
`qlora-mistral-chat`.

**If custom:**
```
create_training_config(
    project_id="acme-ft-001",
    base_model="Qwen/Qwen3-7B",
    framework="unsloth",
    lora_rank=32,
    lr=2e-4,
    batch_size=2,
    epochs=3,
    scheduler="cosine",
    max_seq_len=4096
)
generate_requirements(framework="unsloth", project_id="acme-ft-001")
```

### Step 3 — Verify model license

**Always run before any commitment** (see [legal-compliance.md](legal-compliance.md)):
```
verify_model_license(repo_id="Qwen/Qwen3-7B")
# → {license: "Apache-2.0", commercial_ok: true}
```
Stop if `commercial_ok=false` or license is unknown. Escalate to client.

### Step 4 — Cache base model (C2)

```
cache_base_model(repo_id="Qwen/Qwen3-7B", dest="/data/models/qwen3-7b")
# Returns: {command: "huggingface-cli download ...", dry_run: true}
# Execute the returned command in the client enclave or local infra.
```
`meta.dry_run=true` unless `HF_TOKEN` + `HF_HOME` are configured. This is
correct — present the command to the client/operator for manual execution.

---

## Go/No-Go Gate

Before proceeding to Phase 2:

- [ ] `project.json` exists and readable
- [ ] `config/training.yaml` rendered (no template errors)
- [ ] `requirements.txt` generated
- [ ] `verify_model_license` returns `commercial_ok=true`
- [ ] Client has confirmed spec (task type, expected data format, target metrics)
- [ ] NDA signed (generate via `generate_nda` in Phase 8, but execute early if client requires)

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Wrong framework key | `create_training_config` returns `error: unknown framework` | Use `unsloth`, `axolotl`, or `custom` |
| Template not found | `load_project_template` returns `error: unknown template` | List available presets in tool description |
| Restrictive license | `verify_model_license` returns `commercial_ok=false` | Switch to Apache-2.0/MIT model (see sota-may-2026.md) |
| Project already exists | `create_project_structure` fails with duplicate | Use unique `project_id` or archive old project |
| LR too high | Config accepted but diverges at training | Use `optimize_hyperparams` (tool 16) in Phase 3 |

---

## Hyperparameter Starting Points

See [sota-may-2026.md](sota-may-2026.md) §14.2 for full decision tree.

| Method | Rank | Alpha | LR | Batch | Grad Accum |
|--------|------|-------|----|-------|-----------|
| LoRA | 16-32 | 2×rank | 2e-4 | 2 | 4-8 |
| QLoRA | 32-64 | 2×rank | 1e-4 | 2 | 8 |
| DoRA | 16-32 | 2×rank | 2e-4 | 2 | 4-8 |

Scheduler: `cosine` with 3-5% warmup. Packing: enabled by default.
