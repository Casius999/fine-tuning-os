# Troubleshooting Guide

> Symptom → Cause → Tool / Action
> Back: [SKILL.md](../SKILL.md)

---

## Training Anomalies

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **Loss = NaN at step 1** | LR too high; bad tokenizer (missing pad_token) | `optimize_hyperparams` (16): lower LR 10×; check tokenizer pad_token config |
| **Loss spikes mid-training** | LR too high after warmup; bad batch | `detect_anomalies` (23) → `pause_resume_training` (24); reduce LR |
| **Loss plateau > 20% of run** | LR too low; data quality issue; rank too small | `optimize_hyperparams` (16): increase LR, increase rank, check data diversity |
| **Loss oscillates without converging** | Batch size too small; missing grad clipping | Increase batch_size or grad_accum; add `max_grad_norm=1.0` |
| **NaN loss after checkpoint resume** | Corrupted checkpoint | Download fresh checkpoint; `download_checkpoint_metadata` (26) to verify |
| **Training faster than expected but poor results** | Packing error; data repetition | Check synthetic data diversity; verify packing=True with pad_token |
| **Very high initial loss (> 10 on synthetic)** | Wrong task_type in config; wrong format | Verify `describe_expected_data_format` schema matches config task_type |

---

## Memory / OOM Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **CUDA OOM during training** | Batch size too large for available VRAM | `optimize_hyperparams` (16): reduce batch_size; add gradient checkpointing |
| **OOM during merge** | Insufficient RAM/VRAM for 16-bit merge | Run merge in enclave with more memory; use CPU offloading |
| **OOM during quantization** | GGUF/AWQ on GPU without offload | Run on CPU; specify `--cpu` flag in quantize command |
| **Docker container OOM** | ulimits not set; shared memory | Add `--shm-size 8g` to docker run; increase `--memory` limit |
| **VRAM near 100% during synthetic train** | Model too large for GPU | Switch to QLoRA; reduce max_seq_len; reduce rank |

---

## Pipeline / Build Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **Docker build fails: CUDA not found** | Base image CUDA version mismatch with driver | Check driver version; switch base image (e.g., `cuda12.1` → `cuda12.4`) |
| **Docker build fails: pip install error** | Pinned version conflict | `generate_requirements` (3) with updated extras; check PyPI for latest compatible |
| **`test_docker_build` returns error output** | Internal test failed | Inspect sanitized output; check tokenizer or import error |
| **`build_docker_image` returns dry_run** | Docker not installed or `FTOS_LOCAL_PYTHON` not set | Install Docker; set `FTOS_LOCAL_PYTHON` or use unsloth-server |
| **Template render error** | Jinja2 syntax in config template | Check `templates/configs/` for syntax errors; re-run `create_training_config` |
| **`dry_run_remote_config` reports missing vars** | Required env vars not set | Set the listed env vars before execution |

---

## Security / Leakage Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **`audit_code_no_network` CRITICAL: `requests.get` found** | Training script makes external call | Remove network call; add to allowlist only if absolutely necessary |
| **`audit_dockerfile_security` HIGH: running as root** | No `USER` directive | Add `USER trainer` after setup; `audit_dockerfile_security` re-run |
| **`audit_dockerfile_security` CRITICAL: `curl \| sh`** | Remote code execution pattern | Remove; use pinned packages instead |
| **`scan_data_leakage_risk` finds email pattern in logs** | PII leaked through log statement | `sanitize_logs_for_claude` (38) on all outputs; re-run `scan_data_leakage_risk`; incident response |
| **`sanitize_logs_for_claude` masked_count > 0** | Sensitive data in logs | Log the event; do not pass original to Claude; use sanitized only |
| **`detect_anomalies` flags "data pattern" in loss curve** | Possible memorization of training data | Reduce epochs; add data augmentation; evaluate with `bias_fairness_scan` |
| **`verify_model_license` commercial_ok: false** | License restricts commercial use | Switch to Apache-2.0 or MIT model (see sota-may-2026.md) |

---

## Evaluation Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **FT metrics worse than baseline** | Catastrophic forgetting; bad training | Check data format; reduce epochs; add regularization; re-run `compare_to_baseline` |
| **`evaluate_on_synthetic` very high perplexity** | Model not loading correctly | Check checkpoint path; re-run `download_checkpoint_metadata` |
| **Client rejects metrics** | Target not met; misaligned expectations | `schedule_meeting` (57); review targets in contract; iterate training |
| **`bias_fairness_scan` HIGH severity** | Model biased on tested categories | Adjust training data; re-evaluate; document exceptions if acceptable |
| **`compute_metrics` returns 0 BLEU on reasonable output** | BLEU implementation issue; tokenization | Verify ref/pred format; use ROUGE as backup |

---

## Delivery / Packaging Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **`merge_lora_weights` returns dry_run** | unsloth-server not configured; `FTOS_LOCAL_PYTHON` missing | Configure unsloth-server or set `FTOS_LOCAL_PYTHON`; present command to client |
| **`quantize_model` fails: conversion error** | llama.cpp version incompatible with model architecture | Update llama.cpp; check model architecture support |
| **`test_inference_api` timeout** | Model loading slowly; GPU OOM on inference | Reduce max_tokens; check GPU; use smaller quantization |
| **`encrypt_deliverable` fails** | File not found; disk space | Check paths; ensure > 2× model size free |
| **`upload_deliverable` fails** | SFTP credentials wrong; network issue | Check `FTOS_SFTP_*` vars; test SFTP connection manually |
| **SHA256 mismatch after upload** | File corruption during transfer | Re-upload; verify source SHA256 before upload |

---

## Document / Contract Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **`export_document_pdf` fails** | weasyprint CSS error; missing dependency | Check weasyprint install; simplify Markdown table formatting |
| **`sign_document` returns dry_run** | E-sign API not configured | Configure e-sign API or use manual signature; log with `log_project_event` |
| **`generate_destruction_certificate` missing artifacts list** | project.json incomplete | Manually list files in `files` argument; ensure events.jsonl has delivery entry |

---

## Maintenance / Drift Issues

| Symptom | Likely Cause | Tool / Action |
|---------|-------------|---------------|
| **`check_model_rot` threshold_exceeded: true** | Distribution shift; new entity types | `suggest_retraining` (62); notify client; plan retrain cycle |
| **Drift detected but client won't authorize retrain** | Budget constraint | Document in events.jsonl; reduce SLA threshold; monitor more frequently |
| **`update_base_model` breaks pipeline** | New model architecture incompatible | Re-run Phase 3 (pipeline test) with new model; check tokenizer changes |
| **`mcp_self_update` breaks tools** | Breaking API change in server update | Pin version; roll back to previous tag; report issue |

---

## General Debugging Flow

```
Problem observed
  └─ Check events.jsonl for timeline
       └─ Identify last successful tool call
            └─ Re-run from that point with `log_project_event` before each step
                 └─ If external output involved: run sanitize_logs_for_claude first
                      └─ If anomaly: run detect_anomalies on sanitized data
                           └─ If security concern: run scan_data_leakage_risk
                                └─ Document resolution in events.jsonl
```

When in doubt: **sanitize first, analyze second, document always.**
