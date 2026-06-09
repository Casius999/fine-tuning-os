# Architecture Decision Records

This directory contains the Architecture Decision Records (ADRs) for **fine-tuning-os**,
using the [MADR](https://adr.github.io/madr/) (Markdown Architectural Decision Records) format.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0000](0000-adr-template.md) | ADR template | — |
| [0001](0001-zero-data-tool-taxonomy.md) | Zero-Data Tool Taxonomy (C1 / C2 / C3) | Accepted |
| [0002](0002-modular-register-tool-pattern.md) | Modular Register Tool Pattern | Accepted |
| [0003](0003-execution-boundary-no-ml-deps.md) | Execution Boundary — No ML Dependencies in Server Process | Accepted |
| [0004](0004-result-envelope-and-sanitize-boundary.md) | Uniform Result Envelope and Sanitize Boundary | Accepted |
| [0005](0005-stdio-transport-json-store.md) | stdio Transport and Filesystem JSON Store | Accepted |

## Adding a new ADR

1. Copy `0000-adr-template.md` to the next numbered file (e.g. `0006-short-title.md`).
2. Fill in all sections. Set **Status** to `Proposed`.
3. After review, update **Status** to `Accepted` (or `Deprecated` / `Superseded by ADR-XXXX`).
4. Update this index table.
