# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> This file is maintained automatically by release automation (release-please) from
> [Conventional Commits](https://www.conventionalcommits.org/). Add entries under
> `[Unreleased]` only if editing by hand.

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.1.0] - 2026-06-09

### Added

- **64 MCP tools** across 10 domain modules covering the full LLM fine-tuning delivery lifecycle:
  - `prep` (9 tools) — training config, base model caching, data validation, schema, anonymisation, splits
  - `synthetic` (1 tool) — instruction-tuning dataset generation from schema
  - `pipeline` (7 tools) — Docker build/test, local training, metrics, hyperparameter optimisation, test generation
  - `execution` (8 tools) — remote SSH training, log streaming, metrics monitoring, anomaly detection, early stopping
  - `evaluation` (7 tools) — checkpoint metadata, synthetic/validation evaluation, BLEU/ROUGE/perplexity, baseline comparison, bias scan
  - `security` (6 tools, C3) — code/Dockerfile/data audit, license verification, security report, log sanitisation
  - `packaging` (8 tools) — LoRA merge, quantisation (GGUF/GPTQ/AWQ), inference container, AES-256 encryption, SFTP delivery, delivery note
  - `docs` (8 tools) — contract, NDA, performance report, user guide, deployment guide, RGPD destruction certificate, PDF export, document signing
  - `client` (6 tools) — onboarding, status updates, meeting scheduling, event log, approval requests, invoice generation
  - `maintenance` (4 tools) — model-rot detection, retraining recommendations, base-model update plan, self-update
  - `health` (1 tool) — server version, tool count, workspace status
- **Zero-Data architecture**: C1/C2/C3 classification enforced and verified by `tests/test_zero_data.py`
  - C1/C3 tools cannot open sockets (patched in test suite on every run)
  - C2 tools return `executed=False, dry_run=True` when required env vars absent
  - No secrets written to disk or returned in tool output values
  - All writes anchored under `FTOS_WORKSPACE` (path traversal rejected)
- **Companion Claude Code skill** under `skills/fine-tuning-os/` with 16 reference guides
- **Synthetic demo bundle** (`scripts/demo_bundle.py`) demonstrating all 65 tools end-to-end without network or secrets
- Full test suite: 594 tests, 2 skipped (weasyprint optional), ~93% coverage
- SOTA repository scaffolding: Apache-2.0 license, SPDX headers, CI matrix (3 OS × 4 Python versions), CodeQL, OpenSSF Scorecard, SBOM attestation, release-please automation

[Unreleased]: https://github.com/Casius999/fine-tuning-os/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Casius999/fine-tuning-os/releases/tag/v0.1.0
