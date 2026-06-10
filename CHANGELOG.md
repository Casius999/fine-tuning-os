# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> This file is maintained automatically by release automation (release-please) from
> [Conventional Commits](https://www.conventionalcommits.org/). Add entries under
> `[Unreleased]` only if editing by hand.

## [0.2.0](https://github.com/Casius999/fine-tuning-os/compare/fine-tuning-os-v0.1.0...fine-tuning-os-v0.2.0) (2026-06-10)


### Features

* add AES-256-GCM encrypt/decrypt for deliverables ([0a594f7](https://github.com/Casius999/fine-tuning-os/commit/0a594f72903f5b78519529d1dcce2bc14d411527))
* add C2 target gating (resolve_target/gate) from env vars ([a0d5863](https://github.com/Casius999/fine-tuning-os/commit/a0d5863526e833544b34c5e84d301a4a18d873f9))
* add Dockerfile.train, compose.yaml, and train.py Jinja2 templates ([de977df](https://github.com/Casius999/fine-tuning-os/commit/de977df48bbf08777008fc53423372fae97402b7))
* add evaluation tools (26-32) with TDD tests ([4a2605a](https://github.com/Casius999/fine-tuning-os/commit/4a2605a4148d4435050a2285fa0a8d4de21f811a))
* add FastMCP bootstrap with ftos_health tool (stdio) ([0a32d85](https://github.com/Casius999/fine-tuning-os/commit/0a32d855bf4a3c93ecda7e4262f0e1c7efc6f30d))
* add Jinja2 templates for training configs and dataset split script ([fb177f1](https://github.com/Casius999/fine-tuning-os/commit/fb177f14e9714ada19443d225873c76cee7be399))
* add project Store (workspace, atomic JSON state, event log) ([2848cfb](https://github.com/Casius999/fine-tuning-os/commit/2848cfb56d0b943ed5d54fea0cd19c497fd9ba40))
* add render utils (sha256, atomic write, markdown to html/pdf) ([b8d9156](https://github.com/Casius999/fine-tuning-os/commit/b8d91562733501cf8779e1489611ea6a7c9dd300))
* add Result response envelope with ok/fail helpers ([cddf5ad](https://github.com/Casius999/fine-tuning-os/commit/cddf5ad0ae5a627a7570439963dbc74da6878047))
* add security tools (33-38) with TDD tests ([085e17d](https://github.com/Casius999/fine-tuning-os/commit/085e17dd5890ad72b5516c6d3c80b1b381423c5e))
* add shared pydantic models and jinja2 templating (Lot 2) ([0e2f67c](https://github.com/Casius999/fine-tuning-os/commit/0e2f67c73fafde46d802fab87e4050d97f654baf))
* add synthetic demo bundle (Lot 9 proof-of-sale dossier) ([aa51dd5](https://github.com/Casius999/fine-tuning-os/commit/aa51dd5d8e1de37982e54d02b44bafad9529687d))
* add Zero-Data text sanitizer (email/ip/url-cred/blob masking) ([cc258ba](https://github.com/Casius999/fine-tuning-os/commit/cc258ba23f8a5465950673be83d1755609dad727))
* implement execution tools 18-25 (C1+C2, TDD green) ([ce2db53](https://github.com/Casius999/fine-tuning-os/commit/ce2db530441d1392d2805fd48dd545a08501341d))
* implement pipeline tools 11-17 (C1+C2, TDD green) ([f2d1faa](https://github.com/Casius999/fine-tuning-os/commit/f2d1faa0642df03f0aa2651ca12b9781af282a1a))
* implement tools 1-10 in prep.py and synthetic.py (Lot 2 GREEN) ([cac14df](https://github.com/Casius999/fine-tuning-os/commit/cac14dfa18857604a4c8a52fab806733b0c47ea4))
* Lot 5 — packaging (tools 39-46) + docs (tools 47-54) + 10 Jinja2 templates ([47a7ecf](https://github.com/Casius999/fine-tuning-os/commit/47a7ecf78bb322d00e72844b1a7fa0ff335e8af5))
* **lot6:** implement tools 55-64 (client + maintenance) — GREEN ([698e0fe](https://github.com/Casius999/fine-tuning-os/commit/698e0fe6044b1c652ae3c4d4408e829fad61a492))
* mypy strict mode + dev deps for production hardening ([debaacf](https://github.com/Casius999/fine-tuning-os/commit/debaacf5b9da855e3d48d6b1b3df29838e0e191e))
* PEP 561 py.typed, wheel artifacts, CI typecheck + integration gates ([6f30cf3](https://github.com/Casius999/fine-tuning-os/commit/6f30cf3de0e9ee679e01684e496c3a9d6b3a2004))
* register pipeline and execution tools in server.py ([71c6bff](https://github.com/Casius999/fine-tuning-os/commit/71c6bff993ea484fa29347981872e0cb9cde02a6))
* **skill:** add Fine-Tuning OS companion skill (Lot 8) ([31738bf](https://github.com/Casius999/fine-tuning-os/commit/31738bff308122ca019c8b6c0eb295c6eb33e7e5))
* wire evaluation and security modules into server.py ([e6853bd](https://github.com/Casius999/fine-tuning-os/commit/e6853bd6ea750b49346824cba44f80f20c2f0c19))


### Bug Fixes

* add __main__ entry point; correct README SMTP var + pyproject tool count ([23a56ee](https://github.com/Casius999/fine-tuning-os/commit/23a56eea35c5ad174273529a28bf642478fd2b21))
* address Lot 2 code-quality review (error handling, cuda type, dead code, tests) ([1ea231a](https://github.com/Casius999/fine-tuning-os/commit/1ea231a706824245c7261d5027d94bf38adbcb8b))
* address Lot 3 code-quality review (shell-injection, early-stop boundary, ssh timeout, dry helpers, coverage) ([22a0722](https://github.com/Casius999/fine-tuning-os/commit/22a072222880cf53d0492a543746d91a281543fe))
* address Lot 4 code-quality review (audit allowlist bypass, perplexity overflow, dockerfile USER override, decomposition) ([9cd153f](https://github.com/Casius999/fine-tuning-os/commit/9cd153fe8fd6227461f2f30f5656f4e42d7fea1c))
* address Lot 5 review (sftp transport leak+timeout, decompose packaging.py &lt;800, unify pdf_skipped, black) ([6421f76](https://github.com/Casius999/fine-tuning-os/commit/6421f760eb68b88d8223cd94d89e707910d88cdd))
* address Lot 6 review (smtp timeout, http raise_for_status, assert→fail, drift zero-baseline, decompose) ([786e53a](https://github.com/Casius999/fine-tuning-os/commit/786e53a305c9bbf703fcb094d24c5f4ad7bc8aaa))
* **ci:** exclude integration tests from unit matrix; add pytest-timeout; skip flaky in-proc SSH on CI; unit-cover _ssh_exec host:port ([d032552](https://github.com/Casius999/fine-tuning-os/commit/d03255249727edf2c617384141d8daa68c688d57))
* **ci:** pin real SHAs for osv-scanner-action (v2.3.8) and upload-sarif (v3.30.0) ([2a6aada](https://github.com/Casius999/fine-tuning-os/commit/2a6aada4b9b8235d3331aba8648abeffafc19a23))
* **ci:** use official OSV-Scanner reusable workflow (v2.3.8) ([ea9e661](https://github.com/Casius999/fine-tuning-os/commit/ea9e6614edcd785f5785f8e2e47986fe5b492306))
* enforce filesystem confinement in build_inference_container ([4139274](https://github.com/Casius999/fine-tuning-os/commit/4139274b3bf442ff6f900b115e4fd3a1e2d5981d))
* harden Lot 1 socle per code-quality review ([69b2bee](https://github.com/Casius999/fine-tuning-os/commit/69b2beec9b55db07dcd4b4c3a24bf139585040ae))
* **readme:** render architecture mermaid (br tags + quoted labels); ci(release): non-blocking until PAT ([fb20981](https://github.com/Casius999/fine-tuning-os/commit/fb209814c4dea75c2f94b4117c8f70eb888d35d9))
* **security:** SMTP STARTTLS secure-by-default; SSH host:port parsing (SSH integration test now fully real, no patch) ([82cca75](https://github.com/Casius999/fine-tuning-os/commit/82cca75adb06d05af2cdddd55f3e99a4495cf5ec))


### Documentation

* add Architecture Decision Records (MADR format) ([4d66e40](https://github.com/Casius999/fine-tuning-os/commit/4d66e408d3a4f3335170d2ee62dfcd565e318c85))
* add Fine-Tuning OS design spec (64 tools, Zero-Data, companion skill, SOTA mai 2026, pricing, droit FR) ([df0f22a](https://github.com/Casius999/fine-tuning-os/commit/df0f22ad96d1529ebb197285f66dc8ebe646b500))
* add governance layer (CODEOWNERS, issue templates, PR template, CoC, contributing, ruleset) ([14436a8](https://github.com/Casius999/fine-tuning-os/commit/14436a8da18ec0911f168bf03b95385a0c009aac))
* add Lot 1 socle implementation plan (envelope/sanitize/targets/store/render/crypto/server) ([2c1ef26](https://github.com/Casius999/fine-tuning-os/commit/2c1ef26401904ac57a1893da260c7951dc97c08d))
* add Lots 2-9 implementation plan (64 tools, skill, demo bundle) ([8219e0e](https://github.com/Casius999/fine-tuning-os/commit/8219e0e361e9ca2fd241d5e7224be27097b81e8e))
* **readme:** add SVG hero banner + badges row + highlights (match quantum-ads/adk style) ([11547de](https://github.com/Casius999/fine-tuning-os/commit/11547debd1b6e1810d05dc485b8217b8d8f599ea))
* rebuild README with badges/mermaid/TOC; add CHANGELOG 0.1.0 ([8dc5158](https://github.com/Casius999/fine-tuning-os/commit/8dc51581f08688e59ba3ddb1f28fa52c096349e8))
* replace stub README with full professional documentation ([58be5a9](https://github.com/Casius999/fine-tuning-os/commit/58be5a95d1838637c4cae71791dae256ff529e19))
* update coverage gate to ≥95%, add just + Hypothesis notes ([55127c8](https://github.com/Casius999/fine-tuning-os/commit/55127c82656f2fe3bff50099b9f58941fd5c7cb3))
* use canonical Apache-2.0 license text for GitHub detection ([09ba208](https://github.com/Casius999/fine-tuning-os/commit/09ba208c79d085b05d154f0f638871a78e27e697))

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
