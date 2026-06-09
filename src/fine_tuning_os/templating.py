# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/templating.py
"""Shared Jinja2 environment for rendering YAML/Python/text templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def render_template(rel_path: str, /, **context: object) -> str:
    """Render a Jinja2 template (path relative to the templates/ dir)."""
    return _env.get_template(rel_path).render(**context)
