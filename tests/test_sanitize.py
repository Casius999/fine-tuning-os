# SPDX-License-Identifier: Apache-2.0
# tests/test_sanitize.py
from fine_tuning_os.sanitize import sanitize_text


def test_masks_email():
    out, n = sanitize_text("contact jean.dupont@acme.fr now")
    assert "jean.dupont@acme.fr" not in out
    assert "[REDACTED:EMAIL]" in out
    assert n == 1


def test_masks_ipv4():
    out, n = sanitize_text("host 192.168.1.42 down")
    assert "192.168.1.42" not in out
    assert "[REDACTED:IP]" in out
    assert n == 1


def test_masks_url_with_credentials():
    out, n = sanitize_text("clone https://user:secret@git.acme.fr/repo.git")
    assert "secret" not in out
    assert "[REDACTED:URL_CRED]" in out
    assert n == 1


def test_masks_long_base64_blob():
    blob = "QUJD" * 20  # 80 base64 chars
    out, n = sanitize_text(f"weights={blob}")
    assert blob not in out
    assert "[REDACTED:BLOB]" in out
    assert n == 1


def test_masks_padded_base64_including_tail():
    blob = "QUJD" * 20 + "=="  # 80 base64 chars + padding
    out, n = sanitize_text(f"key={blob}")
    assert "==" not in out  # padding tail must be masked too
    assert "[REDACTED:BLOB]" in out
    assert n == 1


def test_clean_text_is_unchanged_and_counts_zero():
    text = "loss=0.42 step=10 vram=11GB"
    out, n = sanitize_text(text)
    assert out == text
    assert n == 0


def test_counts_multiple_masks():
    out, n = sanitize_text("a@b.cd and e@f.gh")
    assert n == 2
    assert out.count("[REDACTED:EMAIL]") == 2
