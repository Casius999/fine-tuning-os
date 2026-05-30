# Fine-Tuning OS — Lots 2-9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. This plan is executed lot-by-lot in the current session: one feature branch per lot, fresh implementer subagent, spec-compliance review then code-quality review, fix loops, commit, merge to `master`, delete branch.

**Goal:** Complete the Fine-Tuning OS MCP server per the validated spec (`docs/superpowers/specs/2026-05-29-fine-tuning-os-design.md`): all 64 tools across 5 tool modules, Jinja2 templates, the Zero-Data guard test, the companion skill, and a synthetic demo bundle.

**Architecture:** The Lot 1 socle is merged to `master` (envelope/sanitize/targets/store/render/crypto/server + tests, coverage 95%). Lots 2-6 add the tool modules under `src/fine_tuning_os/tools/`. To keep `server.py` small and modular (≤800 lines, cf. coding-style), **each tool module exposes `def register(mcp: FastMCP) -> None`** that defines and registers its tools; `server.py` imports every module and calls `<module>.register(mcp)` after creating `mcp`. Tools are thin: validate input (pydantic models in `models.py`) → call a pure helper → return `Result(...).to_dict()`.

**Tech Stack:** Python ≥3.10, `mcp`/FastMCP, pydantic v2, jinja2, pyyaml, paramiko, markdown(+weasyprint), cryptography. Tests: pytest + pytest-cov, black, ruff. No heavy ML libs in the server.

---

## Socle API (authoritative — implementers MUST use these, read source to confirm)

- `envelope.py`: `Result(success, data=None, error=None, meta={})` frozen, deep-copies data/meta, `.to_dict()`. Helpers `ok(data=None, **meta) -> Result`, `fail(error, **meta) -> Result`.
- `sanitize.py`: `sanitize_text(text: str) -> tuple[str, int]` → (masked_text, n_masked). Masks URL-creds, emails, IPs, long base64 blobs. **Every C2 that ingests external logs and every C3 over logs MUST route text through this.**
- `targets.py`: `resolve_target(kind) -> bool` (presence only, safe to expose). `_get_target_config(kind) -> dict[str,str]|None` (secret values — internal C2 use only, never log/return to Claude). `gate(kind) -> tuple[bool, dict]` → `(configured, {"executed":bool,"dry_run":bool})`. Kinds: `ssh, registry, sftp, smtp, slack, calendly, hf, git_remote, local_python`.
- `store.py`: `workspace_root() -> Path`; `Store(root=workspace_root())` with `project_dir(id)` (path-traversal guarded), `init_project(id, client)`, `read_project(id)`, `write_project(id, state)`, `update_project(id, **changes)` (immutable), `append_event(id, type, payload) -> event_id`. Subdirs created: config, data, synthetic, src, docker, outputs, reports, deliverables, docs.
- `render.py`: `sha256_bytes(b)`, `sha256_file(path)`, `write_text_atomic(path, text) -> Path`, `markdown_to_html(md) -> str`, `markdown_file_to_pdf(md_path, pdf_path) -> Path` (lazy weasyprint; tests skip if absent).
- `crypto.py`: `generate_key() -> bytes` (32), `encrypt_file(src, dst, key) -> Path`, `decrypt_file(src, dst, key) -> Path` (nonce(12)‖ct+tag).

## C2 contract (every C2 tool, no exceptions)

```python
configured, meta = gate(kind)            # meta = {executed, dry_run}
command = build_exact_command(...)       # always computed
if not configured:
    return ok({"command": command}, **meta, **extra).to_dict()   # dry_run=True, executed=False
# configured: perform the real action via _get_target_config(kind); sanitize ALL returned text
result = do_live_action(...)             # subprocess / paramiko / httpx / smtplib
return ok({"command": command, ...sanitized_result}, **meta).to_dict()
```
**Never fake success.** `meta.command` is always present. Live output is sanitized before returning.

## Conventions (all lots)

- One test file per tool module: `tests/test_<module>.py`. Each tool: nominal path + ≥1 error/edge case. C2 tools: assert dry_run path (no env) returns `executed=False, dry_run=True, command=<exact>` with **no network**.
- TDD: write failing test → run (fail) → implement minimal → run (pass) → commit. Frequent commits.
- Type annotations on every signature. black + ruff clean (line-length 100). Coverage ≥80% maintained.
- Use the repo venv: `.venv\Scripts\python.exe` (Windows). Bash classifier may be down → use PowerShell for git/shell; run git with `git -C fine-tuning-os ...` if CWD is the parent.
- Git: identity already LOCAL (Casius999). No `Co-Authored-By`. Commit with `git -c commit.gpgsign=false commit -m "..."`. Conventional commits (feat/test/chore/docs).
- Tools persist artifacts under the project workspace via `Store`; never write secrets to disk or `project.json`.

---

## Lot 2 — `models.py` + `prep.py` (1-5) + `synthetic.py` (6-10)  [all C1]

**Files:** Create `src/fine_tuning_os/models.py` (shared pydantic DTOs: e.g. `DataSchema{columns:list[Column], task_type}`, `TrainingParams{base_model, framework, lora_rank, lr, batch_size, epochs, scheduler, max_seq_len}`, `SplitRatios`), `src/fine_tuning_os/tools/__init__.py`, `src/fine_tuning_os/tools/prep.py`, `src/fine_tuning_os/tools/synthetic.py`. Modify `server.py` (import + `register`). Create `tests/test_prep.py`, `tests/test_synthetic.py`. Add `src/fine_tuning_os/templates/configs/{unsloth.yaml.j2,axolotl.yaml.j2,custom.yaml.j2}` and `templates/train/split.py.j2`.

**Tools (spec §6 In/Out are authoritative):**
- 1 `create_training_config` C1 — render config from `TrainingParams` for unsloth|axolotl|custom via Jinja2 → write to `<project>/config/`; return path + rendered content.
- 2 `cache_base_model` C2 — emit `huggingface-cli download <repo> --revision <rev>` + expected hash; gate on `hf`. (Lot 2 may stub live exec as dry_run-only; live HF optional.)
- 3 `generate_requirements` C1 — render `requirements.txt`/`environment.yml` per framework+cuda+extras.
- 4 `create_project_structure` C1 — create project subdirs (wraps `Store.init_project`/dirs); return created dirs.
- 5 `load_project_template` C1 — instantiate a named project template (e.g. "LoRA Mistral v3") base files.
- 6 `describe_expected_data_format` C1 — persist normalized `DataSchema` into `project.json` (no real content).
- 7 `generate_synthetic_dataset` C1 — deterministic (seeded) 10-50 synthetic examples matching schema → JSONL under `data/synthetic/`.
- 8 `validate_data_schema` C1 — check a file matches schema by **keys/types/lengths only**, never reads textual values; conformity report.
- 9 `anonymize_dataset_preview` C1 — pseudonymize a debug sample via `sanitize_text`; return path + masked-entity count.
- 10 `split_dataset_config` C1 — render `split.py` from ratios/seed/stratify (client-side execution).

**Definition of done:** 10 tools registered; tests nominal+error each; deterministic synthetic gen (seed); no network; black/ruff clean; coverage ≥80%.

## Lot 3 — `pipeline.py` (11-17) + `execution.py` (18-25)

**Files:** Create `tools/pipeline.py`, `tools/execution.py`, `tests/test_pipeline.py`, `tests/test_execution.py`; templates `templates/docker/{Dockerfile.train.j2,compose.yaml.j2}`, `templates/train/{train.py.j2}`. Modify `server.py`.

**Classes:** 11 C2, 12 C2, 13 C2 (`local_python` gate; subprocess if configured), 14 C1, 15 C1, 16 C1, 17 C1; 18 C2 (`registry`), 19 C1, 20 C2 (`ssh` via paramiko), 21 C2 (`ssh`; sanitize logs), 22 C2, 23 C1, 24 C2, 25 C1. Per spec §6. All C2 follow the contract above; SSH via paramiko using `_get_target_config("ssh")`; all ingested logs through `sanitize_text`.

**Done:** 15 tools; C2 dry_run paths proven networkless; SSH/registry/subprocess live paths behind gates; coverage ≥80%.

## Lot 4 — `evaluation.py` (26-32) + `security.py` (33-38)

**Files:** `tools/evaluation.py`, `tools/security.py`, `tests/test_evaluation.py`, `tests/test_security.py`. Modify `server.py`.

**Classes:** 26 C2, 27 C1, 28 C2, 29 C1 (compute perplexity/BLEU/ROUGE/accuracy/F1 from provided preds/refs — pure), 30 C1, 31 C1 (delta table), 32 C1; 33 C3 (**AST** scan: no network calls outside allowlist), 34 C3 (Dockerfile best-practices: non-root, no secrets, pinned, no `curl|sh`), 35 C3 (`scan_data_leakage_risk` via sanitize heuristics over logs), 36 C3 (`verify_model_license` from a local license registry → commercial compatibility; seed registry from spec §14.1: Qwen/Mistral-Small Apache-2.0, DeepSeek/GLM/Phi MIT, Gemma restricted, Llama community/MAU), 37 C1 (aggregate audits → md+pdf report + SHA256), 38 C3 (`sanitize_logs_for_claude` thin wrapper over `sanitize_text`).

**Done:** 13 tools; AST audit + dockerfile audit have real findings logic; license registry covers §14.1; compute_metrics correct on known vectors; coverage ≥80%.

## Lot 5 — `packaging.py` (39-46) + `docs.py` (47-54) + Jinja2 templates + PDF

**Files:** `tools/packaging.py`, `tools/docs.py`, `tests/test_packaging.py`, `tests/test_docs.py`; templates `templates/docker/Dockerfile.infer.j2`, `templates/docs/{user_guide.md.j2,deployment_guide.md.j2,perf_report.md.j2}`, `templates/legal/{contract.md.j2,nda.md.j2,destruction_cert.md.j2,delivery_note.md.j2}`, `templates/business/{invoice.md.j2,status_update.md.j2}`. Modify `server.py`.

**Classes:** 39 C2, 40 C2, 41 C2, 42 C1, 43 C2, 44 C1 (AES-256-GCM via `crypto`; key shown once in `data`, never persisted; SHA256), 45 C2 (`sftp` via paramiko), 46 C1 (delivery note md+pdf, file list + SHA256 + decrypt procedure); 47-53 C1 (legal/docs templates; contract/nda/destruction_cert cite FR legal basis per spec §17), 54 C2 (`sign_document`: detached local signature default; e-sign API if configured). PDF via `render.markdown_file_to_pdf` (tests skip if weasyprint missing).

**Done:** 16 tools; templates render with project data; legal templates cite Code civil/CPI/RGPD/Code de commerce per §17; encrypt_deliverable round-trips (encrypt→decrypt) in tests; coverage ≥80%.

## Lot 6 — `client.py` (55-60) + `maintenance.py` (61-64)

**Files:** `tools/client.py`, `tools/maintenance.py`, `tests/test_client.py`, `tests/test_maintenance.py`. Modify `server.py`.

**Classes:** 55 C1 (`onboard_client` → creates project via Store, initial state), 56 C2 (`smtp`/`slack`: send or return ready message), 57 C2 (`calendly`), 58 C1 (`log_project_event` → events.jsonl), 59 C1 (persisted approval request, pending), 60 C1 (invoice md+pdf + SHA256); 61 C1 (`check_model_rot`: drift over metric history), 62 C1 (`suggest_retraining` from sanitized prod signals), 63 C1 (`update_base_model`: config+requirements diff), 64 C2 (`mcp_self_update` via `git_remote`).

**Done:** 10 tools; client onboarding creates a real project; events appended; invoice renders; coverage ≥80%. **After Lot 6: all 64 tools registered — assert count in test.**

## Lot 7 — `test_zero_data.py` + coverage pass + README

**Files:** Create `tests/test_zero_data.py`; update `README.md`; fill any coverage gaps.

- `test_zero_data.py`: monkeypatch `socket.socket` to raise; import server, call every C1/C3 tool with synthetic inputs → assert no socket use and success. Assert every C2 with no env returns `dry_run=True, executed=False` **without** touching the network. Assert the server registers exactly 64 tools and starts in stdio with zero env (all C2 → dry_run).
- README: install, env-var matrix (spec §8), tool catalogue summary, Zero-Data contract, run/test instructions.
- Coverage ≥80% overall; `test_zero_data.py` green; black/ruff clean.

## Lot 8 — Companion skill (`skills/fine-tuning-os/SKILL.md` + 16 references)

**Files:** Create `skills/fine-tuning-os/SKILL.md` (frontmatter `name: fine-tuning-os`, triggering `description`; body ≤~500 lines: overview, 10-phase ↔ 64-tool map, Zero-Data invariants, decision tree, links to refs) and `references/{01-preparation … 10-maintenance}.md` (phase↔tools, checklists, command/tool examples), plus `zero-data-invariants.md`, `legal-compliance.md` (≡ spec §17), `sota-may-2026.md` (≡ §14), `pricing-packaging.md` (≡ §15), `checklists.md` (go/no-go gates per phase), `troubleshooting.md` (symptom→cause→tool table). Per spec §13.

**Done:** SKILL.md valid frontmatter, every cited tool exists in §6, every phase maps its tools, refs synchronized with §14/§15/§17, no dead links; validate with `everything-claude-code:skill-health` (or skill-create) if available.

## Lot 9 — Synthetic demo bundle (proof-of-sale)

**Files:** Create a reproducible recipe `scripts/demo_bundle.py` (or documented sequence) + doc `docs/demo-bundle.md`. Output under `ftos-workspace/demo-project/deliverables/` (gitignored).

- 100% synthetic end-to-end (spec §11 #6 flow): `onboard_client` → `describe_expected_data_format` → `generate_synthetic_dataset` → `create_training_config` → `run_local_synthetic_train` (or emit) → `compute_metrics` → `generate_security_report` → `encrypt_deliverable` → `generate_delivery_note`, plus performance report (baseline compare), contract/NDA, destruction certificate, user/deployment guides.
- **Done:** running the recipe produces a showable deliverables folder (md+pdf + encrypted archive + SHA256 + decrypt procedure), reproducible; documented.

---

## Self-review notes

- Spec coverage: Lots 2-6 cover tools 1-64 (5 modules); Lot 7 covers §10/§11 #1-5; Lot 8 covers §13; Lot 9 covers §11 #6,#8. All §6 tools mapped to a lot.
- Type consistency: tool names match §6 exactly; socle signatures match merged Lot 1 source.
- No placeholders: per-tool In/Out live in spec §6 (authoritative, provided inline to each implementer); architecture (register pattern, C2 contract) fixed above.
