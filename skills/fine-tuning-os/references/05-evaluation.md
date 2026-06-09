# Phase 5 — Evaluation & Validation

> Tools 26-32 | Class: C2 (26, 28) + C1 (27, 29, 30, 31, 32)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Rigorously evaluate the fine-tuned model against the base model on both
synthetic and client-side validation data. Produce a comparison report for
client approval. All real-data evaluation runs on the client side; only
sanitized metrics return.

---

## Inputs

- Checkpoint metadata from Phase 4
- Synthetic dataset (Phase 2)
- Task type and evaluation criteria
- Baseline metrics (base model before fine-tuning)

## Outputs

- Synthetic eval metrics
- Real eval metrics (client-side, sanitized)
- `compute_metrics` results (perplexity, BLEU, ROUGE, accuracy, F1)
- Baseline comparison table
- Bias/fairness scan report
- Predictions sample (on synthetic prompts)
- Client approval request

---

## Tool Sequence

### Step 1 — Retrieve checkpoint metadata (C2)

```
download_checkpoint_metadata(
    target={"type": "ssh", "host": "${FTOS_SSH_HOST}"},
    checkpoint="/checkpoints/step-500"
)
# → {step: 500, loss: 1.42, timestamp: "2026-06-01T14:32:00Z"} or dry_run command
```

**Zero-Data:** metadata only — not the weights.

### Step 2 — Evaluate on synthetic data (C1)

```
evaluate_on_synthetic(project_id="acme-ft-001")
# → {metrics: {loss: 1.43, perplexity: 4.18}}
```

Runs `eval.py` against the synthetic JSONL using local python. Confirms the
eval harness works before spending client GPU time.

### Step 3 — Evaluate on real validation set (C2)

```
evaluate_on_validation_set(
    target={"type": "ssh", "host": "${FTOS_SSH_HOST}"},
    eval_spec={"checkpoint": "/checkpoints/step-500", "val_path": "/data/val.jsonl"}
)
# → {metrics: {loss: 1.38, accuracy: 0.87}} (client-side execution)
# or dry_run command
```

**Real data stays on client side.** Only the metrics dict returns, having been
sanitized by the enclave's eval script.

### Step 4 — Compute metrics (C1)

```
compute_metrics(
    preds=["synthetic output 0001", ...],
    refs=["synthetic ref 0001", ...],
    task="generation"
)
# → {bleu: 0.41, rouge_l: 0.55}
```

Available metrics by task:
- `generation`: BLEU, ROUGE-1/2/L
- `classification`: accuracy, F1, precision, recall
- `chat`/`instruct`: perplexity + human eval via `generate_predictions_sample`

### Step 5 — Generate prediction samples (C1)

```
generate_predictions_sample(prompts=["What is X?", "Explain Y in simple terms"])
# → {script: "...", outputs: ["..."]} (on synthetic prompts only)
```

Produces 3-5 sample model responses for human inspection. Use only non-sensitive
synthetic prompts.

### Step 6 — Compare to baseline (C1)

```
compare_to_baseline(
    metrics_ft={"bleu": 0.41, "accuracy": 0.87},
    metrics_base={"bleu": 0.28, "accuracy": 0.71}
)
# → {delta: {bleu: +0.13, accuracy: +0.16}, table: "...markdown table..."}
```

Always compare on the **same evaluation harness** (same prompts, same metrics).
The comparison table goes directly into `generate_performance_report`.

### Step 7 — Bias and fairness scan (C1)

```
bias_fairness_scan(
    prompts=["Describe [MALE_NAME] as a leader", "Describe [FEMALE_NAME] as a leader"],
    categories=["gender", "nationality"]
)
# → {report: {...}, findings: [{category: "gender", delta: 0.12, severity: "MEDIUM"}]}
```

### Step 8 — Request client approval

```
request_client_approval(
    project_id="acme-ft-001",
    question="Do you approve the evaluation metrics for v1.0 (accuracy +16%, BLEU +0.13 vs baseline)?",
    artefacts=["reports/eval_v1.md", "reports/comparison.pdf"]
)
# → {approval_id: "apr-001", status: "pending"}
```

Do **not** proceed to Phase 7 until `status: "approved"`.

---

## Go/No-Go Gate

- [ ] `download_checkpoint_metadata` succeeded (checkpoint exists)
- [ ] `evaluate_on_synthetic` metrics are sane (loss < baseline loss)
- [ ] `evaluate_on_validation_set` metrics meet agreed target (documented in contract)
- [ ] `compare_to_baseline` shows improvement or flat (no regression)
- [ ] `bias_fairness_scan` — no HIGH severity findings (or documented exceptions)
- [ ] `request_client_approval` → `status: "approved"`

---

## Evaluation Benchmarks (SOTA May 2026)

See [sota-may-2026.md](sota-may-2026.md) §14.4 for full list.

| Benchmark | Use | Tool |
|-----------|-----|------|
| Task-specific perplexity | All LM tasks | `compute_metrics` (29) |
| BLEU/ROUGE | Generation/summarization | `compute_metrics` (29) |
| Accuracy/F1 | Classification | `compute_metrics` (29) |
| MMLU-Pro | General capability | External harness; results fed to `compare_to_baseline` |
| IFEval | Instruction following | Same |
| Human sample review | Chat/instruct quality | `generate_predictions_sample` (30) |

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Eval on real data without sanitization | `masked_count` = 0 on obviously sensitive logs | Enforce enclave-side sanitization |
| Baseline metrics not recorded | `compare_to_baseline` fails | Record base model metrics at Phase 1 |
| Overfitting to synthetic | High synthetic score, low real | More diverse synthetic; check regularization |
| Client approval blocked | `status: pending` indefinitely | `schedule_meeting` (57) to review metrics live |
