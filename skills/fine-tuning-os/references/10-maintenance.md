# Phase 10 — Maintenance & Model Updates

> Tools 61-64 | Class: C1 (61, 62, 63) + C2 (64)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Monitor the deployed model for performance drift, recommend retraining when
drift exceeds the SLA threshold, upgrade the base model when a superior version
becomes available, and keep the Fine-Tuning OS server itself up to date.

---

## Inputs

- Historical eval metrics from production monitoring
- Production logs (sanitized via `sanitize_logs_for_claude` before analysis)
- SLA drift threshold (agreed in contract)
- New base model version (when available)

## Outputs

- Drift verdict + magnitude
- Retraining recommendation + justification
- Updated config diff for new base model
- Server self-update result

---

## Tool Sequence

### Step 1 — Check model drift (C1)

```
check_model_rot(metrics_history=[
    {"date": "2026-03-01", "accuracy": 0.87, "bleu": 0.41},
    {"date": "2026-04-01", "accuracy": 0.85, "bleu": 0.40},
    {"date": "2026-05-01", "accuracy": 0.81, "bleu": 0.37}
])
# → {verdict: "drift_detected", magnitude: 0.06, trend: "declining", threshold_exceeded: true}
```

Run periodically — monthly at minimum, or whenever the client reports quality
degradation. Compare against the baseline metrics recorded at Phase 5.

**Drift causes:**
- Data distribution shift (user behavior changes)
- New entity types (names, products, terminology) not in training data
- Seasonal patterns the model wasn't trained on
- Underlying infrastructure changes (tokenizer updates, etc.)

### Step 2 — Suggest retraining (C1)

```
suggest_retraining(signals={
    "drift_magnitude": 0.06,
    "user_complaints": "increased since March 2026",
    "new_data_available": true,
    "new_data_estimate": "15k new examples"
})
# → {
#     recommendation: "retrain",
#     justification: "Accuracy dropped 6.9% over 3 months; new data available; LoRA update recommended",
#     suggested_approach: "LoRA rank 32, 1 epoch on new data + 20% original data mix",
#     estimated_cost: "2-4 hours A100"
# }
```

Present the recommendation to the client with the justification for the
maintenance billing (see [pricing-packaging.md](pricing-packaging.md) §SLA).

### Step 3 — Update base model (C1)

When a new version of the base model is released (e.g., Qwen3.5 → Qwen3.6):

```
update_base_model(
    project_id="acme-ft-001",
    new_repo_id="Qwen/Qwen3-7B-v2",
    new_revision="main"
)
# → {
#     config_diff: "base_model: Qwen/Qwen3-7B → Qwen/Qwen3-7B-v2\n...",
#     requirements_diff: "transformers==4.46.0 → 4.50.0\n..."
# }
```

Always re-run Phase 6 (security audit + license verification) after updating
the base model. Run a new synthetic micro-train (Phase 3) to confirm compatibility.

### Step 4 — Server self-update (C2)

```
mcp_self_update(ref="v1.2.0")
# → {command: "git fetch origin && git checkout v1.2.0 && pip install -e .", dry_run: true}
# or {executed: true, version: "1.2.0"} if FTOS_GIT_REMOTE configured
```

---

## SLA Framework

Define in the contract (see [pricing-packaging.md](pricing-packaging.md)):

| Parameter | Typical value | Tool |
|-----------|--------------|------|
| Drift check frequency | Monthly | `check_model_rot` |
| Retraining trigger threshold | 5% accuracy drop | `check_model_rot` → `suggest_retraining` |
| Response time to retraining request | 5 business days | `send_status_update` + `schedule_meeting` |
| Base model update SLA | Quarterly review | `update_base_model` |
| Server update SLA | Monthly | `mcp_self_update` |

---

## Retraining Decision Framework

```
check_model_rot (61)
  ├─ threshold_exceeded: false → log_project_event "DRIFT_CHECK_OK"
  └─ threshold_exceeded: true
       └─ suggest_retraining (62)
            ├─ recommendation: "monitor" → increase check frequency
            └─ recommendation: "retrain"
                 → send_status_update with justification
                 → request_client_approval for retraining budget
                 → if approved: restart from Phase 2 (new data schema)
                              OR Phase 3 if schema unchanged
                 → generate new invoice (maintenance billing)
```

---

## Go/No-Go Gate

- [ ] `check_model_rot` run at agreed cadence
- [ ] Drift events logged in `events.jsonl`
- [ ] Retraining recommendation shared with client (when triggered)
- [ ] Client approval for retraining budget before billable work
- [ ] Post-retraining: new security audit + performance report

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| No historical metrics | `check_model_rot` has empty history | Record baseline at Phase 5; automate monthly eval |
| Retraining on drifted base model | New issues after retrain | Run `verify_model_license` + `update_base_model` first |
| `mcp_self_update` breaks tools | Post-update failures | Always test in staging; dry_run first |
| Drift not linked to SLA | Billing dispute | Define threshold in contract at Phase 8 |
| Production logs contain PII | `scan_data_leakage_risk` finds issues | Always sanitize via `sanitize_logs_for_claude` before any analysis |
