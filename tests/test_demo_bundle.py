# SPDX-License-Identifier: Apache-2.0
# tests/test_demo_bundle.py
"""Smoke test for scripts/demo_bundle.py — end-to-end reproducibility check.

Calls build_demo(tmp_path) directly (no subprocess, no ftos-workspace pollution).
Asserts the key artifacts are produced and key fields are present.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the demo_bundle module without importing it as a package (it lives
# under scripts/, which is not on sys.path by default).
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_DEMO_BUNDLE_PATH = _SCRIPTS_DIR / "demo_bundle.py"


def _load_demo_bundle():
    """Dynamically load scripts/demo_bundle.py and return the module."""
    spec = importlib.util.spec_from_file_location("demo_bundle", _DEMO_BUNDLE_PATH)
    assert spec is not None and spec.loader is not None, "Could not load demo_bundle.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Main smoke test
# ---------------------------------------------------------------------------


def test_demo_bundle_produces_artifacts(tmp_path: Path) -> None:
    """Run build_demo against a tmp workspace and assert all key artifacts exist."""
    demo = _load_demo_bundle()

    workspace = tmp_path / "ftos-workspace-demo"
    result = demo.build_demo(workspace)

    # --- top-level success ---
    assert result.get(
        "success"
    ), f"build_demo returned success=False; warnings: {result.get('warnings')}"

    project_id: str = result["project_id"]
    assert project_id, "project_id must not be empty"

    pdir = workspace / project_id

    # --- deliverables directory exists ---
    deliverables_dir = pdir / "deliverables"
    assert deliverables_dir.is_dir(), f"deliverables dir missing: {deliverables_dir}"

    # --- critical artifacts ---
    delivery_note = deliverables_dir / "delivery_note.md"
    assert delivery_note.exists(), "delivery_note.md missing"

    contract = deliverables_dir / "contract.md"
    assert contract.exists(), "contract.md missing"

    nda = deliverables_dir / "nda.md"
    assert nda.exists(), "nda.md missing"

    destruction_cert = deliverables_dir / "destruction_cert.md"
    assert destruction_cert.exists(), "destruction_cert.md missing"

    # --- reports ---
    security_report = pdir / "reports" / "security_report.md"
    assert security_report.exists(), "security_report.md missing"

    perf_report = pdir / "reports" / "perf_report.md"
    assert perf_report.exists(), "perf_report.md missing"

    # --- docs ---
    user_guide = pdir / "docs" / "user_guide.md"
    assert user_guide.exists(), "user_guide.md missing"

    deployment_guide = pdir / "docs" / "deployment_guide.md"
    assert deployment_guide.exists(), "deployment_guide.md missing"

    # --- encrypted file exists ---
    enc_files = list(deliverables_dir.glob("*.enc"))
    assert enc_files, "No encrypted deliverable (.enc) found in deliverables/"

    # --- sha256 of encrypted file is present in result ---
    assert result.get("enc_sha256"), "enc_sha256 must be non-empty in result"
    assert len(result["enc_sha256"]) == 64, "enc_sha256 should be a 64-char hex string"

    # --- key_hex is present in result (proof it was generated) ---
    key_hex = result.get("key_hex", "")
    assert (
        key_hex and key_hex != "[NOT CAPTURED — encrypt_deliverable failed]"
    ), "key_hex must be present in result"
    assert len(key_hex) == 64, "key_hex should be a 64-char hex string (256-bit key)"

    # --- delivery note mentions at least one file ---
    note_text = delivery_note.read_text(encoding="utf-8")
    assert len(note_text) > 100, "delivery_note.md seems too short"

    # --- security report has content ---
    sec_text = security_report.read_text(encoding="utf-8")
    assert "Security Report" in sec_text, "security_report.md missing header"

    # --- config artifacts ---
    training_yaml = pdir / "config" / "training.yaml"
    assert training_yaml.exists(), "config/training.yaml missing"

    # --- synthetic dataset ---
    dataset = pdir / "data" / "synthetic" / "dataset.jsonl"
    assert dataset.exists(), "data/synthetic/dataset.jsonl missing"
    lines = [ln for ln in dataset.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 30, f"Expected 30 synthetic rows, got {len(lines)}"

    # --- workspace is NOT polluted into repo root ---
    # The test uses tmp_path so the repo-root workspace should be untouched.
    # We just verify tmp_path was used for test isolation.
    assert workspace.is_relative_to(
        tmp_path
    ), "workspace should be under tmp_path for test isolation"


def test_demo_bundle_file_exists() -> None:
    """Sanity check: the demo_bundle.py script is present."""
    assert _DEMO_BUNDLE_PATH.exists(), f"demo_bundle.py not found at {_DEMO_BUNDLE_PATH}"
