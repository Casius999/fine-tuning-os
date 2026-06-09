# ADR-0004: Uniform Result Envelope and Sanitize Boundary

**Date:** 2025-11-01
**Status:** Accepted
**Deciders:** project maintainers

---

## Context and Problem Statement

Every MCP tool returns a Python dict to the FastMCP runtime, which serialises it to JSON for
Claude. Without a consistent shape, each tool invents its own response structure, making Claude
prompt engineering fragile and making it impossible to write generic error-handling logic.

Additionally, tools may incorporate log fragments, subprocess output, or file content that
contains secrets (API keys, tokens) or PII (emails, IPs). These must not reach Claude's context.

## Decision Drivers

- Claude prompt logic should not branch on per-tool response shapes.
- All tools should have a single, predictable contract for success vs. failure.
- Secrets and PII in raw subprocess output must be stripped before the value enters Claude's
  context window.
- The sanitize step must be mandatory, not opt-in per tool.

## Considered Options

- **Option A:** Each tool returns an ad-hoc dict; callers adapt.
- **Option B:** Two helpers `ok(data)` / `fail(msg)` returning plain dicts.
- **Option C:** Frozen `Result` dataclass with `ok()` / `fail()` constructors plus a mandatory
  `sanitize_text()` call at the boundary of any string that entered from outside the server.

## Decision Outcome

**Chosen option:** Option C — `Result` envelope + `sanitize_text()` boundary.

```python
@dataclass(frozen=True)
class Result:
    success: bool
    data: dict | None
    error: str | None
    meta: dict

def ok(data, **meta) -> dict: ...
def fail(msg, **meta) -> dict: ...
```

`sanitize_text(text: str) -> tuple[str, int]` replaces emails, IPs, and token-shaped strings
with `[REDACTED]` and returns the count of replacements. Every tool that incorporates external
string input (subprocess stdout, file content, user-supplied values passed back in output) must
pass those strings through `sanitize_text` before embedding in the Result.

### Positive Consequences

- Claude sees a uniform `{success, data, error, meta}` shape on every call.
- Secrets and PII are stripped at a well-known, testable boundary.
- `ok()` / `fail()` helpers make tool implementations concise.
- `Result` is frozen — tools cannot mutate the envelope after construction.

### Negative Consequences / Trade-offs

- The `sanitize_text` call adds a small overhead on every external-string-containing response.
- Overly aggressive redaction patterns could redact legitimate data (e.g., hex strings that
  look like tokens). The patterns are tunable in `sanitize.py`.

## Links

- `src/fine_tuning_os/models.py` — `Result` dataclass
- `src/fine_tuning_os/sanitize.py` — `sanitize_text` implementation
- ADR-0001 — tool taxonomy (C1/C2/C3)
