#!/usr/bin/env python3
"""Fine-Tuning OS — Synthetic Demo Bundle (Proof-of-Sale Dossier).

PURPOSE
-------
This script drives a 100% SYNTHETIC, end-to-end delivery lifecycle for a
fictional client ("ACME Corp") to demonstrate the *structure* and *quality*
of deliverables produced by the Fine-Tuning OS.

IMPORTANT: This is a demonstration only.
  - No real client data is used (all data is synthetically generated).
  - No real model training is executed (the training step is a dry-run;
    FTOS_LOCAL_PYTHON is not expected to be set).
  - Metrics are computed against synthetic predictions/references.
  - The script proves deliverable STRUCTURE and toolchain correctness,
    NOT model performance.

USAGE
-----
    python scripts/demo_bundle.py

OUTPUT
------
All artifacts land under ftos-workspace/demo-project/
(gitignored — never committed).  The one-time encryption key is printed
to the console and is NOT written to any file.

REPRODUCIBILITY
---------------
Deterministic where possible (fixed seed=42). Safe to re-run: clears and
recreates the demo workspace at the start of each run.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve project root so the script can be run from anywhere.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Import tool functions directly (in-process, no MCP overhead).
# ---------------------------------------------------------------------------
from fine_tuning_os.store import Store  # noqa: E402
from fine_tuning_os.tools.client import onboard_client  # noqa: E402
from fine_tuning_os.tools.docs import (  # noqa: E402
    generate_contract,
    generate_deployment_guide,
    generate_destruction_certificate,
    generate_nda,
    generate_performance_report,
    generate_user_guide,
)
from fine_tuning_os.tools.evaluation import compare_to_baseline, compute_metrics  # noqa: E402
from fine_tuning_os.tools.packaging import (  # noqa: E402
    build_inference_container,
    encrypt_deliverable,
    generate_delivery_note,
    generate_inference_config,
)
from fine_tuning_os.tools.pipeline import run_local_synthetic_train  # noqa: E402
from fine_tuning_os.tools.prep import (  # noqa: E402
    create_training_config,
    describe_expected_data_format,
)
from fine_tuning_os.tools.security import (  # noqa: E402
    audit_code_no_network,
    audit_dockerfile_security,
    generate_security_report,
    verify_model_license,
)
from fine_tuning_os.tools.synthetic import generate_synthetic_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEMO_CLIENT = "ACME Corp"
_BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
_WORKSPACE_NAME = "ftos-workspace"
_SEED = 42

# Synthetic preds/refs for metrics computation
_SYNTHETIC_PREDS = [
    "The model outputs a helpful response.",
    "Fine-tuning improves task-specific performance.",
    "The system processes the user query correctly.",
    "Output quality depends on training data diversity.",
    "Evaluation metrics confirm model improvements.",
]
_SYNTHETIC_REFS = [
    "The model produces a helpful and accurate response.",
    "Fine-tuning significantly improves task-specific performance.",
    "The system correctly processes and responds to user queries.",
    "Output quality is strongly influenced by training data diversity.",
    "Evaluation metrics clearly confirm the model improvements achieved.",
]
_BASELINE_PREDS = [
    "The model gives an answer.",
    "Training can improve performance.",
    "The system handles input.",
    "Quality depends on data.",
    "Metrics show results.",
]

# A minimal synthetic Python snippet to audit (no real network calls)
_SYNTHETIC_SNIPPET = '''\
#!/usr/bin/env python3
"""Synthetic training stub — demo only, no real training."""
import json
from pathlib import Path


def load_dataset(path: str) -> list[dict]:
    data = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def train_loop(dataset: list[dict], steps: int = 10) -> dict:
    """Simulate a training loop — synthetic only."""
    losses = [1.0 / (i + 1) for i in range(steps)]
    return {"final_loss": losses[-1], "steps": steps, "step_history": losses}


if __name__ == "__main__":
    ds = load_dataset("data/synthetic/dataset.jsonl")
    result = train_loop(ds)
    print(json.dumps(result))
'''


# ---------------------------------------------------------------------------
# Step logger
# ---------------------------------------------------------------------------
class _StepLog:
    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []

    def log(self, step: str, result: dict[str, Any], label: str = "") -> None:
        success = result.get("success", False)
        dry = result.get("meta", {}).get("dry_run", False) if success else False
        status = "DRY_RUN" if dry else ("OK" if success else "WARN")
        note = ""
        if not success:
            note = f" [{result.get('error', 'unknown error')}]"
        tag = f"  [{label}]" if label else ""
        print(f"  {status:8s}  {step}{tag}{note}")
        self._steps.append(
            {
                "step": step,
                "success": success,
                "dry_run": dry,
                "error": result.get("error") if not success else None,
            }
        )

    @property
    def warnings(self) -> list[str]:
        return [f"{s['step']}: {s['error']}" for s in self._steps if not s["success"]]

    @property
    def all_ok(self) -> bool:
        return all(s["success"] for s in self._steps)


# ---------------------------------------------------------------------------
# Main demo function
# ---------------------------------------------------------------------------
def build_demo(workspace: Path) -> dict[str, Any]:
    """Run the full synthetic delivery lifecycle.

    Parameters
    ----------
    workspace:
        Root directory for the demo workspace.  Will be cleared and recreated.

    Returns
    -------
    dict with keys: project_id, deliverables_dir, key_hex, warnings, steps
    """
    log = _StepLog()

    # --- 0. Clear and prepare workspace ---
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    store = Store(root=workspace)

    print("\n" + "=" * 60)
    print(" Fine-Tuning OS — SYNTHETIC Demo Bundle")
    print(" 100% synthetic data — no real client, no real training")
    print("=" * 60 + "\n")

    # --- 1. Onboard client ---
    print("[Step 1] Onboarding client ...")
    r = onboard_client(
        company=_DEMO_CLIENT,
        needs="Customer-support chatbot fine-tuned on internal FAQ",
        contact_email="contact@acme-corp.example.com",
        base_model=_BASE_MODEL,
        store=store,
    )
    log.log("onboard_client", r)
    if not r["success"]:
        print(f"\nFATAL: onboard_client failed: {r.get('error')}")
        return {"success": False, "error": r.get("error")}
    project_id: str = r["data"]["project_id"]
    print(f"  project_id = {project_id}")

    # --- 2. Describe data schema ---
    print("\n[Step 2] Describing data schema ...")
    r = describe_expected_data_format(
        project_id=project_id,
        columns=[
            {"name": "instruction", "dtype": "str"},
            {"name": "input", "dtype": "str"},
            {"name": "output", "dtype": "str"},
        ],
        task_type="instruct",
        store=store,
    )
    log.log("describe_expected_data_format", r)

    # --- 3. Generate synthetic dataset ---
    print("\n[Step 3] Generating synthetic dataset (n=30, seed=42) ...")
    r = generate_synthetic_dataset(
        project_id=project_id,
        n=30,
        seed=_SEED,
        store=store,
    )
    log.log("generate_synthetic_dataset", r)

    # --- 4. Create training config ---
    print("\n[Step 4] Creating training config (Qwen2.5-7B, LoRA rank=16) ...")
    r = create_training_config(
        project_id=project_id,
        base_model=_BASE_MODEL,
        framework="unsloth",
        lora_rank=16,
        lr=2e-4,
        batch_size=2,
        epochs=1,
        scheduler="cosine",
        max_seq_len=2048,
        store=store,
    )
    log.log("create_training_config", r)

    # --- 5. Run local synthetic train (dry-run expected) ---
    print("\n[Step 5] Running local synthetic train (dry-run expected) ...")
    r = run_local_synthetic_train(
        project_id=project_id,
        steps=10,
        store=store,
    )
    log.log("run_local_synthetic_train", r, label="dry_run=expected")
    train_command = r["data"].get("command", "") if r["success"] else "[unavailable]"

    # --- 6. Compute metrics & baseline comparison ---
    print("\n[Step 6] Computing metrics ...")
    r_ft = compute_metrics(
        preds=_SYNTHETIC_PREDS,
        refs=_SYNTHETIC_REFS,
        task="generation",
    )
    log.log("compute_metrics (fine-tuned)", r_ft)

    r_base = compute_metrics(
        preds=_BASELINE_PREDS,
        refs=_SYNTHETIC_REFS,
        task="generation",
    )
    log.log("compute_metrics (baseline)", r_base)

    ft_metrics = r_ft["data"]["metrics"] if r_ft["success"] else {}
    base_metrics = r_base["data"]["metrics"] if r_base["success"] else {}

    r_cmp: dict[str, Any] = {"success": False, "data": {}}
    if ft_metrics and base_metrics:
        r_cmp = compare_to_baseline(
            metrics_ft=ft_metrics,
            metrics_base=base_metrics,
        )
        log.log("compare_to_baseline", r_cmp)

    # --- 7. Security audits ---
    print("\n[Step 7] Security audits ...")

    # 7a. Audit the synthetic training snippet
    r_code = audit_code_no_network(source=_SYNTHETIC_SNIPPET)
    log.log("audit_code_no_network", r_code)

    # 7b. Build inference container (dry-run) then audit its Dockerfile
    r_infer = build_inference_container(
        model_path="outputs/merged-model",
        engine="vllm",
        project_id=project_id,
        store=store,
    )
    log.log("build_inference_container", r_infer, label="dry_run=expected")

    dockerfile_path = r_infer["data"].get("dockerfile_path") if r_infer["success"] else None
    r_df: dict[str, Any] = {"success": False, "data": {}, "error": "dockerfile not built"}
    if dockerfile_path and Path(dockerfile_path).exists():
        r_df = audit_dockerfile_security(dockerfile_path=dockerfile_path)
        log.log("audit_dockerfile_security", r_df)
    else:
        print("  SKIP     audit_dockerfile_security  [dockerfile not present]")

    # 7c. Verify model license
    r_lic = verify_model_license(repo_id=_BASE_MODEL)
    log.log("verify_model_license", r_lic)

    # 7d. Generate security report
    security_findings: dict[str, Any] = {
        "code_audit": r_code["data"] if r_code["success"] else {},
        "dockerfile_audit": r_df["data"] if r_df["success"] else {},
        "license": r_lic["data"] if r_lic["success"] else {},
    }
    r_sec = generate_security_report(
        project_id=project_id,
        findings=security_findings,
        store=store,
    )
    log.log("generate_security_report", r_sec)

    # --- 8. Documentation ---
    print("\n[Step 8] Generating documentation ...")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    r_perf = generate_performance_report(
        project_id=project_id,
        metrics=ft_metrics or {"rouge1": 0.72, "bleu": 0.41},
        baseline=base_metrics or {"rouge1": 0.51, "bleu": 0.28},
        notes=["100% synthetic evaluation — for structural demonstration only"],
        eval_dataset="synthetic evaluation set (seed=42)",
        store=store,
    )
    log.log("generate_performance_report", r_perf)

    r_ug = generate_user_guide(
        project_id=project_id,
        base_url="http://localhost:8000",
        port=8000,
        engine="vllm",
        model_name="acme-corp-finetuned",
        store=store,
    )
    log.log("generate_user_guide", r_ug)

    r_dg = generate_deployment_guide(
        project_id=project_id,
        port=8000,
        gpu_device="all",
        api_hostname="api.acme-corp.example.com",
        store=store,
    )
    log.log("generate_deployment_guide", r_dg)

    r_contract = generate_contract(
        project_id=project_id,
        montant="15 000 EUR HT",
        clauses=(
            "Livraison du modèle fine-tuné sous licence Apache-2.0. "
            "Maintenance corrective 3 mois incluse. "
            "Confidentialité : NDA joint en annexe."
        ),
        prestataire_nom="Fine-Tuning OS SAS",
        client_nom=_DEMO_CLIENT,
        store=store,
    )
    log.log("generate_contract", r_contract)

    r_nda = generate_nda(
        project_id=project_id,
        partie_a="Fine-Tuning OS SAS",
        partie_b=_DEMO_CLIENT,
        duree="3 ans",
        objet="Fine-tuning de modèle de langage sur données propriétaires ACME",
        store=store,
    )
    log.log("generate_nda", r_nda)

    r_cert = generate_destruction_certificate(
        project_id=project_id,
        date=today,
        methode="Suppression sécurisée (DoD 5220.22-M, 7 passes) + certificat",
        signataire="CTO Fine-Tuning OS SAS",
        client_nom=_DEMO_CLIENT,
        prestataire_nom="Fine-Tuning OS SAS",
        description_donnees=(
            "Données d'entraînement synthétiques (seed=42), "
            "checkpoints intermédiaires, fichiers de configuration."
        ),
        store=store,
    )
    log.log("generate_destruction_certificate", r_cert)

    # --- 9. Inference config ---
    print("\n[Step 9] Generating inference config ...")
    r_icfg = generate_inference_config(
        port=8000,
        context_length=4096,
        max_concurrent=4,
        engine="vllm",
        api_key_env_name="ACME_API_KEY",
        project_id=project_id,
        store=store,
    )
    log.log("generate_inference_config", r_icfg)

    # --- 10. Encrypt deliverable & delivery note ---
    print("\n[Step 10] Encrypting deliverable & generating delivery note ...")

    # Collect key deliverables for encryption
    deliverables_dir = store.project_dir(project_id) / "deliverables"
    contract_path = deliverables_dir / "contract.md"
    nda_path = deliverables_dir / "nda.md"

    encrypt_paths = [p for p in [contract_path, nda_path] if p.exists()]
    if not encrypt_paths:
        # Fallback: write a placeholder
        placeholder = deliverables_dir / "demo_placeholder.txt"
        placeholder.write_text("Fine-Tuning OS Demo Deliverable\n", encoding="utf-8")
        encrypt_paths = [placeholder]

    r_enc = encrypt_deliverable(
        paths=[str(p) for p in encrypt_paths],
        output_dir=str(deliverables_dir),
    )
    log.log("encrypt_deliverable", r_enc)

    key_hex = "[NOT CAPTURED — encrypt_deliverable failed]"
    enc_sha256 = ""
    enc_path_str = ""
    if r_enc["success"]:
        key_hex = r_enc["data"]["key_hex"]
        enc_sha256 = r_enc["data"]["sha256"]
        enc_path_str = r_enc["data"]["encrypted_path"]
        print("\n  *** ONE-TIME DECRYPTION KEY (store securely, shown once) ***")
        print(f"  KEY: {key_hex}")
        print(f"  SHA256 (encrypted file): {enc_sha256}\n")

    # Build file list for delivery note
    all_files: list[dict[str, Any]] = []
    pdir = store.project_dir(project_id)
    for rel in [
        "reports/security_report.md",
        "reports/perf_report.md",
        "docs/user_guide.md",
        "docs/deployment_guide.md",
        "deliverables/contract.md",
        "deliverables/nda.md",
        "deliverables/destruction_cert.md",
    ]:
        fp = pdir / rel
        if fp.exists():
            all_files.append({"path": str(fp), "name": fp.name})
    if enc_path_str and Path(enc_path_str).exists():
        all_files.append(
            {
                "path": enc_path_str,
                "name": Path(enc_path_str).name,
                "note": (
                    f"AES-256-GCM encrypted archive. "
                    f'Decrypt with: python -c "from fine_tuning_os.crypto import decrypt_file; '
                    f"import bytes; decrypt_file('<enc_path>', '<out_path>', bytes.fromhex('<KEY>'))\" "
                    f"SHA256={enc_sha256}"
                ),
            }
        )

    r_note = generate_delivery_note(
        project_id=project_id,
        files=all_files if all_files else [{"name": "demo_placeholder.txt", "sha256": "N/A"}],
        prestataire_nom="Fine-Tuning OS SAS",
        client_nom=_DEMO_CLIENT,
        store=store,
    )
    log.log("generate_delivery_note", r_note)

    # --- Summary ---
    print("\n" + "=" * 60)
    print(" DEMO BUNDLE SUMMARY")
    print("=" * 60)
    print(f"  project_id : {project_id}")
    print(f"  workspace  : {workspace}")
    deliverables_path = pdir / "deliverables"
    print(f"  deliverables dir: {deliverables_path}")
    print()
    print("  Files produced:")
    produced: list[Path] = []
    for sub in ("deliverables", "reports", "docs", "config", "src", "data/synthetic", "docker"):
        d = pdir / sub
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    produced.append(f)
                    print(f"    {f.relative_to(pdir)}")
    print(f"\n  Total files : {len(produced)}")
    print(f"  Train cmd   : {train_command}")

    if log.warnings:
        print("\n  WARNINGS (non-fatal):")
        for w in log.warnings:
            print(f"    - {w}")
    else:
        print("\n  All steps completed successfully.")

    print("=" * 60 + "\n")

    return {
        "success": log.all_ok,
        "project_id": project_id,
        "deliverables_dir": str(deliverables_path),
        "key_hex": key_hex,
        "enc_sha256": enc_sha256,
        "warnings": log.warnings,
        "files_produced": [str(p) for p in produced],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    workspace = repo_root / _WORKSPACE_NAME

    result = build_demo(workspace)
    sys.exit(0 if result.get("success") else 1)
