# ADR-0003: Execution Boundary — No ML Dependencies in Server Process

**Date:** 2025-11-01
**Status:** Accepted
**Deciders:** project maintainers

---

## Context and Problem Statement

Fine-tuning involves heavyweight ML libraries (PyTorch, Unsloth, Transformers, etc.) that
consume gigabytes of GPU memory and take seconds to import. The MCP server must start in
milliseconds, run on any Python 3.10+ host without a GPU, and not import these libraries.

## Decision Drivers

- Server cold-start must be fast (< 1 s) and work on any developer machine.
- The server process must not require CUDA, a GPU, or multi-gigabyte ML libraries.
- Training execution is a separate concern — the server emits the command string; a separate
  process (local Python, Docker, remote VM) executes it.
- The test suite must pass on CPU-only CI runners.

## Considered Options

- **Option A:** Import torch/unsloth lazily inside tool functions, fallback to dry-run if absent.
- **Option B:** Separate `fine_tuning_os_ml` package that imports ML libs; server delegates via
  subprocess or HTTP.
- **Option C:** Server is permanently ML-dep-free; training tools are C2 (emit) and return the
  exact CLI command or Docker invocation for the user/orchestrator to execute.

## Decision Outcome

**Chosen option:** Option C — the server is permanently and unconditionally ML-dep-free.

Training tools (`run_local_synthetic_train`, `build_docker_image`, `push_docker_to_registry`,
etc.) construct and return the exact shell command or Docker invocation. They never import
`torch`, `unsloth`, or any ML library. The ML dependency boundary is enforced by the absence of
those packages in `pyproject.toml` and by CI passing on standard ubuntu-24.04 runners.

### Positive Consequences

- Server installs in seconds with no GPU or ML framework required.
- CI runs on stock ubuntu/macos/windows runners with no special hardware.
- The server can orchestrate training on remote machines without managing their ML environment.

### Negative Consequences / Trade-offs

- The server cannot run local training itself — it is purely an operations layer.
- Users must separately install ML libraries in the environment where they run emitted commands.

## Links

- `pyproject.toml` — dependencies (no torch/unsloth)
- `src/fine_tuning_os/tools/pipeline.py` — training command emission
- ADR-0001 — C2 (emit/dry-run) class definition
