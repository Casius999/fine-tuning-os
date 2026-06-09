# ADR-0001: Zero-Data Tool Taxonomy (C1 / C2 / C3)

**Date:** 2025-11-01
**Status:** Accepted
**Deciders:** project maintainers

---

## Context and Problem Statement

An MCP server for fine-tuning operations must integrate into Claude's context window without
leaking secrets, triggering unintended side-effects, or faking execution. The server needs a
principled classification so that hosts, tests, and contributors all share the same mental model
of which tools are safe to call in any context and which require external configuration.

## Decision Drivers

- Claude must be able to call any tool without fearing network egress or secret exfiltration.
- Tools that require external services should degrade gracefully when not configured.
- The test suite must be able to enforce network isolation and dry-run semantics automatically.
- Contributors need a clear rule for where to place a new tool.

## Considered Options

- **Option A:** Flat tool list — no classification; callers read docs to understand behaviour.
- **Option B:** Two classes — pure vs. effectful.
- **Option C:** Three classes — C1 (pure), C2 (emit/dry-run), C3 (audit/read-only).

## Decision Outcome

**Chosen option:** Option C — three classes with strict semantic contracts.

| Class | Name | Network | Secrets | Dry-run |
|-------|------|---------|---------|---------|
| C1 | Pure/Offline | Never | None | N/A |
| C2 | Emit/Ingest | Only when configured | Optional | Yes — default |
| C3 | Audit/Security | Never | None | N/A |

The class is declared in the tool docstring and enforced by `tests/test_zero_data.py` on every
CI run. C2 tools use `targets.gate(kind)` to check whether the required env var is set; if not,
they return `meta.executed=False, meta.dry_run=True` with an actionable CLI command string and
never open a socket.

### Positive Consequences

- Every tool is safe to invoke in a restricted Claude session.
- The zero-data invariant is machine-verified on every push.
- Contributors have unambiguous placement rules.

### Negative Consequences / Trade-offs

- Three-class model adds a small amount of upfront taxonomy overhead for new tools.
- C2 tools must implement the gate pattern rather than calling external services directly.

## Links

- `src/fine_tuning_os/targets.py` — gate implementation
- `tests/test_zero_data.py` — invariant enforcement
- ADR-0002 — modular register pattern
