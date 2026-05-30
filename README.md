# Fine-Tuning OS

Serveur MCP « Zero-Data » d'opérations de fine-tuning LLM (64 outils, cycle de vie complet).
Voir `docs/superpowers/specs/2026-05-29-fine-tuning-os-design.md`.

## Installation (dev)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e .[dev]

## Tests

    pytest --cov=src --cov-report=term-missing
