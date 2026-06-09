# fine-tuning-os task runner
# Install: https://github.com/casey/just
# Usage: just <task>

# Default: list available tasks
default:
    @just --list

# Install all dev dependencies in editable mode
install:
    pip install -e ".[dev]"

# Run full test suite
test:
    pytest -q

# Run tests with coverage report (gate >=95%)
cov:
    pytest --cov=src/fine_tuning_os --cov-report=term-missing --cov-fail-under=95

# Lint with ruff
lint:
    ruff check --output-format=github .

# Format source code with black
fmt:
    black .

# Type check (advisory)
typecheck:
    mypy src

# Run opt-in mutation testing (slow — do not add to CI)
mutation:
    mutmut run

# Regenerate uv.lock from pyproject.toml
lock:
    uv lock

# Run the zero-network synthetic demo bundle (no secrets needed)
demo:
    python scripts/demo_bundle.py

# Build the wheel and sdist
build:
    python -m pip install --quiet build
    python -m build
