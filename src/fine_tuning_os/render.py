# src/fine_tuning_os/render.py
"""Deterministic file utilities: hashing, atomic writes, Markdown rendering."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import markdown as _markdown


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text_atomic(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def markdown_to_html(md_text: str) -> str:
    return _markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def markdown_file_to_pdf(md_path: Path, pdf_path: Path) -> Path:
    """Render a Markdown file to PDF via WeasyPrint.

    Requires the optional `pdf` extra (`pip install -e .[pdf]`). Imported
    lazily so the core install stays light on Windows.
    """
    from weasyprint import HTML  # noqa: PLC0415 (lazy heavy native dep)

    html = markdown_to_html(Path(md_path).read_text(encoding="utf-8"))
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(pdf_path))
    return pdf_path
