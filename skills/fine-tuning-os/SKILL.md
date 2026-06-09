---
name: fine-tuning-os
description: >
  Use this skill when conducting a professional LLM fine-tuning engagement in
  Zero-Data mode via the MCP server fine-tuning-os. Triggers on: prestation de
  fine-tuning LLM, livraison de modèle affiné, pipeline Zero-Data, orchestration
  des 64 outils fine-tuning-os, cycle de vie entraînement (préparation / données
  synthétiques / pipeline / exécution / évaluation / sécurité / packaging /
  livraison / documentation / contrats / relation client / maintenance). Invoke
  whenever Claude pilots the fine-tuning-os MCP to deliver a fine-tuning service
  without exposing real client data.
---

# Fine-Tuning OS — Operator Playbook

## Overview

Fine-Tuning OS is a 64-tool MCP server that turns Claude into the **executive
orchestrator** of a professional LLM fine-tuning engagement. It covers the full
lifecycle — preparation, synthetic data, pipeline construction, training
execution, evaluation, security audit, packaging, delivery, documentation,
contracts, client relations, and maintenance — while enforcing a strict
**Zero-Data boundary**: neither Claude nor the server ever sees real client data
or unencrypted trained weights leaving the client enclave.

All 64 tools return a uniform `Result{success, data, error, meta}` envelope.
C2 tools always include `meta.executed`, `meta.dry_run`, `meta.command` so the
operator knows exactly what ran versus what was emitted for human execution.

**Execution boundary** (§16 of spec): Fine-Tuning OS does not embed torch or
unsloth. Heavy GPU work runs either (a) inside the **client enclave** (Zero-Data
nominal — C2 tools emit the exact command; only sanitized metrics return) or
(b) via the companion **unsloth-server MCP** on operator infrastructure,
exclusively on synthetic or explicitly authorized data.

---

## Phase Map — 10 Phases × 64 Tools

| # | Phase | Tools | Gate to next phase | Reference |
|---|-------|-------|--------------------|-----------|
| 1 | **Preparation** | `create_project_structure` `load_project_template` `create_training_config` `generate_requirements` `cache_base_model` | Spec signed by client; config rendered; license verified | [01-preparation.md](references/01-preparation.md) |
| 2 | **Synthetic Data** | `describe_expected_data_format` `generate_synthetic_dataset` `validate_data_schema` `anonymize_dataset_preview` `split_dataset_config` | Schema validated; synthetic JSONL committed; split script rendered | [02-synthetic-data.md](references/02-synthetic-data.md) |
| 3 | **Pipeline** | `build_docker_image` `test_docker_build` `run_local_synthetic_train` `get_local_metrics` `dry_run_remote_config` `optimize_hyperparams` `generate_unit_tests` | Docker builds clean; micro-train passes; unit tests green; security audit (phase 6) pre-flight OK | [03-pipeline.md](references/03-pipeline.md) |
| 4 | **Execution** | `push_docker_to_registry` `generate_deployment_command` `trigger_remote_training` `stream_remote_logs` `monitor_training_metrics` `detect_anomalies` `pause_resume_training` `early_stopping_check` | Training completed (or early-stopped); no anomaly alerts; sanitized loss curve delivered | [04-execution.md](references/04-execution.md) |
| 5 | **Evaluation** | `download_checkpoint_metadata` `evaluate_on_synthetic` `evaluate_on_validation_set` `compute_metrics` `generate_predictions_sample` `compare_to_baseline` `bias_fairness_scan` | Client approval of metrics via `request_client_approval` | [05-evaluation.md](references/05-evaluation.md) |
| 6 | **Security Audit** | `audit_code_no_network` `audit_dockerfile_security` `scan_data_leakage_risk` `verify_model_license` `generate_security_report` `sanitize_logs_for_claude` | Security report generated (MD+PDF+SHA256); zero critical findings or documented exceptions | [06-security-audit.md](references/06-security-audit.md) |
| 7 | **Packaging** | `merge_lora_weights` `quantize_model` `build_inference_container` `generate_inference_config` `test_inference_api` `encrypt_deliverable` `upload_deliverable` `generate_delivery_note` | Delivery note accepted; SHA256 verified; deliverable uploaded | [07-packaging-delivery.md](references/07-packaging-delivery.md) |
| 8 | **Docs & Contracts** | `generate_contract` `generate_nda` `generate_performance_report` `generate_user_guide` `generate_deployment_guide` `generate_destruction_certificate` `export_document_pdf` `sign_document` | All documents signed/dated; destruction certificate issued; PDF SHA256 logged | [08-docs-contracts.md](references/08-docs-contracts.md) |
| 9 | **Client Relations** | `onboard_client` `send_status_update` `schedule_meeting` `log_project_event` `request_client_approval` `generate_invoice` | Invoice issued; final approval recorded in `events.jsonl` | [09-client-relations.md](references/09-client-relations.md) |
| 10 | **Maintenance** | `check_model_rot` `suggest_retraining` `update_base_model` `mcp_self_update` | Drift threshold defined in SLA; retraining triggered if exceeded | [10-maintenance.md](references/10-maintenance.md) |

> **Note:** Phase 6 (Security Audit) runs in parallel during phases 3-4, not
> strictly after. `sanitize_logs_for_claude` is called by C2 tools throughout.

---

## Zero-Data Invariants — Summary

Full detail: [zero-data-invariants.md](references/zero-data-invariants.md)

**Golden rules for the operator:**

1. **Never read real client data.** All data-touching tools operate on schema
   descriptions or synthetic examples only (C1 class).
2. **Never exfiltrate trained weights in cleartext.** Weights stay in the
   client enclave. Only `download_checkpoint_metadata` retrieves metadata
   (not weights). Packaged weights are AES-256-GCM encrypted before leaving.
3. **Always sanitize before sending to Claude.** Any external text (logs, shell
   output, error traces) must pass through `sanitize_logs_for_claude` (tool 38)
   before inclusion in a Claude context.
4. **Secrets only via environment variables.** Never log, echo, or embed
   credentials in config files, reports, or messages.
5. **C2 dry_run is not failure.** When a target is not configured, `meta.dry_run=true`
   + `meta.command=<exact runnable>` is the correct output — present it to the
   client for manual execution.

**Class contracts:**

| Class | Behaviour | Real data? |
|-------|-----------|-----------|
| **C1** CODEGEN/PURE | Offline, deterministic, local file generation | Never |
| **C2** EMIT/INGEST | Emits exact command; executes live only if target env vars set | Only on client side; server receives only sanitized output |
| **C3** AUDIT/SECURITY | Static analysis of our own artefacts + log filtering | Never |

---

## Decision Tree — Which Tool When

```
Project start
  └─ onboard_client (55) → create_project_structure (4) → load_project_template (5)
       └─ verify_model_license (36) → create_training_config (1) → generate_requirements (3)
            └─ cache_base_model (2) [C2-dry_run unless HF configured]

Schema & data
  └─ describe_expected_data_format (6) → generate_synthetic_dataset (7)
       └─ validate_data_schema (8) → anonymize_dataset_preview (9) → split_dataset_config (10)

Pipeline build
  └─ build_docker_image (11) [C2] → test_docker_build (12) [C2]
       └─ run_local_synthetic_train (13) [C2] → get_local_metrics (14)
            └─ optimize_hyperparams (16) → generate_unit_tests (17)
                 └─ dry_run_remote_config (15)

Security (runs in parallel, mandatory before execution)
  └─ audit_code_no_network (33) + audit_dockerfile_security (34)
       └─ verify_model_license (36) + scan_data_leakage_risk (35)
            └─ generate_security_report (37)

Training execution
  └─ push_docker_to_registry (18) [C2] → generate_deployment_command (19)
       └─ trigger_remote_training (20) [C2]
            └─ stream_remote_logs (21) [C2] → sanitize_logs_for_claude (38)
                 └─ monitor_training_metrics (22) → detect_anomalies (23)
                      └─ early_stopping_check (25) [pause_resume_training (24) if needed]

Evaluation
  └─ download_checkpoint_metadata (26) [C2] → evaluate_on_synthetic (27)
       └─ evaluate_on_validation_set (28) [C2-client-side]
            └─ compute_metrics (29) → compare_to_baseline (31) → bias_fairness_scan (32)
                 └─ generate_predictions_sample (30) → request_client_approval (59)

Packaging
  └─ merge_lora_weights (39) [C2] → quantize_model (40) [C2]
       └─ build_inference_container (41) [C2] → generate_inference_config (42)
            └─ test_inference_api (43) [C2] → encrypt_deliverable (44)
                 └─ upload_deliverable (45) [C2] → generate_delivery_note (46)

Documentation
  └─ generate_contract (47) + generate_nda (48)
       └─ generate_performance_report (49) + generate_user_guide (50)
            └─ generate_deployment_guide (51) → generate_destruction_certificate (52)
                 └─ export_document_pdf (53) → sign_document (54) [C2]

Billing & closure
  └─ generate_invoice (60) → send_status_update (56) [C2]
       └─ log_project_event (58) [final event] → schedule_meeting (57) [C2] [handoff]

Maintenance (post-delivery)
  └─ check_model_rot (61) → suggest_retraining (62)
       └─ update_base_model (63) → mcp_self_update (64) [C2]
```

---

## Execution Boundary (§16)

Fine-Tuning OS is a **piloting factory** (orchestration, security, documentation,
delivery) — not a training engine. The distinction matters:

- **C1/C3 tools** run entirely inside Fine-Tuning OS (offline, no torch).
- **C2 tools that trigger training** (`run_local_synthetic_train`, `merge_lora_weights`,
  `quantize_model`) route to one of two backends:
  - **Client enclave** (Zero-Data nominal): C2 emits the Docker/shell command;
    the client runs it; only sanitized metrics return.
  - **unsloth-server MCP** on operator infrastructure: used for synthetic
    pipeline proof or explicitly authorized runs. Requires `FTOS_LOCAL_PYTHON`
    (or unsloth-server configured as target).
- Fine-Tuning OS carries **no torch/unsloth dependency**; it is installable on
  any machine.

---

## Reference Files (load on demand)

| File | Content |
|------|---------|
| [01-preparation.md](references/01-preparation.md) | Tools 1-5, pre-flight, model selection |
| [02-synthetic-data.md](references/02-synthetic-data.md) | Tools 6-10, schema design, JSONL generation |
| [03-pipeline.md](references/03-pipeline.md) | Tools 11-17, Docker, synthetic micro-train |
| [04-execution.md](references/04-execution.md) | Tools 18-25, enclave execution, log sanitization |
| [05-evaluation.md](references/05-evaluation.md) | Tools 26-32, metrics, baseline comparison |
| [06-security-audit.md](references/06-security-audit.md) | Tools 33-38, AST audit, Dockerfile hardening |
| [07-packaging-delivery.md](references/07-packaging-delivery.md) | Tools 39-46, merge/quant/encrypt/deliver |
| [08-docs-contracts.md](references/08-docs-contracts.md) | Tools 47-54, contracts, NDA, destruction cert |
| [09-client-relations.md](references/09-client-relations.md) | Tools 55-60, onboarding, approvals, invoicing |
| [10-maintenance.md](references/10-maintenance.md) | Tools 61-64, drift detection, retraining |
| [zero-data-invariants.md](references/zero-data-invariants.md) | Golden rules, class contracts, incident response |
| [legal-compliance.md](references/legal-compliance.md) | French law: Code civil, CPI, RGPD, secret affaires |
| [sota-may-2026.md](references/sota-may-2026.md) | Model selection, LoRA/QLoRA, quantization, eval |
| [pricing-packaging.md](references/pricing-packaging.md) | Offer structure, milestones, SLA, billing |
| [checklists.md](references/checklists.md) | Go/no-go gate per phase, mapped to tools |
| [troubleshooting.md](references/troubleshooting.md) | Symptom → cause → tool/action table |
