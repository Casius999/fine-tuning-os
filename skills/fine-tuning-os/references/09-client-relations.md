# Phase 9 — Client Relations & Project Management

> Tools 55-60 | Class: C1 (55, 58, 59, 60) + C2 (56, 57)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Maintain transparent, traceable communication throughout the project. Every
milestone, approval, and billing event is logged in `events.jsonl`. Client
approvals are formal gate artifacts. Status updates and meeting scheduling
integrate with the client's communication preferences.

---

## Workflow Overview

```
onboard_client (55)
  → creates project + initial state
  → log_project_event (58): "PROJECT_CREATED"

[per milestone]
  → send_status_update (56) [C2]
  → schedule_meeting (57) [C2] when review needed
  → request_client_approval (59) for formal gates
  → log_project_event (58): "<MILESTONE>_APPROVED"

[billing]
  → generate_invoice (60)
  → log_project_event (58): "INVOICE_ISSUED"

[closure]
  → final send_status_update (56)
  → log_project_event (58): "PROJECT_CLOSED"
```

---

## Tool Sequence

### Onboarding

```
onboard_client(
    company="Acme Corp",
    contact_name="Marie Dupont",
    contact_email="marie.dupont@acme.fr",
    use_case="Customer support chatbot for e-commerce (FR)",
    base_model="Qwen/Qwen3-7B",
    task_type="chat",
    data_volume_estimate="50k conversations",
    timeline_weeks=6
)
# → {project_id: "acme-ft-001", state: {status: "onboarding", ...}}
```

`onboard_client` creates `project.json` with all client metadata.
**Always run before any other tool.**

### Status Updates (C2)

```
send_status_update(
    project_id="acme-ft-001",
    content={
        "phase": "Pipeline & preuve synthétique",
        "status": "COMPLETE",
        "highlights": ["Docker build OK", "Synthetic micro-train: loss=2.31", "Security audit: PASS"],
        "next_steps": ["Await client data upload to enclave", "Schedule training kickoff"],
        "blockers": []
    }
)
# → {message: "<rendered markdown>", dry_run: true} or {executed: true, sent_to: "..."}
```

Configure `FTOS_SMTP_*` or `FTOS_SLACK_WEBHOOK` for real sending.

**Cadence (recommended):**

| Phase | Update trigger |
|-------|---------------|
| Phase 1 complete | Spec confirmed |
| Phase 3 complete | Pipeline proof demo |
| Phase 4 complete | Training complete |
| Phase 5 complete | Metrics for approval |
| Phase 7 complete | Delivery ready |
| Phase 8 complete | All docs + cert |

### Meeting Scheduling (C2)

```
schedule_meeting(
    duration_minutes=60,
    window={"from": "2026-06-10", "to": "2026-06-14"},
    topic="Metrics review & go/no-go for delivery"
)
# → {links: ["https://calendly.com/..."], dry_run: false} or {command: "...", dry_run: true}
```

Requires `FTOS_CALENDLY_TOKEN`.

### Event Logging (C1) — continuous

```
log_project_event(
    project_id="acme-ft-001",
    event_type="APPROVAL_RECEIVED",
    payload={"approval_id": "apr-001", "approved_by": "marie.dupont@acme.fr", "timestamp": "2026-06-05T14:00:00Z"}
)
# → {event_id: "evt-0042"}
```

**Event types to log systematically:**

| Event | When |
|-------|------|
| `PROJECT_CREATED` | onboard_client |
| `SCHEMA_DEFINED` | describe_expected_data_format |
| `PIPELINE_PROVEN` | After Phase 3 gate |
| `TRAINING_STARTED` | trigger_remote_training |
| `TRAINING_COMPLETE` | Job completed |
| `METRICS_APPROVED` | request_client_approval approved |
| `DELIVERY_SENT` | upload_deliverable confirmed |
| `INVOICE_ISSUED` | generate_invoice |
| `DESTRUCTION_CERTIFIED` | generate_destruction_certificate |
| `PROJECT_CLOSED` | Final cleanup |

### Formal Approvals (C1)

```
request_client_approval(
    project_id="acme-ft-001",
    question="Approuvez-vous les métriques de la v1.0 (accuracy +16%, BLEU +0.13 vs baseline) ?",
    artefacts=["reports/performance_report.pdf", "reports/security_report.pdf"]
)
# → {approval_id: "apr-001", status: "pending"}
```

Approval statuses: `pending` → `approved` | `rejected`.
If `rejected`: document reason in `log_project_event`, iterate on the issue,
re-request approval.

**Never proceed to the next billing milestone without `approved` status.**

### Invoicing (C1)

```
generate_invoice(
    project_id="acme-ft-001",
    lines=[
        {"description": "Cadrage & faisabilité", "amount_eur": 3000},
        {"description": "Pipeline & preuve synthétique", "amount_eur": 7000}
    ],
    payment_terms="30 jours net",
    vat_rate=0.20
)
# → {invoice_md: ".../docs/invoice_001.md", invoice_pdf: ".../docs/invoice_001.pdf", sha256: "..."}
```

Issue invoices per the milestone structure in [pricing-packaging.md](pricing-packaging.md).

---

## Go/No-Go Gate

- [ ] All formal approvals recorded (`request_client_approval` → `approved`)
- [ ] `events.jsonl` has entries for all major milestones
- [ ] Final invoice issued and SHA256 logged
- [ ] Destruction certificate issued (after delivery, before project close)
- [ ] `log_project_event` "PROJECT_CLOSED" entry present

---

## Communication Protocol

| Situation | Action | Tool |
|-----------|--------|------|
| Phase complete | Status update email/Slack | `send_status_update` |
| Metrics ready | Schedule review meeting | `schedule_meeting` |
| Client decision needed | Formal approval request | `request_client_approval` |
| Any issue or anomaly | Event log + immediate update | `log_project_event` + `send_status_update` |
| Billing milestone | Issue invoice | `generate_invoice` |
| Slow response > 3 days | Escalation | `schedule_meeting` + `send_status_update` with deadline |

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Missing `onboard_client` | Other tools fail (project not found) | Always run `onboard_client` first |
| Approvals not tracked | Billing disputes | Always `request_client_approval` before milestone invoice |
| `send_status_update` dry_run | SMTP/Slack not configured | Show rendered message to operator for manual send |
| Invoice without prior approval | Client rejects | Get approval first |
| events.jsonl gaps | Audit trail incomplete | Log every milestone immediately via `log_project_event` |
