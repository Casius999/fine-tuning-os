# tests/test_render.py
import importlib.util
from pathlib import Path

import pytest

from fine_tuning_os.render import (
    markdown_file_to_pdf,
    markdown_to_html,
    sha256_bytes,
    sha256_file,
    write_text_atomic,
)

_HAS_WEASYPRINT = importlib.util.find_spec("weasyprint") is not None


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_sha256_file_matches_bytes(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    assert sha256_file(p) == sha256_bytes(b"hello")


def test_write_text_atomic_creates_parents_and_no_tmp(tmp_path):
    target = tmp_path / "a" / "b" / "note.md"
    write_text_atomic(target, "content")
    assert target.read_text(encoding="utf-8") == "content"
    assert list((tmp_path / "a" / "b").glob("*.tmp")) == []


def test_markdown_to_html_renders_table_and_heading():
    html = markdown_to_html("# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<h1>" in html
    assert "<table>" in html


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint extra not installed")
def test_markdown_file_to_pdf_writes_pdf(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n\nbody\n", encoding="utf-8")
    pdf = tmp_path / "out" / "doc.pdf"
    markdown_file_to_pdf(md, pdf)
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
