# Phase 4 — Training Execution

> Tools 18-25 | Class: C2 (18, 20, 21, 22, 24) + C1 (19, 23, 25)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Launch the training job in the client's enclave (or on authorized operator
infrastructure), stream sanitized logs, monitor metrics, and detect anomalies
— all while maintaining the Zero-Data boundary. Real trained weights never
leave the enclave; only sanitized metrics and status reach Fine-Tuning OS.

---

## Execution Boundary (§16)

```
Fine-Tuning OS                   Client Enclave / Operator Infra
─────────────────                ──────────────────────────────────
generate_deployment_command  →   operator pastes docker run cmd
push_docker_to_registry      →   registry accessible to enclave
trigger_remote_training     ──►  training starts (torch/unsloth runs here)
stream_remote_logs          ◄──  sanitized logs returned
monitor_training_metrics    ◄──  loss/lr curves (sanitized)
detect_anomalies (C1)            analyzes sanitized data locally
pause_resume_training       ──►  SSH command to enclave
early_stopping_check (C1)        decision from sanitized metrics only
```

---

## Inputs

- Docker image in registry (from Phase 3)
- SSH/API credentials configured in env vars (or dry_run)
- Sanitized metrics from stream

## Outputs

- `job_id` (enclave side)
- Time-series metrics (loss, lr, GPU util)
- Anomaly report
- Checkpoint metadata

---

## Environment Variables (C2 gating)

| Tool | Requires | Dry-run if missing |
|------|----------|--------------------|
| `push_docker_to_registry` | `FTOS_REGISTRY` + `FTOS_REGISTRY_TOKEN` | Returns `docker push` command |
| `trigger_remote_training` | `FTOS_SSH_HOST` + `FTOS_SSH_KEY` | Returns SSH command |
| `stream_remote_logs` | `FTOS_SSH_HOST` + `FTOS_SSH_KEY` | Returns `ssh ... tail -f` command |
| `monitor_training_metrics` | same as stream | Returns polling command |
| `pause_resume_training` | same as stream | Returns SSH command |

---

## Tool Sequence

### Step 1 — Push image to registry (C2)

```
push_docker_to_registry(image_tag="acme-ft-001:latest", registry="registry.client.com")
# → {command: "docker push ...", dry_run: true} or {executed: true, digest: "sha256:..."}
```

### Step 2 — Generate deployment command (C1)

```
generate_deployment_command(
    image="registry.client.com/acme-ft-001:latest",
    mounts=["/data/client:/data/train:ro", "/checkpoints:/checkpoints:rw"],
    env={"EPOCHS": "3", "LR": "2e-4"},
    gpus="all"
)
# → {command: "docker run --gpus all -v /data/client:/data/train:ro ..."}
```

**Always C1** — no network, no execution. Present to client to run in enclave.

### Step 3 — Trigger remote training (C2)

```
trigger_remote_training(
    target={"type": "ssh", "host": "${FTOS_SSH_HOST}"},
    command="cd /training && docker compose up -d"
)
# → {job_id: "run-20260601-0932", dry_run: false, executed: true}
# or {command: "ssh bastion 'cd /training && docker compose up -d'", dry_run: true}
```

### Step 4 — Stream and sanitize logs (C2)

```
stream_remote_logs(job_id="run-20260601-0932", n_lines=200)
# → {logs: "<sanitized output>", masked_count: 3}
```

`sanitize_logs_for_claude` is called internally. Never pass raw logs to Claude.

### Step 5 — Monitor metrics (C2)

```
monitor_training_metrics(source="run-20260601-0932")
# → {series: [{step: 100, loss: 1.82, lr: 2e-4, gpu_util: 94},...]}
```

### Step 6 — Detect anomalies (C1)

```
detect_anomalies(logs="<sanitized>", metrics=[...])
# → {alerts: [{type: "divergence", severity: "HIGH", step: 250}]}
```

Detects: NaN loss, sudden spike, plateau >N steps, potential data leak pattern.
See [troubleshooting.md](troubleshooting.md) for remediation actions.

### Step 7 — Early stopping check (C1)

```
early_stopping_check(
    metrics=[{step: 100, loss: 1.82}, {step: 200, loss: 1.81}, ...],
    patience=5,
    min_delta=0.001
)
# → {decision: "continue"|"stop", reason: "..."}
```

### Step 8 — Pause/resume if needed (C2)

```
pause_resume_training(job_id="run-20260601-0932", action="pause")
# → {command: "ssh ... docker pause ...", dry_run: true}
# or {executed: true, status: "paused"}
```

---

## Go/No-Go Gate

- [ ] Training completed successfully (or early-stopped with documented reason)
- [ ] No `detect_anomalies` alerts at CRITICAL severity (or documented + approved)
- [ ] Final loss curve shows convergence (not plateau, not divergence)
- [ ] At least one checkpoint accessible (metadata via `download_checkpoint_metadata`)
- [ ] All logs passed through `sanitize_logs_for_claude` before any Claude context

---

## Log Sanitization Reflex

**Every time you receive text from the training environment**, run:
```
sanitize_logs_for_claude(text="<raw output>")
# → {sanitized: "...", masked_count: N}
```
Only pass `sanitized` to Claude. `masked_count > 0` → log the event.

---

## Common Pitfalls

See [troubleshooting.md](troubleshooting.md) for full table.

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| NaN loss at step 1 | LR too high or bad data | Lower LR 10×; check tokenizer |
| Loss plateau after 20% | LR too low or data quality | `optimize_hyperparams`; inspect synthetic data |
| OOM during real run | batch_size too large | Reduce batch; add gradient checkpointing |
| `trigger_remote_training` → dry_run | SSH creds missing | Set `FTOS_SSH_HOST` + `FTOS_SSH_KEY` |
| `detect_anomalies` finds IP in logs | Potential data leak | `scan_data_leakage_risk`; re-sanitize |
