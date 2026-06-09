# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/tools/docs.py
"""Lot 5 — Documentation tools 47-54.

C1 tools (47, 48, 49, 50, 51, 52, 53): offline, deterministic, template-based.
C2 tool (54 — sign_document): local sig sidecar by default; e-sign API if configured.

Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..envelope import fail, ok
from ..render import markdown_file_to_pdf, sha256_bytes, sha256_file, write_text_atomic
from ..store import Store, workspace_root
from ..targets import gate
from ..templating import render_template

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _try_pdf(md_path: Path) -> tuple[str | None, str | None]:
    """Attempt to produce a PDF; return (pdf_path_str, error_or_skip_msg)."""
    try:
        pdf_path = md_path.with_suffix(".pdf")
        markdown_file_to_pdf(md_path, pdf_path)
        return str(pdf_path), None
    except ImportError:
        return None, "weasyprint not installed"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


# ---------------------------------------------------------------------------
# Tool 47: generate_contract (C1)
# ---------------------------------------------------------------------------


def generate_contract(
    project_id: str,
    montant: str,
    clauses: str = "",
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render contract.md.j2 (French law: Code civil, CPI, RGPD art. 28)."""
    try:
        content = render_template(
            "legal/contract.md.j2",
            project_id=project_id,
            montant=montant,
            clauses=clauses,
            prestataire_nom=prestataire_nom,
            client_nom=client_nom,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "deliverables" / "contract.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    md_sha256 = sha256_bytes(content.encode())
    result_data: dict[str, Any] = {"md_path": str(dest), "sha256": md_sha256}

    pdf_path, pdf_msg = _try_pdf(dest)
    if pdf_path:
        result_data["pdf_path"] = pdf_path
    elif pdf_msg:
        result_data["pdf_skipped"] = pdf_msg

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# Tool 48: generate_nda (C1)
# ---------------------------------------------------------------------------


def generate_nda(
    project_id: str,
    partie_a: str,
    partie_b: str,
    duree: str = "3 ans",
    juridiction: str = "Tribunal de commerce de Paris",
    objet: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render nda.md.j2 (secret des affaires — Code de commerce L151-1 s.)."""
    try:
        content = render_template(
            "legal/nda.md.j2",
            project_id=project_id,
            partie_a=partie_a,
            partie_b=partie_b,
            duree=duree,
            juridiction=juridiction,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            objet=objet,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "deliverables" / "nda.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "md_path": str(dest),
            "sha256": sha256_bytes(content.encode()),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 49: generate_performance_report (C1)
# ---------------------------------------------------------------------------


def generate_performance_report(
    project_id: str,
    metrics: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    eval_dataset: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render perf_report.md.j2 (metrics, baseline comparison, curves description)."""
    base = baseline or {}
    comparison_rows = []
    for key in sorted(set(metrics) | set(base)):
        ft_val = metrics.get(key)
        base_val = base.get(key)
        delta = None
        direction = "lower=better" if key in ("perplexity", "loss") else "higher=better"
        if ft_val is not None and base_val is not None:
            delta = round(float(ft_val) - float(base_val), 6)
        comparison_rows.append(
            {
                "metric": key,
                "finetuned": ft_val,
                "baseline": base_val,
                "delta": delta,
                "direction": direction,
            }
        )

    try:
        content = render_template(
            "docs/perf_report.md.j2",
            project_id=project_id,
            metrics=metrics,
            baseline=base,
            comparison_rows=comparison_rows,
            notes=notes or [],
            eval_dataset=eval_dataset or "client validation set",
            generated_at=_now_iso(),
            curves_description=None,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "reports" / "perf_report.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    md_sha256 = sha256_bytes(content.encode())
    result_data: dict[str, Any] = {"md_path": str(dest), "sha256": md_sha256}

    pdf_path, pdf_msg = _try_pdf(dest)
    if pdf_path:
        result_data["pdf_path"] = pdf_path
    elif pdf_msg:
        result_data["pdf_skipped"] = pdf_msg

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# Tool 50: generate_user_guide (C1)
# ---------------------------------------------------------------------------


def generate_user_guide(
    project_id: str,
    base_url: str = "http://localhost:8000",
    port: int = 8000,
    engine: str = "vllm",
    model_name: str = "ftos-model",
    max_tokens: int = 512,
    temperature: float = 0.7,
    context_length: int = 4096,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render user_guide.md.j2 (API endpoints, code examples, params)."""
    try:
        content = render_template(
            "docs/user_guide.md.j2",
            project_id=project_id,
            base_url=base_url,
            port=port,
            engine=engine,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            context_length=context_length,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "docs" / "user_guide.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "md_path": str(dest),
            "sha256": sha256_bytes(content.encode()),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 51: generate_deployment_guide (C1)
# ---------------------------------------------------------------------------


def generate_deployment_guide(
    project_id: str,
    port: int = 8000,
    gpu_device: str = "all",
    api_hostname: str = "api.example.com",
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render deployment_guide.md.j2 (IT deployment procedure)."""
    try:
        content = render_template(
            "docs/deployment_guide.md.j2",
            project_id=project_id,
            port=port,
            gpu_device=gpu_device,
            api_hostname=api_hostname,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "docs" / "deployment_guide.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "md_path": str(dest),
            "sha256": sha256_bytes(content.encode()),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 52: generate_destruction_certificate (C1)
# ---------------------------------------------------------------------------


def generate_destruction_certificate(
    project_id: str,
    date: str,
    methode: str,
    signataire: str = "[SIGNATAIRE]",
    client_nom: str = "[CLIENT]",
    prestataire_nom: str = "[PRESTATAIRE]",
    description_donnees: str | None = None,
    lieu: str = "Paris",
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render destruction_cert.md.j2 (RGPD art. 17, 5-1-c, 32)."""
    try:
        content = render_template(
            "legal/destruction_cert.md.j2",
            project_id=project_id,
            date=date,
            methode=methode,
            signataire=signataire,
            client_nom=client_nom,
            prestataire_nom=prestataire_nom,
            lieu=lieu,
            description_donnees=description_donnees,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "deliverables" / "destruction_cert.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    md_sha256 = sha256_bytes(content.encode())
    result_data: dict[str, Any] = {"md_path": str(dest), "sha256": md_sha256}

    pdf_path, pdf_msg = _try_pdf(dest)
    if pdf_path:
        result_data["pdf_path"] = pdf_path
    elif pdf_msg:
        result_data["pdf_skipped"] = pdf_msg

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# Tool 53: export_document_pdf (C1)
# ---------------------------------------------------------------------------


def export_document_pdf(md_path: str) -> dict[str, Any]:
    """Convert a generated Markdown document to PDF via render.markdown_file_to_pdf.

    Returns pdf_path + sha256. Skips/fails gracefully if weasyprint absent.
    """
    src = Path(md_path)
    if not src.exists():
        return fail(f"file not found: {md_path}").to_dict()

    try:
        pdf_dest = src.with_suffix(".pdf")
        markdown_file_to_pdf(src, pdf_dest)
        file_sha256 = sha256_file(pdf_dest)
        return ok(
            {
                "pdf_path": str(pdf_dest),
                "sha256": file_sha256,
            }
        ).to_dict()
    except ImportError:
        return fail(
            "weasyprint is not installed; install it with: pip install weasyprint"
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 54: sign_document (C2 — local sig sidecar default)
# ---------------------------------------------------------------------------


def sign_document(
    doc_path: str,
    signer: str | None = None,
) -> dict[str, Any]:
    """Apply an electronic signature to a document.

    Default: local detached signature — SHA-256 hash + RFC3339 timestamp
    written to a .sig sidecar file. No external API calls unless configured.
    Dry-run: always produces the sidecar locally (C2 gate is for esign API upgrade).
    """
    src = Path(doc_path)
    if not src.exists():
        return fail(f"file not found: {doc_path}").to_dict()

    # Always compute local signature (C2 = "configured path goes to esign API")
    configured, meta = gate("local_python")  # local_python = "extended" mode gate
    now = _now_iso()

    try:
        doc_sha256 = sha256_file(src)
        signer_str = signer or os.environ.get("FTOS_SIGNER", "[operator]")
        sig_content = (
            f"document: {src.name}\n"
            f"sha256: {doc_sha256}\n"
            f"timestamp: {now}\n"
            f"signer: {signer_str}\n"
            f"method: sha256-local\n"
        )
        sig_path = src.with_suffix(src.suffix + ".sig")
        write_text_atomic(sig_path, sig_content)
        sig_sha256 = sha256_bytes(sig_content.encode())
    except (OSError, ValueError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "sig_path": str(sig_path),
            "doc_sha256": doc_sha256,
            "timestamp": now,
            "signer": signer_str,
            "sig_sha256": sig_sha256,
            "method": "sha256-local",
            "note": "Local detached signature. For qualified electronic signatures, configure an e-sign API.",
        },
        executed=True,
        dry_run=False,
    ).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with generate_contract
def _mcp_generate_contract(
    project_id: str,
    montant: str,
    clauses: str = "",
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
) -> dict[str, Any]:
    return generate_contract(
        project_id=project_id,
        montant=montant,
        clauses=clauses,
        prestataire_nom=prestataire_nom,
        client_nom=client_nom,
    )


# MCP wrapper — keep signature in sync with generate_nda
def _mcp_generate_nda(
    project_id: str,
    partie_a: str,
    partie_b: str,
    duree: str = "3 ans",
    juridiction: str = "Tribunal de commerce de Paris",
    objet: str | None = None,
) -> dict[str, Any]:
    return generate_nda(
        project_id=project_id,
        partie_a=partie_a,
        partie_b=partie_b,
        duree=duree,
        juridiction=juridiction,
        objet=objet,
    )


# MCP wrapper — keep signature in sync with generate_performance_report
def _mcp_generate_performance_report(
    project_id: str,
    metrics: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    eval_dataset: str | None = None,
) -> dict[str, Any]:
    return generate_performance_report(
        project_id=project_id,
        metrics=metrics,
        baseline=baseline,
        notes=notes,
        eval_dataset=eval_dataset,
    )


# MCP wrapper — keep signature in sync with generate_user_guide
def _mcp_generate_user_guide(
    project_id: str,
    base_url: str = "http://localhost:8000",
    port: int = 8000,
    engine: str = "vllm",
    model_name: str = "ftos-model",
    max_tokens: int = 512,
    temperature: float = 0.7,
    context_length: int = 4096,
) -> dict[str, Any]:
    return generate_user_guide(
        project_id=project_id,
        base_url=base_url,
        port=port,
        engine=engine,
        model_name=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        context_length=context_length,
    )


# MCP wrapper — keep signature in sync with generate_deployment_guide
def _mcp_generate_deployment_guide(
    project_id: str,
    port: int = 8000,
    gpu_device: str = "all",
    api_hostname: str = "api.example.com",
) -> dict[str, Any]:
    return generate_deployment_guide(
        project_id=project_id,
        port=port,
        gpu_device=gpu_device,
        api_hostname=api_hostname,
    )


# MCP wrapper — keep signature in sync with generate_destruction_certificate
def _mcp_generate_destruction_certificate(
    project_id: str,
    date: str,
    methode: str,
    signataire: str = "[SIGNATAIRE]",
    client_nom: str = "[CLIENT]",
    prestataire_nom: str = "[PRESTATAIRE]",
    description_donnees: str | None = None,
    lieu: str = "Paris",
) -> dict[str, Any]:
    return generate_destruction_certificate(
        project_id=project_id,
        date=date,
        methode=methode,
        signataire=signataire,
        client_nom=client_nom,
        prestataire_nom=prestataire_nom,
        description_donnees=description_donnees,
        lieu=lieu,
    )


# MCP wrapper — keep signature in sync with export_document_pdf
def _mcp_export_document_pdf(md_path: str) -> dict[str, Any]:
    return export_document_pdf(md_path=md_path)


# MCP wrapper — keep signature in sync with sign_document
def _mcp_sign_document(
    doc_path: str,
    signer: str | None = None,
) -> dict[str, Any]:
    return sign_document(doc_path=doc_path, signer=signer)


_MCP_TOOLS = [
    (
        _mcp_generate_contract,
        "Render a French-law service contract (Code civil, CPI, RGPD art. 28) as Markdown + optional PDF.",
    ),
    (
        _mcp_generate_nda,
        "Render a bilateral NDA (secret des affaires — Code de commerce L151-1 s.) as Markdown.",
    ),
    (
        _mcp_generate_performance_report,
        "Render a performance report with metrics, baseline comparison, and curves description.",
    ),
    (
        _mcp_generate_user_guide,
        "Render an inference API user guide (endpoints, code examples, parameters).",
    ),
    (
        _mcp_generate_deployment_guide,
        "Render an IT deployment guide for the inference container.",
    ),
    (
        _mcp_generate_destruction_certificate,
        "Render an irreversible data destruction certificate (RGPD art. 17, 5-1-c, 32).",
    ),
    (
        _mcp_export_document_pdf,
        "Convert a Markdown document to PDF — skips gracefully if weasyprint absent.",
    ),
    (
        _mcp_sign_document,
        "Apply a local detached signature (SHA-256 + timestamp) as a .sig sidecar file.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all documentation tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
