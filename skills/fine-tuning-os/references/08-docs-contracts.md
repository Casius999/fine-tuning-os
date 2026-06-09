# Phase 8 — Documentation & Contracts

> Tools 47-54 | Class: C1 (47, 48, 49, 50, 51, 52, 53) + C2 (54)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Generate all contractual and technical documents that formalize the engagement,
protect both parties legally, and enable the client to use and maintain the
deliverable independently. All templates are rendered from Jinja2 with project
data; they cite their legal basis and are designed to require only the client's
legal review, not custom drafting from scratch.

For the full legal framework see [legal-compliance.md](legal-compliance.md).

---

## Document Set

| Document | Tool | Template | Legal basis |
|----------|------|----------|-------------|
| Prestation contract | `generate_contract` (47) | `contract.md.j2` | Code civil art. 1101+, 1231+, CPI |
| NDA | `generate_nda` (48) | `nda.md.j2` | Secret affaires art. L151-1+ |
| Performance report | `generate_performance_report` (49) | `perf_report.md.j2` | — |
| User guide | `generate_user_guide` (50) | `user_guide.md.j2` | — |
| Deployment guide | `generate_deployment_guide` (51) | `deployment_guide.md.j2` | — |
| Destruction certificate | `generate_destruction_certificate` (52) | `destruction_cert.md.j2` | RGPD art. 17, art. 32 |
| Invoice | `generate_invoice` (60) | `invoice.md.j2` | — |

---

## Tool Sequence

### Contracts (run early — ideally before Phase 1 work starts)

#### NDA

```
generate_nda(
    parties={"operator": "FineTuning SAS", "client": "Acme Corp"},
    duration_years=3,
    jurisdiction="Paris, France"
)
# → {nda_md: ".../docs/nda_acme.md"}
```

Send for client signature before sharing any project details. Legal basis:
Code de commerce art. L151-1 (secret des affaires).

#### Prestation contract

```
generate_contract(
    project_id="acme-ft-001",
    amount_eur=28000,
    clauses={
        "payment_terms": "30% upfront, 40% post-eval, 30% post-delivery",
        "liability_cap": "total contract value",
        "data_ownership": "client retains all rights to training data and trained model",
        "non_reuse": "operator will not reuse client data for any other purpose"
    }
)
# → {contract_md: ".../docs/contract_acme.md"}
```

Key clauses (see [legal-compliance.md](legal-compliance.md)):
- Art. 1101 s. Code civil: formation, consentement, objet
- Art. 1231 s.: responsabilité + clause limitative (plafond)
- CPI: titularité du modèle fine-tuné au client après paiement complet
- RGPD art. 28: DPA (contrat de sous-traitance) si données personnelles

### Technical Documentation

#### Performance report

```
generate_performance_report(
    project_id="acme-ft-001",
    metrics={
        "ft": {"accuracy": 0.87, "bleu": 0.41},
        "base": {"accuracy": 0.71, "bleu": 0.28},
        "delta": {"accuracy": "+0.16", "bleu": "+0.13"}
    }
)
# → {report_md: ".../reports/performance_report.md", report_pdf: ".../reports/performance_report.pdf"}
```

#### User guide

```
generate_user_guide(inference_config={
    "endpoint": "http://localhost:8000/v1",
    "model": "qwen3-7b-acme",
    "auth": "Bearer ${CLIENT_API_KEY}",
    "examples": [...]
})
# → {guide_md: ".../docs/user_guide.md"}
```

Include: API reference, Python/curl examples, parameter explanations, rate
limits, error codes.

#### Deployment guide

```
generate_deployment_guide(deployment_spec={
    "container": "acme-infer:v1",
    "requirements": {"gpu": "NVIDIA A10 or better", "vram_gb": 16},
    "startup": "docker run --gpus all -p 8000:8000 acme-infer:v1",
    "healthcheck": "GET /health → {status: ok}",
    "scaling": "horizontal via load balancer"
})
# → {guide_md: ".../docs/deployment_guide.md"}
```

### Destruction Certificate (RGPD compliance)

```
generate_destruction_certificate(
    project_id="acme-ft-001",
    date="2026-06-15",
    method="secure_delete_3pass + shred on Docker volumes; workspace deleted"
)
# → {cert_md: ".../docs/destruction_cert.md", cert_pdf: ".../docs/destruction_cert.pdf", sha256: "..."}
```

**When to issue:** after confirming the client has received and verified the
deliverable AND all intermediate data (synthetic datasets, logs, checkpoints on
operator infra) has been deleted. Documents:
- What was deleted (list)
- Method (secure overwrite, shred, Docker volume purge)
- Date
- Operator signature

Legal basis: RGPD art. 17 (droit à l'effacement) + art. 32 (sécurité).

### Export to PDF and Sign

```
export_document_pdf(md_path=".../docs/contract_acme.md")
# → {pdf_path: ".../docs/contract_acme.pdf", sha256: "..."}

sign_document(doc_path=".../docs/contract_acme.pdf")
# C2: uses local key or e-sign API
# → {signature: "...", timestamp: "2026-06-01T10:00:00Z"} or dry_run command
```

`sign_document` requires an e-sign API (DocuSign, Yousign, etc.) configured via
env vars, or uses a local detached signature by default.

---

## Go/No-Go Gate

- [ ] NDA signed by both parties (before project start)
- [ ] Contract signed (before billable work)
- [ ] Performance report generated (MD + PDF)
- [ ] User guide complete (endpoint + examples)
- [ ] Deployment guide complete (startup + health + scaling)
- [ ] Destruction certificate issued (AFTER delivery confirmed)
- [ ] All PDFs SHA256-logged in `events.jsonl`

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Missing DPA | Legal review flags | Add RGPD art. 28 addendum to contract |
| PDF export fails (weasyprint) | `export_document_pdf` error | Check weasyprint install + CSS compatibility |
| Destruction cert issued too early | Cert date before delivery | Wait for client delivery confirmation |
| Sign tool dry_run | Missing e-sign credentials | Configure or use local signature |
