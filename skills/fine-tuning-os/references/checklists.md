# Go/No-Go Checklists — Per Phase

> Each item is mapped to the MCP tool that performs it.
> Back: [SKILL.md](../SKILL.md)

---

## Phase 1 — Preparation Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 1.1 | NDA signed before any technical disclosure | `generate_nda` (48) + `sign_document` (54) | |
| 1.2 | Project structure initialized | `create_project_structure` (4) | |
| 1.3 | Training config rendered without template errors | `create_training_config` (1) | |
| 1.4 | Requirements file generated | `generate_requirements` (3) | |
| 1.5 | Model license verified: `commercial_ok: true` | `verify_model_license` (36) | |
| 1.6 | Base model HF download command emitted | `cache_base_model` (2) | |
| 1.7 | Client confirmed spec (task, format, target metrics) in writing | — | |

**Gate:** all 1.1-1.7 checked → proceed to Phase 2.

---

## Phase 2 — Synthetic Data Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 2.1 | Data schema defined and persisted in project.json | `describe_expected_data_format` (6) | |
| 2.2 | Synthetic dataset generated (n=10-50, seed recorded) | `generate_synthetic_dataset` (7) | |
| 2.3 | Synthetic dataset passes schema validation | `validate_data_schema` (8) | |
| 2.4 | Seed logged in events.jsonl | `log_project_event` (58) | |
| 2.5 | Split script rendered | `split_dataset_config` (10) | |
| 2.6 | Client confirmed schema matches real data structure | — | |

**Gate:** all 2.1-2.6 → proceed to Phase 3.

---

## Phase 3 — Pipeline Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 3.1 | Dockerfile.train generated | `build_docker_image` (11) | |
| 3.2 | Docker build succeeds (or dry_run command verified) | `test_docker_build` (12) | |
| 3.3 | Synthetic micro-train: initial loss < 10, no NaN | `run_local_synthetic_train` (13) | |
| 3.4 | Metrics retrieved and sane | `get_local_metrics` (14) | |
| 3.5 | Remote config pre-flight: no missing critical env vars | `dry_run_remote_config` (15) | |
| 3.6 | Hyperparameters optimized if needed | `optimize_hyperparams` (16) | |
| 3.7 | Unit tests generated and committed | `generate_unit_tests` (17) | |
| 3.8 | Code AST audit: 0 CRITICAL network calls | `audit_code_no_network` (33) | |
| 3.9 | Dockerfile security: 0 CRITICAL findings | `audit_dockerfile_security` (34) | |
| 3.10 | Security report generated (MD+PDF+SHA256) | `generate_security_report` (37) | |
| 3.11 | Client approved pipeline demo | `request_client_approval` (59) | |
| 3.12 | Second billing milestone invoice issued | `generate_invoice` (60) | |

**Gate:** all 3.1-3.12 → proceed to Phase 4. **Block on 3.8, 3.9 CRITICAL.**

---

## Phase 4 — Execution Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 4.1 | Image pushed to registry (or command provided) | `push_docker_to_registry` (18) | |
| 4.2 | Deployment command generated and delivered to client | `generate_deployment_command` (19) | |
| 4.3 | Training launched (or command provided) | `trigger_remote_training` (20) | |
| 4.4 | All logs sanitized before Claude context | `sanitize_logs_for_claude` (38) | |
| 4.5 | Loss converges (no NaN, no plateau > 20% of run) | `detect_anomalies` (23) | |
| 4.6 | No CRITICAL anomaly alerts | `detect_anomalies` (23) | |
| 4.7 | Early stopping evaluated and decision documented | `early_stopping_check` (25) | |
| 4.8 | Training completion logged in events.jsonl | `log_project_event` (58) | |

**Gate:** all 4.1-4.8 → proceed to Phase 5. **Block on 4.5, 4.6 unresolved CRITICAL.**

---

## Phase 5 — Evaluation Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 5.1 | Checkpoint metadata retrieved | `download_checkpoint_metadata` (26) | |
| 5.2 | Synthetic eval completed, metrics sane | `evaluate_on_synthetic` (27) | |
| 5.3 | Real validation eval completed (client-side) | `evaluate_on_validation_set` (28) | |
| 5.4 | Metrics computed (task-appropriate) | `compute_metrics` (29) | |
| 5.5 | Baseline comparison generated | `compare_to_baseline` (31) | |
| 5.6 | No regression vs baseline | `compare_to_baseline` (31) | |
| 5.7 | Bias scan: no HIGH findings (or documented exceptions) | `bias_fairness_scan` (32) | |
| 5.8 | Predictions sample generated for human review | `generate_predictions_sample` (30) | |
| 5.9 | Client approval of metrics received | `request_client_approval` (59) | |
| 5.10 | Third billing milestone invoice issued | `generate_invoice` (60) | |

**Gate:** 5.9 must be `approved` before proceeding to Phase 7. **Block on 5.6, 5.7 HIGH.**

---

## Phase 6 — Security Gate (runs in parallel with 3-4, mandatory before delivery)

| # | Check | Tool | Status |
|---|-------|------|--------|
| 6.1 | Training code network audit: 0 CRITICAL | `audit_code_no_network` (33) | |
| 6.2 | Inference Dockerfile audit: 0 CRITICAL | `audit_dockerfile_security` (34) | |
| 6.3 | Data leakage scan on all outputs/: 0 risks | `scan_data_leakage_risk` (35) | |
| 6.4 | Model license verified for delivery | `verify_model_license` (36) | |
| 6.5 | Security report final (MD+PDF+SHA256) | `generate_security_report` (37) | |
| 6.6 | SHA256 of security report logged in events.jsonl | `log_project_event` (58) | |

**Gate:** 6.1-6.6 all clear before any deliverable leaves operator infrastructure.

---

## Phase 7 — Packaging & Delivery Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 7.1 | LoRA weights merged (or command provided) | `merge_lora_weights` (39) | |
| 7.2 | Quantization applied for target format | `quantize_model` (40) | |
| 7.3 | Inference container built | `build_inference_container` (41) | |
| 7.4 | Inference container audited (audit_dockerfile_security) | `audit_dockerfile_security` (34) | |
| 7.5 | Inference API tested with synthetic prompts | `test_inference_api` (43) | |
| 7.6 | Deliverable encrypted (AES-256-GCM) | `encrypt_deliverable` (44) | |
| 7.7 | AES key stored securely (not in any project file) | Manual check | |
| 7.8 | Encrypted archive SHA256 verified | `encrypt_deliverable` (44) | |
| 7.9 | Deliverable uploaded or command provided | `upload_deliverable` (45) | |
| 7.10 | Delivery note generated (MD+PDF) | `generate_delivery_note` (46) | |
| 7.11 | Client confirmed receipt and SHA256 verification | `request_client_approval` (59) | |
| 7.12 | Fourth billing milestone invoice issued | `generate_invoice` (60) | |

**Gate:** 7.11 `approved` + 7.7 manual check → proceed to Phase 8.

---

## Phase 8 — Documentation Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 8.1 | Contract signed by both parties (if not done at start) | `generate_contract` (47) + `sign_document` (54) | |
| 8.2 | NDA signed | `generate_nda` (48) + `sign_document` (54) | |
| 8.3 | Performance report generated (MD+PDF+SHA256) | `generate_performance_report` (49) | |
| 8.4 | User guide complete (API examples) | `generate_user_guide` (50) | |
| 8.5 | Deployment guide complete | `generate_deployment_guide` (51) | |
| 8.6 | **Destruction certificate issued** (AFTER delivery confirmed) | `generate_destruction_certificate` (52) | |
| 8.7 | All PDFs SHA256-logged in events.jsonl | `log_project_event` (58) | |
| 8.8 | All documents signed/dated | `sign_document` (54) | |

**Gate:** 8.6 is non-negotiable before project closure (RGPD compliance).

---

## Phase 9 — Client Relations Gate

| # | Check | Tool | Status |
|---|-------|------|--------|
| 9.1 | All approvals recorded (approval_id + status=approved) | `request_client_approval` (59) | |
| 9.2 | events.jsonl has entry for every major milestone | `log_project_event` (58) | |
| 9.3 | Final invoice issued | `generate_invoice` (60) | |
| 9.4 | Final status update sent | `send_status_update` (56) | |
| 9.5 | PROJECT_CLOSED event logged | `log_project_event` (58) | |

---

## Phase 10 — Maintenance Gate (recurring)

| # | Check | Tool | Cadence |
|---|-------|------|---------|
| 10.1 | Model drift check completed | `check_model_rot` (61) | Monthly |
| 10.2 | Drift events logged | `log_project_event` (58) | Per check |
| 10.3 | Retraining recommended if threshold exceeded | `suggest_retraining` (62) | On trigger |
| 10.4 | Client approval for retraining budget | `request_client_approval` (59) | Per retrain |
| 10.5 | Base model update reviewed | `update_base_model` (63) | Quarterly |
| 10.6 | Server updated | `mcp_self_update` (64) | Monthly |
