# Fine-Tuning OS — Synthetic Demo Bundle

## What it is

The **demo bundle** is a proof-of-sale dossier: a fully reproducible script
that drives the entire Fine-Tuning OS delivery lifecycle against 100% synthetic
data and produces a complete deliverables folder in seconds.

It proves the **structure and quality** of the deliverables your prospects will
receive, without requiring a real client, real training data, or a GPU.

## How to reproduce

```bash
python scripts/demo_bundle.py
```

Output lands under `ftos-workspace/` (gitignored).

## Artifacts produced

| Artifact | Location | Description |
|---|---|---|
| `security_report.md` | `reports/` | Code audit + Dockerfile audit + model license check |
| `perf_report.md` | `reports/` | Performance metrics + baseline comparison table |
| `contract.md` | `deliverables/` | Service contract (French law: Code civil, CPI, RGPD) |
| `nda.md` | `deliverables/` | NDA (Code de commerce L151-1) |
| `destruction_cert.md` | `deliverables/` | RGPD data destruction certificate |
| `user_guide.md` | `docs/` | API endpoints, code examples, parameters |
| `deployment_guide.md` | `docs/` | IT deployment procedure |
| `training.yaml` | `config/` | Unsloth LoRA training configuration |
| `inference.json` | `config/` | Inference server config (env-var refs only) |
| `Dockerfile.infer` | `docker/` | Inference container Dockerfile |
| `train.py` | `src/` | Generated training script (dry-run) |
| `dataset.jsonl` | `data/synthetic/` | 30 synthetic training examples (seed=42) |
| `deliverables.tar.gz.enc` | `deliverables/` | AES-256-GCM encrypted deliverables archive |
| `delivery_note.md` | `deliverables/` | Delivery note with file list + SHA256 + decryption procedure |

## Encryption key

The one-time decryption key is printed to the console once and is **not**
written to any file. Copy it immediately from the terminal output.

To decrypt:

```python
from fine_tuning_os.crypto import decrypt_file
import pathlib

decrypt_file(
    pathlib.Path("deliverables.tar.gz.enc"),
    pathlib.Path("deliverables.tar.gz"),
    bytes.fromhex("<KEY_HEX_FROM_CONSOLE>"),
)
```

## Synthetic nature — what this means

- **No real client data** — all training examples are procedurally generated
  (instruction/input/output columns with placeholder values).
- **No real training** — the training step emits the exact command that _would_
  be run, but does not execute it (FTOS_LOCAL_PYTHON is not set).
- **Metrics are synthetic** — BLEU/ROUGE scores are computed on synthetic
  prediction/reference pairs to demonstrate the metrics pipeline.
- **Dates and names are fictional** — ACME Corp is a placeholder.

The demo proves the deliverable **structure** and **toolchain**; it does not
prove model performance.  Real performance is demonstrated during the actual
fine-tuning engagement.

## Showing it to a prospect

1. Run `python scripts/demo_bundle.py`.
2. Open `ftos-workspace/<project_id>/deliverables/` in your file manager.
3. Walk the prospect through each artifact to demonstrate:
   - Legal documents (contract, NDA, destruction certificate)
   - Technical reports (performance metrics, security audit)
   - Deployment documentation (user guide, deployment guide)
   - Encrypted, SHA256-verified delivery archive
4. The delivery note lists every file with its SHA256 hash and decryption
   instructions — exactly what the client receives at project close.

## Workspace location

`ftos-workspace/` is gitignored. Re-running the script clears and recreates it.
Never commit the workspace directory.
