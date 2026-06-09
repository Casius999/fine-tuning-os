<div align="center">

# fine-tuning-os

**Zero-Data fine-tuning operations MCP server — 64 tools for the full LLM fine-tuning delivery lifecycle, callable by Claude Code**

[![CI](https://github.com/Casius999/fine-tuning-os/actions/workflows/ci.yml/badge.svg)](https://github.com/Casius999/fine-tuning-os/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Casius999/fine-tuning-os/actions/workflows/codeql.yml/badge.svg)](https://github.com/Casius999/fine-tuning-os/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Casius999/fine-tuning-os/badge)](https://scorecard.dev/viewer/?uri=github.com/Casius999/fine-tuning-os)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A595%25-brightgreen?style=flat-square)](https://github.com/Casius999/fine-tuning-os/actions/workflows/ci.yml)

</div>

## Table of Contents

- [Overview](#overview)
- [Zero-Data Contract](#zero-data-contract)
- [Architecture](#architecture)
- [Install](#install)
- [Run](#run)
- [Configuration](#configuration)
- [Tool Catalogue](#tool-catalogue)
- [Testing](#testing)
- [Security Notes](#security-notes)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**fine-tuning-os** is a zero-dependency-on-secrets MCP server that exposes 64 domain tools (+ 1 health tool) for the entire LLM fine-tuning delivery workflow. It integrates into any MCP-compatible host — Claude Desktop, Claude Code, or a custom orchestrator — with **no mandatory secrets at boot**.

Tools that require external services (SSH, HuggingFace, SFTP, SMTP, Slack, registries) advertise their requirements via a `dry_run` response rather than failing silently or faking execution. This means you get a fully operational server and actionable CLI commands from day one, and can progressively enable live execution by setting environment variables.

---

## Zero-Data Contract

Every tool belongs to one of three classes:

| Class | Behaviour | Network | Secrets required |
|-------|-----------|---------|-----------------|
| **C1** — Pure/Offline | Generates text, configs, or analysis from local state only | Never | None |
| **C2** — Emit/Dry-run | Builds and returns an actionable command or payload; if the required env var is absent returns `meta.executed=False, meta.dry_run=True` and never fakes execution | Only when env is configured | Optional (enables live mode) |
| **C3** — Static Audit | Reads local files/config and returns a structured report | Never | None |

Guarantees enforced by `tests/test_zero_data.py` on every CI run:

1. C1 and C3 tools cannot open sockets (socket patched to raise on any attempt).
2. C2 tools with no env configured return `executed=False, dry_run=True` and open no sockets.
3. 65 tools registered at server boot with zero env vars set.
4. No file written outside the configured workspace root (`FTOS_WORKSPACE`).

---

## Architecture

```mermaid
flowchart TB
    subgraph Host["MCP Host (Claude Code / Claude Desktop)"]
        CC[Claude Code]
    end

    subgraph Server["fine-tuning-os MCP Server (stdio)"]
        S[server.py\nFastMCP + 65 tools]

        subgraph Socle["Socle / Infrastructure"]
            ST[store.py\nFilesystem abstraction]
            TG[targets.py\ngate() — env-based C2 activation]
            MD[models.py\nResponse dataclasses]
            CR[crypto.py\nAES-256 encryption]
            SN[sanitize.py\nSecret/PII stripping]
            RE[render.py\nMarkdown → PDF]
        end

        subgraph Tools["10 Tool Modules"]
            T1[prep\n9 tools]
            T2[synthetic\n1 tool]
            T3[pipeline\n7 tools]
            T4[execution\n8 tools]
            T5[evaluation\n7 tools]
            T6[security\n6 tools C3]
            T7[packaging\n8 tools]
            T8[docs\n8 tools]
            T9[client\n6 tools]
            T10[maintenance\n4 tools]
        end
    end

    subgraph Boundary["Zero-Data Boundary"]
        direction LR
        ZD["C1/C3: socket=BLOCKED\nC2: dry_run when no env\nAll writes: FTOS_WORKSPACE only"]
    end

    subgraph Enclave["Client Enclave (optional)"]
        HF[HuggingFace API]
        SSH[Remote GPU server\nSSH]
        REG[Container Registry]
        SFTP[SFTP / SMTP / Slack]
    end

    CC <-->|MCP stdio protocol| S
    S --> Socle
    S --> Tools
    Tools --> Boundary
    Boundary -.->|C2 live mode\nonly when env set| Enclave
```

The server registers all 65 tools at startup. C2 tools call `gate()` from `targets.py` to check whether the required environment variable is set; if not, they return the dry-run command without touching the network.

---

## Install

```bash
# Clone
git clone https://github.com/Casius999/fine-tuning-os.git
cd fine-tuning-os

# Create virtual environment (Python 3.10+)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# Install (dev mode with test dependencies)
pip install -e ".[dev]"
```

Optional PDF export support (requires system libraries):

```bash
pip install -e ".[pdf]"
```

---

## Run

### stdio transport (Claude Desktop / Claude Code)

```bash
python -m fine_tuning_os
# or: fine-tuning-os
```

### Claude Desktop config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "fine-tuning-os": {
      "command": "python",
      "args": ["-m", "fine_tuning_os"],
      "env": {
        "FTOS_WORKSPACE": "/path/to/your/workspace"
      }
    }
  }
}
```

---

## Configuration

All configuration is through environment variables. Setting **none** of them is valid — the server starts and all tools respond (C2 tools return dry-run commands).

| Variable | Class | Description | Default |
|----------|-------|-------------|---------|
| `FTOS_WORKSPACE` | All | Root directory for all project files | `./ftos-workspace` |
| `FTOS_LOCAL_PYTHON` | C2 | Path to Python interpreter for local training/merge/quantize | — |
| `HF_TOKEN` | C2 | Hugging Face token for `cache_base_model`, checkpoint download | — |
| `FTOS_SSH_HOST` | C2 | Remote training server hostname | — |
| `FTOS_SSH_KEY` | C2 | Path to SSH private key for remote operations | — |
| `FTOS_REGISTRY` | C2 | Container registry URL for `push_docker_to_registry` | — |
| `FTOS_REGISTRY_TOKEN` | C2 | Registry authentication token | — |
| `FTOS_SFTP_HOST` | C2 | SFTP host for `upload_deliverable` | — |
| `FTOS_SFTP_USER` | C2 | SFTP username | — |
| `FTOS_SFTP_KEY` | C2 | Path to SFTP private key | — |
| `FTOS_SMTP_HOST` | C2 | SMTP host for `send_status_update` | — |
| `FTOS_SMTP_USER` | C2 | SMTP username | — |
| `FTOS_SMTP_PASSWORD` | C2 | SMTP password | — |
| `FTOS_SLACK_WEBHOOK` | C2 | Slack incoming webhook URL for notifications | — |
| `FTOS_CALENDLY_TOKEN` | C2 | Calendly API token for `schedule_meeting` | — |
| `FTOS_GIT_REMOTE` | C2 | Git remote URL for `self_update` | — |

---

## Tool Catalogue

### prep — Data Preparation (9 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `create_training_config` | C1 | Generate a full training configuration (LoRA, hyperparams, scheduler) |
| `cache_base_model` | C2 | Emit `huggingface-cli download` command or execute if HF_TOKEN set |
| `generate_requirements` | C1 | Produce `requirements.txt` for a given framework (unsloth, trl, etc.) |
| `create_project_structure` | C1 | Scaffold a project directory tree under workspace |
| `load_project_template` | C1 | Load and render a named project template |
| `describe_expected_data_format` | C1 | Return schema documentation for a task type |
| `validate_data_schema` | C1 | Validate a dataset sample against the expected schema |
| `anonymize_dataset_preview` | C1 | Mask PII in a dataset sample for safe preview |
| `split_dataset_config` | C1 | Generate train/eval/test split configuration |

### synthetic — Synthetic Data (1 tool, C1)

| Tool | Class | Description |
|------|-------|-------------|
| `generate_synthetic_dataset` | C1 | Generate a synthetic instruction-tuning dataset from a schema |

### pipeline — Local Pipeline (7 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `build_docker_image` | C2 | Emit `docker build` command or execute if Docker configured |
| `test_docker_build` | C2 | Emit `docker run` smoke-test command |
| `run_local_synthetic_train` | C2 | Emit local training command via `FTOS_LOCAL_PYTHON` |
| `get_local_metrics` | C1 | Parse and return metrics from a local training log file |
| `dry_run_remote_config` | C1 | Validate remote training config without connecting |
| `optimize_hyperparams` | C1 | Suggest hyperparameter adjustments based on metrics |
| `generate_unit_tests` | C1 | Generate pytest unit tests for a training script |

### execution — Remote Execution (8 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `push_docker_to_registry` | C2 | Emit `docker push` command or execute if registry configured |
| `generate_deployment_command` | C1 | Build deployment command string for a given engine and host |
| `trigger_remote_training` | C2 | SSH-trigger training job or emit command if SSH not configured |
| `stream_remote_logs` | C2 | SSH-tail training logs or emit SSH command |
| `monitor_training_metrics` | C2 | SSH-poll metrics endpoint or emit monitoring command |
| `detect_anomalies` | C1 | Analyse a metrics series and flag anomalies |
| `pause_resume_training` | C2 | SSH-send pause/resume signal or emit command |
| `early_stopping_check` | C1 | Evaluate early-stopping criteria from a metrics snapshot |

### evaluation — Model Evaluation (7 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `download_checkpoint_metadata` | C2 | Fetch checkpoint metadata from remote or emit command |
| `evaluate_on_synthetic` | C1 | Run evaluation loop on synthetic dataset locally |
| `evaluate_on_validation_set` | C2 | Run evaluation on remote validation set or emit command |
| `compute_metrics` | C1 | Compute BLEU, ROUGE, and task-specific metrics |
| `generate_predictions_sample` | C1 | Generate a sample of model predictions for review |
| `compare_to_baseline` | C1 | Compare current metrics to a stored baseline |
| `bias_fairness_scan` | C1 | Run bias and fairness checks on evaluation outputs |

### security — Security Auditing (6 tools, C3)

| Tool | Class | Description |
|------|-------|-------------|
| `audit_code_no_network` | C3 | Static security scan of training code (no network) |
| `audit_dockerfile_security` | C3 | Audit a Dockerfile for security misconfigurations |
| `scan_data_leakage_risk` | C3 | Scan dataset for PII and data-leakage patterns |
| `verify_model_license` | C3 | Verify model license compatibility for commercial use |
| `generate_security_report` | C3 | Aggregate audit results into a structured security report |
| `sanitize_logs_for_claude` | C3 | Strip secrets and PII from logs before sharing with Claude |

### packaging — Model Packaging (8 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `merge_lora_weights` | C2 | Emit merge command or execute via `FTOS_LOCAL_PYTHON` |
| `quantize_model` | C2 | Emit quantization command (GGUF/GPTQ/AWQ) or execute |
| `build_inference_container` | C2 | Write Dockerfile to workspace and emit `docker build` command |
| `generate_inference_config` | C1 | Generate vLLM/SGLang/TGI inference configuration |
| `test_inference_api` | C2 | Emit curl test command or execute against live endpoint |
| `encrypt_deliverable` | C1 | Encrypt a deliverable file with AES-256 and return key hex |
| `upload_deliverable` | C2 | Emit SFTP upload command or execute if SFTP configured |
| `generate_delivery_note` | C1 | Generate a signed delivery note document |

### docs — Documentation (8 tools, C1)

| Tool | Class | Description |
|------|-------|-------------|
| `generate_contract` | C1 | Generate a service contract from project metadata |
| `generate_nda` | C1 | Generate a non-disclosure agreement |
| `generate_performance_report` | C1 | Generate a full training performance report |
| `generate_user_guide` | C1 | Generate end-user guide for a fine-tuned model |
| `generate_deployment_guide` | C1 | Generate deployment and operations guide |
| `generate_destruction_certificate` | C1 | Generate data destruction certificate (RGPD) |
| `export_document_pdf` | C1 | Render a markdown document to PDF locally |
| `sign_document` | C1 | Hash-sign a document and return verification metadata |

### client — Client Management (6 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `onboard_client` | C1 | Create client project record and onboarding checklist |
| `send_status_update` | C2 | Send status email/Slack or emit message if not configured |
| `schedule_meeting` | C2 | Create Calendly event or emit scheduling command |
| `log_project_event` | C1 | Append a timestamped event to the project log |
| `request_client_approval` | C1 | Generate an approval request document |
| `generate_invoice` | C1 | Generate a project invoice from billing metadata |

### maintenance — Maintenance (4 tools, C1/C2)

| Tool | Class | Description |
|------|-------|-------------|
| `check_model_rot` | C1 | Analyse metric drift to detect model rot |
| `suggest_retraining` | C1 | Recommend retraining schedule based on drift analysis |
| `update_base_model` | C1 | Generate update plan for a new base model version |
| `self_update` | C2 | Emit `git pull` command or execute if `FTOS_GIT_REMOTE` set |

### health (1 tool)

| Tool | Class | Description |
|------|-------|-------------|
| `ftos_health` | C1 | Return server version, tool count, and workspace status |

---

## Testing

```bash
# Full suite with coverage
pytest --cov=src/fine_tuning_os --cov-report=term-missing --cov-fail-under=90

# Zero-Data invariant tests only
pytest tests/test_zero_data.py -v

# Tool registration check (65 tools)
pytest tests/test_registration.py -v

# Run the synthetic demo bundle (no network, no secrets needed)
python scripts/demo_bundle.py
```

Coverage gate: **≥95%** (CI enforced).

Test structure (`tests/`):

```
tests/
├── conftest.py              # workspace / store / project_id fixtures
├── test_registration.py     # 65-tool registration check
├── test_zero_data.py        # Zero-Data invariants (C1/C2/C3 × network × filesystem)
├── test_prep.py
├── test_synthetic.py
├── test_pipeline.py
├── test_execution.py
├── test_evaluation.py
├── test_security.py
├── test_packaging.py        # TDD + confinement regression
├── test_docs.py
├── test_client.py
├── test_maintenance.py
├── test_error_paths.py      # error-path coverage (OSError, TemplateError, missing-project, bad-crypto)
└── test_property.py         # Hypothesis property-based tests (sanitize, crypto, metrics, Store)
```

---

## Security Notes

- **No secret on disk.** All credentials are read from environment variables at call time via `targets.py:gate()`. No secret is ever written to files or returned in tool output values.
- **Filesystem confinement.** Every tool that writes files resolves the destination through `Store.project_dir(project_id)`, anchored under `FTOS_WORKSPACE`. Writing outside is rejected with an explicit error.
- **Sanitize before returning.** Use `sanitize_logs_for_claude` to strip secrets and PII from logs before passing output to any LLM.
- **C2 dry_run is safe.** The returned `command` string contains only env var name references (e.g., `$HF_TOKEN`), never literal secret values.
- **No network for C1/C3.** Verified by the test suite on every CI run.

Found a vulnerability? See [SECURITY.md](./SECURITY.md) — report privately, do **not** open a public issue.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) and our
[Code of Conduct](./CODE_OF_CONDUCT.md). Commits follow
[Conventional Commits](https://www.conventionalcommits.org/).

---

## Legal Notice

Ce logiciel est fourni à titre d'outil d'assistance technique. Il ne constitue pas un conseil juridique, fiscal, ou professionnel. Les documents générés (contrats, NDA, factures) sont des modèles à soumettre à un professionnel qualifié avant tout usage. L'utilisateur reste seul responsable de l'usage qu'il fait des outils et des sorties produites.

---

## License

Licensed under the [Apache-2.0](./LICENSE) license. © 2026 Casius999.
