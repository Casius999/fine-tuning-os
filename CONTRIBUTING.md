# Contributing to fine-tuning-os

Thanks for your interest in contributing! This guide explains how to get set up and submit changes.

## Code of Conduct

This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md). By participating you agree to
uphold it.

## Development setup

Python 3.10+ is required. We recommend using a virtual environment.

```bash
# Clone the repo
git clone https://github.com/Casius999/fine-tuning-os.git
cd fine-tuning-os

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
# .venv\Scripts\activate    # Windows

# Install in dev mode with all dev dependencies
pip install -e ".[dev]"

# Optional: install pre-commit hooks
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

For a fully reproducible containerised environment, open the repo in VS Code with the
Dev Container extension — `.devcontainer/devcontainer.json` configures Python 3.12 and
runs `pip install -e ".[dev]"` automatically.

## Running the local gate

```bash
# Lint
ruff check --output-format=github .

# Format check
black --check .

# Type check (strict — required CI gate)
mypy src

# Full test suite with coverage
pytest --cov=src/fine_tuning_os --cov-report=term-missing --cov-fail-under=95

# Zero-Data invariant tests only
pytest tests/test_zero_data.py -v

# Tool registration check
pytest tests/test_registration.py -v
```

If you have [just](https://github.com/casey/just) installed, the `Justfile` at repo root
provides short aliases for all of the above:

```bash
just install   # pip install -e ".[dev]"
just lint      # ruff check
just fmt       # black .
just typecheck # mypy src
just test      # pytest -q
just cov       # pytest --cov … --cov-fail-under=95
just demo      # zero-network demo bundle
just build     # wheel + sdist
```

### Property-based tests

`tests/test_property.py` uses [Hypothesis](https://hypothesis.readthedocs.io/) to exercise
`sanitize_text`, the AES-256-GCM crypto round-trip, `compute_metrics`, and `Store` with
hundreds of generated inputs. These run as part of the normal `pytest` suite. If you add a
pure, deterministic function, consider adding a `@given` test for it.

## Workflow

1. Fork and create a branch: `git checkout -b feat/short-description` (or `fix/...`).
2. Make your change with tests.
3. Run the full local gate (see above) before pushing.
4. Commit using **[Conventional Commits](https://www.conventionalcommits.org/)**
   (`feat:`, `fix:`, `docs:`, `chore:`, ...). This drives automated versioning and the changelog.
5. Open a pull request; fill in the PR template, including a test plan.

## Quality bar

- Tests required for new behaviour and bug fixes.
- **Coverage gate: 95%** (CI enforced).
- `ruff check` and `black --check` must be clean.
- No secrets, credentials, or PII in commits or history.
- Keep functions small (< 50 lines) and files focused (< 800 lines).
- Every new tool must belong to one of the three Zero-Data classes (C1, C2, C3) and be
  declared in its module's `_MCP_TOOLS` list.

## Adding a new tool

1. Place it in the appropriate module under `src/fine_tuning_os/tools/`.
2. Annotate its class (C1/C2/C3) in the docstring and via the `gate()` pattern for C2 tools.
3. Add it to `_MCP_TOOLS` and ensure `register(mcp)` picks it up.
4. Add at least one unit test in the matching `tests/test_<module>.py`.
5. Update the Tool Catalogue in `README.md`.
6. The `test_registration.py` total count check will need updating if you add tools.

## Mutation testing (opt-in)

Mutation testing is **not** part of the CI gate — it is too slow to run on every push. Run it
locally when evaluating test suite robustness.

### Current score (2026-06-10)

**Core mutation score: 100% — 13/13 killed** across `sanitize.py`, `crypto.py`,
`targets.py`, and `envelope.py`.

Mutations exercised (via `scripts/run_mutation.py`):
- Comparison operators (`!=` → `==`, `<` → `<=`, `is None` → `is not None`)
- Negation removal (`not x` → `x`)
- Integer constant off-by-one (`_NONCE_BYTES`, `_KEY_BYTES`, `_TAG_BYTES`, `bit_length`)
- AugAssign zeroing (`count += n` → `count += 0`)

All 13 mutations were killed by the existing unit/property test suite (no survivors).

### Running mutation tests

```bash
# Cross-platform runner (works on Windows; mutmut requires WSL/Linux)
python scripts/run_mutation.py

# On Linux/macOS/WSL — mutmut native
mutmut run
mutmut results
mutmut show <id>
```

Configuration lives in `[tool.mutmut]` in `pyproject.toml`:
- `paths_to_mutate = "src/fine_tuning_os/sanitize.py:src/fine_tuning_os/crypto.py:src/fine_tuning_os/targets.py:src/fine_tuning_os/envelope.py"` — core pure modules
- `tests_dir = "tests/"` — test directory
- `runner = "python -m pytest -x -q"` — fast-fail runner

A mutation score ≥ 80% is the informal bar before merging significant new modules.

## Reporting bugs / requesting features

Use the issue forms. For **security vulnerabilities**, do NOT open a public issue — see
[SECURITY.md](./SECURITY.md).

## License

By contributing, you agree your contributions are licensed under the project's
[Apache-2.0](./LICENSE) license.
