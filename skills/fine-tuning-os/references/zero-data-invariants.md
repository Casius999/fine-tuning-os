# Zero-Data Invariants — Golden Rules

> Back: [SKILL.md](../SKILL.md)

---

## Why Zero-Data

The Zero-Data architecture is the primary commercial differentiator vs.
managed fine-tuning APIs (Together, Fireworks, OpenAI FT) — those require the
client to send their data outside their infrastructure. Fine-Tuning OS trains
entirely inside the client's enclave; only sanitized metrics leave.

It also directly serves RGPD compliance: data minimization (art. 5-1-c),
security of processing (art. 32), and lawful basis for processing (art. 6).

---

## The Seven Golden Rules

### Rule 1 — Claude never sees real client data

Neither directly (via MCP tool arguments) nor indirectly (via logs that haven't
been sanitized). If a client sends a data sample "for debugging," run
`anonymize_dataset_preview` before any analysis.

**Forbidden:**
```python
# NEVER do this
result = compute_metrics(preds=real_client_predictions, refs=real_client_labels)
```

**Correct:**
```
anonymize_dataset_preview(file_path="/tmp/client_debug.jsonl")
# then work only with the .anon copy
```

### Rule 2 — Trained weights never leave the enclave in cleartext

The merged, full-precision model stays in the client's enclave. If the client
transfers it to the operator for packaging:
- It must travel over an encrypted channel (SFTP with key auth)
- It must be immediately encrypted with `encrypt_deliverable` (AES-256-GCM)
- The cleartext weight file must be purged from operator storage after encryption
- Document purge in `generate_destruction_certificate`

### Rule 3 — Sanitize before every Claude context insertion

Any text that came from an external process (SSH output, Docker logs, eval
output, error traces) **must** pass through `sanitize_logs_for_claude` before
inclusion in a Claude message or tool call argument.

```
sanitize_logs_for_claude(text=raw_ssh_output)
# Use only the 'sanitized' field in subsequent tool calls
```

This is not optional. It is a non-negotiable reflex.

### Rule 4 — Secrets only via environment variables

Never write `FTOS_SSH_KEY`, `FTOS_REGISTRY_TOKEN`, `HF_TOKEN`, or any other
secret to:
- `project.json` or any project file
- Log files or event entries
- Report content or document bodies
- Tool call arguments (except as `${ENV_VAR}` placeholders in commands)

The `dry_run` command strings use placeholder names (e.g., `$FTOS_SSH_KEY`),
never the actual value.

### Rule 5 — C2 dry_run is not failure — it is the correct contract

When a C2 tool returns `meta.dry_run=true`, this means:
- The target is not configured (no env vars) → **this is expected and correct**
- The command returned is exact and runnable — present it to the operator or client
- Never simulate success with fabricated output
- Never attempt to "work around" dry_run by calling the tool differently

```python
# C2 response shape when not configured:
{
  "success": true,
  "data": {"command": "docker push registry.client.com/acme-ft-001:latest"},
  "meta": {"executed": false, "dry_run": true}
}
```

### Rule 6 — Schema validation inspects structure, not values

`validate_data_schema` checks keys, dtypes, and lengths only. It never reads
string values. If you need to verify data content (e.g., check for empty strings),
use `anonymize_dataset_preview` first to mask the content, then analyze the
masked version.

### Rule 7 — Destruction is irrevocable and documented

When the project ends:
1. Delete all operator-side copies of: synthetic data, logs, intermediate
   checkpoints, any client-provided samples
2. Purge Docker volumes and workspace directory
3. Issue `generate_destruction_certificate` with:
   - Exact list of deleted artifacts
   - Deletion method (secure overwrite/shred)
   - Date and operator signature
4. Log with `log_project_event` type `DESTRUCTION_CERTIFIED`

---

## Class Contracts

### C1 — CODEGEN / PURE

**Contract:** 100% offline. No network calls. No file reads outside the
project workspace (no absolute paths to client directories). Deterministic
given the same inputs and seed. Can be tested in a fully air-gapped environment.

**Operator promise:** If `audit_code_no_network` (C3) passes, this class makes
no network calls.

**Examples:** `create_training_config`, `generate_synthetic_dataset`,
`compute_metrics`, `generate_contract`, `encrypt_deliverable`.

### C2 — EMIT / INGEST

**Contract:** Always produces the exact runnable command in `data.command`.
Executes live if and only if the required env var target is configured.
ALL external output passes through `sanitize_text` before return.
`meta.executed` and `meta.dry_run` are always present.

**The C2 gate pattern:**
```python
configured, meta = gate("ssh")  # checks FTOS_SSH_HOST + FTOS_SSH_KEY
if not configured:
    return ok({"command": cmd}, **meta).to_dict()  # dry_run=true
# else: execute and sanitize before returning
```

**Examples:** `trigger_remote_training`, `push_docker_to_registry`,
`upload_deliverable`, `send_status_update`.

### C3 — AUDIT / SECURITY

**Contract:** Analyzes artefacts produced by Fine-Tuning OS (our own code,
Dockerfiles, sanitized logs). Never touches client data. Uses static analysis
(AST parsing, regex heuristics). Always produces a structured findings report.

**Examples:** `audit_code_no_network`, `audit_dockerfile_security`,
`scan_data_leakage_risk`, `verify_model_license`, `sanitize_logs_for_claude`.

---

## Systematic `sanitize` Reflex

Every operator interaction with external output follows this pattern:

```
External process output
  ↓
sanitize_logs_for_claude(text=raw_output)
  ↓ sanitized field only
Claude context / tool argument
```

**When to apply:**
- After any C2 tool that executed (check `meta.executed=true`)
- After any SSH log retrieval
- After any Docker build/test output
- After any subprocess stdout/stderr
- When the client sends debug samples

**`masked_count > 0` in the response:** log this immediately with
`log_project_event` (event_type: `SENSITIVE_CONTENT_DETECTED`, payload:
include masked_count and source, NOT the content itself).

---

## Incident Response — Suspected Data Leak

**Trigger:** `scan_data_leakage_risk` finds risks, OR `detect_anomalies`
flags unusual log patterns, OR you notice client PII in tool output.

**Immediate actions:**

1. **STOP** all tool calls that could propagate the leak
2. `sanitize_logs_for_claude` on all recent tool outputs
3. `scan_data_leakage_risk` on all `outputs/`, `reports/`, `deliverables/`
4. `log_project_event` type `SECURITY_INCIDENT` with findings (no PII in payload)
5. Notify client within 72h if personal data may have been involved
   (RGPD art. 33 — see [legal-compliance.md](legal-compliance.md))
6. Purge all potentially contaminated files
7. Re-run security audit from scratch (Phase 6)
8. Issue updated `generate_security_report` after clean audit

**Never:** mention the incident in public channels, commit incident details to
git, or include raw leaked content in any document.
