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

# Type check (advisory — passes with lenient config)
mypy src

# Full test suite with coverage
pytest --cov=src/fine_tuning_os --cov-report=term-missing --cov-fail-under=90

# Zero-Data invariant tests only
pytest tests/test_zero_data.py -v

# Tool registration check
pytest tests/test_registration.py -v
```

## Workflow

1. Fork and create a branch: `git checkout -b feat/short-description` (or `fix/...`).
2. Make your change with tests.
3. Run the full local gate (see above) before pushing.
4. Commit using **[Conventional Commits](https://www.conventionalcommits.org/)**
   (`feat:`, `fix:`, `docs:`, `chore:`, ...). This drives automated versioning and the changelog.
5. Open a pull request; fill in the PR template, including a test plan.

## Quality bar

- Tests required for new behaviour and bug fixes.
- **Coverage gate: 90%** (CI enforced). Aspiration: 95%.
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

## Reporting bugs / requesting features

Use the issue forms. For **security vulnerabilities**, do NOT open a public issue — see
[SECURITY.md](./SECURITY.md).

## License

By contributing, you agree your contributions are licensed under the project's
[Apache-2.0](./LICENSE) license.
