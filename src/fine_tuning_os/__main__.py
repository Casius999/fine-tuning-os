# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/__main__.py
"""Enable `python -m fine_tuning_os` to launch the stdio MCP server.

Mirrors the `fine-tuning-os` console entry point (see pyproject.toml).
"""

from __future__ import annotations

from .server import main

if __name__ == "__main__":  # pragma: no cover
    main()
