# Phase 3 — Pipeline Construction & Test

> Tools 11-17 | Classes: C2 (11, 12, 13) + C1 (14, 15, 16, 17)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Build and validate the training pipeline using the synthetic dataset before
any real data is involved. A passing pipeline proof (Docker build clean +
10-step synthetic micro-train + metrics reasonable) is the gate to commit
the client's resources to a full training run.

---

## Inputs

- `project.json` with schema and training config
- Synthetic dataset from Phase 2
- Base image preference (CUDA version, framework)

## Outputs

- `docker/Dockerfile.train` + `docker/compose.yaml`
- `src/train.py` (rendered training script)
- `src/eval.py`
- `src/tests/` (unit tests)
- Micro-train metrics (loss, time/step, VRAM) or dry_run command
- Pre-flight remote config report
- Optimized hyperparameter suggestion

---

## Tool Sequence

### Step 1 — Build Docker image (C2)

```
build_docker_image(
    project_id="acme-ft-001",
    base_image="pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel",
    cache_models=True
)
# Returns: {dockerfile: "...", command: "docker build ...", dry_run: true}
# or {executed: true, image_tag: "acme-ft-001:latest"} if Docker+FTOS_LOCAL_PYTHON set
```

Always inspect the generated `Dockerfile.train` before execution. Check:
- Non-root user
- No secrets baked in
- Pinned base image digest (add manually if missing)

### Step 2 — Test Docker build (C2)

```
test_docker_build(image_tag="acme-ft-001:latest")
# → {status: "ok", output: "<sanitized build/test output>"} or dry_run
```

### Step 3 — Run local synthetic micro-train (C2)

```
run_local_synthetic_train(project_id="acme-ft-001", steps=10)
# → {command: "python train.py --steps 10 ...", dry_run: true}
# or {executed: true, metrics: {loss: 2.31, time_per_step_s: 0.8, vram_gb: 6.2}}
```

**Execution conditions:** requires `FTOS_LOCAL_PYTHON` env var pointing to a
Python with torch/unsloth, OR route through unsloth-server MCP.

### Step 4 — Retrieve local metrics (C1)

```
get_local_metrics(project_id="acme-ft-001")
# → {metrics: {loss: 2.31, time_per_step_s: 0.8, vram_gb: 6.2}}
```

### Step 5 — Remote config pre-flight (C1)

```
dry_run_remote_config(deployment_spec={
    "ssh_host": "${FTOS_SSH_HOST}",
    "image": "acme-ft-001:latest",
    "mounts": ["/data/client:/data/client:ro"],
    "gpus": "all"
})
# → {preflight: {missing: [], ok: ["ssh_host", "image", "mounts"]}}
```

Identifies missing env vars and mount points before the real execution.

### Step 6 — Optimize hyperparameters (C1)

```
optimize_hyperparams(metrics={"loss": 2.31, "time_per_step_s": 0.8, "vram_gb": 6.2})
# → {suggested_config: {lr: 1e-4, batch_size: 4, grad_accum: 4, rank: 32}, justification: "..."}
```

Use if initial loss is high or VRAM is near limit.

### Step 7 — Generate unit tests (C1)

```
generate_unit_tests(project_id="acme-ft-001", targets=["train.py", "eval.py"])
# → {files: [".../src/tests/test_train.py", ".../src/tests/test_eval.py"]}
```

These tests run inside the Docker container to verify data loading,
tokenization, and forward pass before real training.

---

## Security Pre-Flight (run in parallel with Steps 1-2)

Mandatory before committing to execution:
```
audit_code_no_network(code_path=".../src/", allowlist=["huggingface.co"])
audit_dockerfile_security(dockerfile_path=".../docker/Dockerfile.train")
```
See [06-security-audit.md](06-security-audit.md) for details.

---

## Go/No-Go Gate

- [ ] Docker build succeeds (or dry_run command verified by operator)
- [ ] `test_docker_build` reports `status: ok` (or dry_run)
- [ ] `run_local_synthetic_train` returns loss < 10 (sane initial loss on synthetic data)
- [ ] `audit_code_no_network` → 0 critical findings
- [ ] `audit_dockerfile_security` → 0 critical findings
- [ ] `generate_unit_tests` files committed
- [ ] `dry_run_remote_config` reports no missing critical env vars

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Docker build fails (missing CUDA) | `test_docker_build` output has CUDA error | Switch base image CUDA version |
| OOM on micro-train | metrics.vram_gb > available | Reduce batch_size, enable gradient checkpointing |
| Divergence on 10 steps | loss=NaN | Lower LR 10×, check tokenizer pad token |
| `FTOS_LOCAL_PYTHON` not set | All C2 return `dry_run: true` | Set env var OR use unsloth-server |
| `audit_code_no_network` finds `requests.get` | finding `CRITICAL: network call` | Remove or wrap in allowlist |

---

## unsloth-server Routing

When `FTOS_LOCAL_PYTHON` is not set but the unsloth-server MCP is available,
`run_local_synthetic_train` can route to it (operator configures the bridge).
This is the recommended approach for operator infra with no local GPU.
See [04-execution.md](04-execution.md) and [SKILL.md](../SKILL.md) §Execution Boundary.
