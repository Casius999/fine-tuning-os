# ADR-0005: stdio Transport and Filesystem JSON Store

**Date:** 2025-11-01
**Status:** Accepted
**Deciders:** project maintainers

---

## Context and Problem Statement

The server needs a transport mechanism compatible with Claude Desktop, Claude Code, and any
MCP-capable orchestrator. It also needs persistent workspace state (projects, metadata) that
requires no external database and works out of the box on any OS.

## Decision Drivers

- The server must integrate with Claude Desktop's MCP config without running a sidecar process
  or binding a network port.
- Workspace state must persist across server restarts.
- The state store must be portable (no Postgres/Redis dependency), testable with a tmp directory,
  and safe against concurrent writes on a single machine.
- Path traversal attacks on project IDs must be rejected at the store layer.

## Considered Options

- **Option A:** HTTP/SSE transport + SQLite database.
- **Option B:** HTTP/SSE transport + filesystem JSON files.
- **Option C:** stdio transport + filesystem JSON files with atomic writes.

## Decision Outcome

**Chosen option:** Option C — stdio transport + `Store` (atomic filesystem JSON).

**Transport:** FastMCP's default stdio transport. Claude Desktop and Claude Code both support
`{"type": "stdio", "command": "...", "args": [...]}` in their MCP config. No port, no TLS, no
process manager required.

**Store:** `Store` (in `store.py`) persists each project as a JSON file under
`$FTOS_WORKSPACE/<project_id>/project.json`. Writes use `os.replace()` (atomic rename) to avoid
partial-write corruption. `project_dir(project_id)` validates that the resolved path stays under
the workspace root, rejecting `..` traversal and absolute-path IDs with a `ValueError`.

```python
class Store:
    def project_dir(self, project_id: str) -> Path:
        # raises ValueError if resolved path escapes workspace root
        ...
    def update_project(self, project_id: str, **kwargs) -> dict:
        # returns new dict; never mutates in-place
        ...
```

### Positive Consequences

- Zero network ports and zero external services required.
- Store works in any tmp directory — easy to test.
- Atomic writes prevent corrupt JSON on crash.
- Path traversal is rejected at the entry point, not in each tool.

### Negative Consequences / Trade-offs

- stdio transport ties the server to a single client session; not suitable for multi-tenant use.
- Filesystem JSON does not support concurrent writes from multiple processes; sufficient for
  single-user MCP sessions.

## Links

- `src/fine_tuning_os/store.py` — `Store` implementation
- `src/fine_tuning_os/server.py` — FastMCP instantiation with stdio transport
- ADR-0004 — Result envelope and sanitize boundary
