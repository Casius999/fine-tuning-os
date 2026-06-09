# SPDX-License-Identifier: Apache-2.0
"""Property-based tests using Hypothesis.

Tests pure, deterministic core logic only — no I/O, no network, no subprocess.
Each suite is capped at @settings(max_examples=50) to keep CI fast.
"""

from __future__ import annotations

import string
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fine_tuning_os.crypto import decrypt_file, encrypt_file, generate_key
from fine_tuning_os.sanitize import sanitize_text
from fine_tuning_os.store import Store
from fine_tuning_os.tools.evaluation import compute_metrics

# ---------------------------------------------------------------------------
# sanitize.sanitize_text properties
# ---------------------------------------------------------------------------

# Strategies for realistic "dirty" text containing emails and IPv4s
_email_strategy = st.builds(
    lambda u, d, t: f"{u}@{d}.{t}",
    u=st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=10),
    d=st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=8),
    t=st.sampled_from(["com", "io", "org", "net", "fr"]),
)
_ipv4_strategy = st.builds(
    lambda a, b, c, d: f"{a}.{b}.{c}.{d}",
    a=st.integers(1, 254),
    b=st.integers(0, 255),
    c=st.integers(0, 255),
    d=st.integers(1, 254),
)


class TestSanitizeProperties:
    @given(
        prefix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        suffix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        email=_email_strategy,
    )
    @settings(max_examples=50)
    def test_email_does_not_appear_in_output(self, prefix: str, suffix: str, email: str) -> None:
        """After sanitization, the original email address must not appear in output."""
        text = f"{prefix} {email} {suffix}"
        out, count = sanitize_text(text)
        assert email not in out
        assert count >= 1

    @given(
        prefix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        suffix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        ip=_ipv4_strategy,
    )
    @settings(max_examples=50)
    def test_ipv4_does_not_appear_in_output(self, prefix: str, suffix: str, ip: str) -> None:
        """After sanitization, the original IPv4 address must not appear in output."""
        text = f"{prefix} {ip} {suffix}"
        out, count = sanitize_text(text)
        assert ip not in out
        assert count >= 1

    @given(
        text=st.text(
            alphabet=string.ascii_letters + string.digits + " \t\n!?,.",
            min_size=0,
            max_size=200,
        )
    )
    @settings(max_examples=50)
    def test_sanitize_clean_text_count_zero(self, text: str) -> None:
        """Sanitizing text with no sensitive patterns returns count==0."""
        out, count = sanitize_text(text)
        assert count == 0
        assert out == text

    @given(
        prefix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        email=_email_strategy,
    )
    @settings(max_examples=50)
    def test_sanitize_is_idempotent(self, prefix: str, email: str) -> None:
        """Sanitizing already-sanitized text masks nothing new (count == 0 on second pass)."""
        text = f"{prefix} {email}"
        once, _ = sanitize_text(text)
        twice, count2 = sanitize_text(once)
        assert count2 == 0
        assert twice == once


# ---------------------------------------------------------------------------
# crypto: encrypt_file -> decrypt_file round-trip
# ---------------------------------------------------------------------------


class TestCryptoRoundTrip:
    @given(payload=st.binary(min_size=0, max_size=4096))
    @settings(max_examples=50)
    def test_encrypt_decrypt_roundtrip(self, payload: bytes) -> None:
        """AES-256-GCM round-trip must recover original bytes exactly."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            key = generate_key()
            src = tmp / "plain.bin"
            enc = tmp / "enc.bin"
            dec = tmp / "dec.bin"

            src.write_bytes(payload)
            encrypt_file(src, enc, key)
            decrypt_file(enc, dec, key)
            assert dec.read_bytes() == payload

    def test_encrypt_wrong_key_length_raises(self, tmp_path: Path) -> None:
        """encrypt_file raises ValueError for a key that isn't 32 bytes."""
        src = tmp_path / "f.bin"
        src.write_bytes(b"hello")
        with pytest.raises(ValueError, match="32 bytes"):
            encrypt_file(src, tmp_path / "out.bin", b"tooshort")

    def test_decrypt_wrong_key_length_raises(self, tmp_path: Path) -> None:
        """decrypt_file raises ValueError for a key that isn't 32 bytes."""
        src = tmp_path / "f.bin"
        src.write_bytes(b"\x00" * 64)
        with pytest.raises(ValueError, match="32 bytes"):
            decrypt_file(src, tmp_path / "out.bin", b"tooshort")


# ---------------------------------------------------------------------------
# evaluation.compute_metrics: identical preds==refs => bleu==1.0, rougeL==1.0
# and all values in [0, 1]
# ---------------------------------------------------------------------------

# Token-list strategy: lists of short simple words
_word = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)
_token_list_strategy = st.lists(_word, min_size=4, max_size=12)


class TestComputeMetricsProperties:
    @given(tokens=_token_list_strategy)
    @settings(max_examples=50)
    def test_identical_preds_refs_bleu_one(self, tokens: list[str]) -> None:
        """When preds == refs for a generation task, BLEU must equal 1.0."""
        sentence = " ".join(tokens)
        result = compute_metrics([sentence], [sentence], task="generation")
        assert result["success"] is True
        bleu = result["data"]["metrics"]["bleu"]
        assert bleu == 1.0, f"Expected bleu=1.0 for identical preds/refs, got {bleu}"

    @given(tokens=_token_list_strategy)
    @settings(max_examples=50)
    def test_identical_preds_refs_rougel_one(self, tokens: list[str]) -> None:
        """When preds == refs for a generation task, rougeL must equal 1.0."""
        sentence = " ".join(tokens)
        result = compute_metrics([sentence], [sentence], task="generation")
        assert result["success"] is True
        rougel = result["data"]["metrics"]["rougeL"]
        assert rougel == 1.0, f"Expected rougeL=1.0 for identical preds/refs, got {rougel}"

    @given(
        preds=_token_list_strategy,
        refs=_token_list_strategy,
    )
    @settings(max_examples=50)
    def test_generation_metrics_in_unit_interval(self, preds: list[str], refs: list[str]) -> None:
        """All generation metrics (bleu, rouge*) must be in [0.0, 1.0]."""
        pred_str = [" ".join(preds)]
        ref_str = [" ".join(refs)]
        result = compute_metrics(pred_str, ref_str, task="generation")
        assert result["success"] is True
        metrics = result["data"]["metrics"]
        for key in ("bleu", "rouge1", "rouge2", "rougeL"):
            val = metrics[key]
            assert 0.0 <= val <= 1.0, f"{key}={val} outside [0,1]"


# ---------------------------------------------------------------------------
# store.Store: immutability and path-traversal rejection
# ---------------------------------------------------------------------------

_safe_key = st.text(alphabet=string.ascii_lowercase + "_", min_size=1, max_size=20)
_safe_value = st.one_of(st.text(min_size=0, max_size=50), st.integers(), st.booleans())


class TestStoreProperties:
    @given(key=_safe_key, value=_safe_value)
    @settings(max_examples=50)
    def test_update_project_does_not_mutate_caller_dict(self, key: str, value: object) -> None:
        """Store.update_project must not mutate the original state dict the caller holds."""
        with tempfile.TemporaryDirectory() as td:
            s = Store(root=Path(td))
            s.init_project("immut_test", "TestCo")

            original = s.read_project("immut_test")
            original_copy = dict(original)

            s.update_project("immut_test", **{key: value})

            # The dict we held before the update must be unchanged
            assert original == original_copy

    @given(
        segment=st.text(
            alphabet=string.ascii_lowercase + "-_",
            min_size=1,
            max_size=10,
        ).filter(lambda s: s not in ("", ".", ".."))
    )
    @settings(max_examples=30)
    def test_project_dir_accepts_safe_ids(self, segment: str) -> None:
        """project_dir must not raise for safe single-segment project IDs."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            s = Store(root=tmp)
            # Should not raise
            path = s.project_dir(segment)
            assert path.is_relative_to(tmp.resolve())

    def test_project_dir_rejects_dotdot_traversal(self, tmp_path: Path) -> None:
        """project_dir must raise ValueError for any ID containing '..' path segments."""
        s = Store(root=tmp_path)
        with pytest.raises(ValueError, match="escapes workspace"):
            s.project_dir("../escape")

    def test_project_dir_rejects_absolute_traversal(self, tmp_path: Path) -> None:
        """project_dir must raise ValueError for absolute path-like IDs."""
        s = Store(root=tmp_path)
        import sys

        evil = "/etc/passwd" if sys.platform != "win32" else "C:\\Windows\\system32"
        with pytest.raises(ValueError, match="escapes workspace"):
            s.project_dir(evil)
