# ADR-0002: Modular Register Tool Pattern

**Date:** 2025-11-01
**Status:** Accepted
**Deciders:** project maintainers

---

## Context and Problem Statement

With 64+ tools spread across 10 domain modules, the server entry-point (`server.py`) must
register all tools without growing into an unmanageable monolith. Each module should be
independently testable and independently extendable.

## Decision Drivers

- `server.py` should not contain any tool business logic.
- Each module should be testable in isolation without importing the MCP runtime.
- Adding a new tool to a module should not require touching `server.py`.
- The tool count check in `tests/test_registration.py` should catch accidental deletions.

## Considered Options

- **Option A:** All tools in a single `tools.py` file, registered inline in `server.py`.
- **Option B:** One file per tool, auto-discovered by a plugin system.
- **Option C:** One file per domain module, each exposing a `register(mcp)` function and a
  `_MCP_TOOLS` list of callable module-level functions.

## Decision Outcome

**Chosen option:** Option C — `register(mcp)` + `_MCP_TOOLS` per module.

Each tool module (`prep.py`, `synthetic.py`, …) exposes:

```python
_MCP_TOOLS: list[Callable] = [function_a, function_b, ...]

def register(mcp: FastMCP) -> None:
    for fn in _MCP_TOOLS:
        mcp.tool()(fn)
```

`server.py` imports every module and calls `module.register(mcp)`. The `_MCP_TOOLS` list is
the authoritative declaration of what a module owns; `test_registration.py` sums all lists and
asserts the expected total (65 including the health tool).

### Positive Consequences

- `server.py` stays thin (<90 lines).
- Each module is independently importable and testable.
- Adding a tool only requires editing one module file.
- The total-count assertion catches accidental deletions or double-registrations.

### Negative Consequences / Trade-offs

- Discoverer must know to look at `_MCP_TOOLS` to enumerate a module's tools.
- The total count in `test_registration.py` must be updated manually when tools are added.

## Links

- `src/fine_tuning_os/server.py` — registration loop
- `tests/test_registration.py` — total count assertion
- ADR-0001 — tool taxonomy (C1/C2/C3)
