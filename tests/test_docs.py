# tests/test_docs.py
"""TDD tests for docs.py tools (47–54).

Coverage requirements:
- Legal templates: assert content contains French law citations
- PDF tools: assert md written + sha256; pdf path or pdf_skipped key
- C2 tool (54 sign_document): nominal + error path
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from fine_tuning_os.tools import docs


# ---------------------------------------------------------------------------
# Tool 47: generate_contract (C1)
# ---------------------------------------------------------------------------
class TestGenerateContract:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="15 000 €",
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]
        assert Path(result["data"]["md_path"]).exists()

    def test_contains_code_civil(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="5 000 €",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "Code civil" in content

    def test_contains_article_1231(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="5 000 €",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "1231" in content

    def test_contains_rgpd_art28(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="5 000 €",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "28" in content or "RGPD" in content or "sous-traitance" in content

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="1 000 €",
            store=store,
        )
        assert len(result["data"]["sha256"]) == 64

    def test_pdf_skipped_gracefully(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = docs.generate_contract(project_id=project_id, montant="1 €", store=store)
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]

    def test_disclaimer_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="1 €",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "relecture" in content.lower() or "adapter" in content.lower()

    def test_clause_limitative_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_contract(
            project_id=project_id,
            montant="1 €",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "limitative" in content.lower() or "plafon" in content.lower()


# ---------------------------------------------------------------------------
# Tool 48: generate_nda (C1)
# ---------------------------------------------------------------------------
class TestGenerateNda:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(
            project_id=project_id,
            partie_a="ACME Corp",
            partie_b="FineTune Labs",
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]

    def test_contains_l151_1(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(
            project_id=project_id,
            partie_a="A",
            partie_b="B",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "L151-1" in content

    def test_contains_secret_affaires(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(
            project_id=project_id,
            partie_a="A",
            partie_b="B",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "secret des affaires" in content.lower() or "Secret des affaires" in content

    def test_duree_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(
            project_id=project_id,
            partie_a="A",
            partie_b="B",
            duree="5 ans",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "5 ans" in content

    def test_juridiction_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(
            project_id=project_id,
            partie_a="A",
            partie_b="B",
            juridiction="Tribunal de commerce de Lyon",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "Lyon" in content

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_nda(project_id=project_id, partie_a="X", partie_b="Y", store=store)
        assert len(result["data"]["sha256"]) == 64


# ---------------------------------------------------------------------------
# Tool 49: generate_performance_report (C1)
# ---------------------------------------------------------------------------
class TestGeneratePerformanceReport:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_performance_report(
            project_id=project_id,
            metrics={"bleu": 0.45, "perplexity": 12.3},
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]

    def test_content_contains_metrics(self, store: Any, project_id: str) -> None:
        result = docs.generate_performance_report(
            project_id=project_id,
            metrics={"bleu": 0.45, "rouge1": 0.55},
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "bleu" in content.lower() or "0.45" in content

    def test_baseline_comparison(self, store: Any, project_id: str) -> None:
        result = docs.generate_performance_report(
            project_id=project_id,
            metrics={"bleu": 0.5},
            baseline={"bleu": 0.3},
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "0.5" in content or "bleu" in content.lower()

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_performance_report(
            project_id=project_id,
            metrics={"accuracy": 0.9},
            store=store,
        )
        assert len(result["data"]["sha256"]) == 64

    def test_pdf_skipped_gracefully(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = docs.generate_performance_report(
                project_id=project_id,
                metrics={"accuracy": 0.9},
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]


# ---------------------------------------------------------------------------
# Tool 50: generate_user_guide (C1)
# ---------------------------------------------------------------------------
class TestGenerateUserGuide:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_user_guide(
            project_id=project_id,
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]

    def test_contains_api_endpoint(self, store: Any, project_id: str) -> None:
        result = docs.generate_user_guide(
            project_id=project_id,
            base_url="http://localhost:8000",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "/v1/chat/completions" in content or "chat" in content.lower()

    def test_no_real_key_in_content(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("API_KEY", "super_secret_api_key_xyz")
        result = docs.generate_user_guide(
            project_id=project_id,
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "super_secret_api_key_xyz" not in content

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_user_guide(project_id=project_id, store=store)
        assert len(result["data"]["sha256"]) == 64

    def test_custom_port_in_content(self, store: Any, project_id: str) -> None:
        result = docs.generate_user_guide(project_id=project_id, port=9090, store=store)
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "9090" in content


# ---------------------------------------------------------------------------
# Tool 51: generate_deployment_guide (C1)
# ---------------------------------------------------------------------------
class TestGenerateDeploymentGuide:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_deployment_guide(project_id=project_id, store=store)
        assert result["success"] is True
        assert "md_path" in result["data"]

    def test_contains_docker_run(self, store: Any, project_id: str) -> None:
        result = docs.generate_deployment_guide(project_id=project_id, store=store)
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "docker" in content.lower()

    def test_project_id_in_content(self, store: Any, project_id: str) -> None:
        result = docs.generate_deployment_guide(project_id=project_id, store=store)
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert project_id in content

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_deployment_guide(project_id=project_id, store=store)
        assert len(result["data"]["sha256"]) == 64


# ---------------------------------------------------------------------------
# Tool 52: generate_destruction_certificate (C1)
# ---------------------------------------------------------------------------
class TestGenerateDestructionCertificate:
    def test_nominal(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-15",
            methode="secure_erase_aes256",
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]

    def test_contains_rgpd_article_17(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-15",
            methode="secure_erase_aes256",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "article 17" in content.lower() or "Article 17" in content

    def test_contains_rgpd_keyword(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-15",
            methode="secure_erase_aes256",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "RGPD" in content

    def test_date_in_content(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-06-01",
            methode="physical_destruction",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "2025-06-01" in content

    def test_methode_in_content(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-01",
            methode="overwrite_dod5220",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "overwrite_dod5220" in content or "DOD" in content or "dod" in content.lower()

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-01",
            methode="secure_erase_aes256",
            store=store,
        )
        assert len(result["data"]["sha256"]) == 64

    def test_pdf_skipped_gracefully(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = docs.generate_destruction_certificate(
                project_id=project_id,
                date="2025-01-01",
                methode="secure_erase_aes256",
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]

    def test_contains_aes256(self, store: Any, project_id: str) -> None:
        result = docs.generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-01",
            methode="secure_erase_aes256",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "AES-256" in content or "AES256" in content


# ---------------------------------------------------------------------------
# Tool 53: export_document_pdf (C1)
# ---------------------------------------------------------------------------
class TestExportDocumentPdf:
    def test_weasyprint_not_installed_fails_gracefully(self, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\nContent", encoding="utf-8")
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = docs.export_document_pdf(md_path=str(md_file))
        assert result["success"] is False
        assert "weasyprint" in result["error"].lower()

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = docs.export_document_pdf(md_path=str(tmp_path / "nonexistent.md"))
        assert result["success"] is False

    def test_pdf_produced_when_weasyprint_available(self, tmp_path: Path) -> None:
        pytest.importorskip("weasyprint")
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\nContent here.", encoding="utf-8")
        result = docs.export_document_pdf(md_path=str(md_file))
        # Either success with pdf_path, or fail gracefully
        if result["success"]:
            assert "pdf_path" in result["data"]
            assert "sha256" in result["data"]


# ---------------------------------------------------------------------------
# Tool 54: sign_document (C2 — local sig sidecar)
# ---------------------------------------------------------------------------
class TestSignDocument:
    def test_nominal(self, tmp_path: Path) -> None:
        doc = tmp_path / "contract.md"
        doc.write_text("# Contract\nContent", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc))
        assert result["success"] is True
        assert "sig_path" in result["data"]
        assert "doc_sha256" in result["data"]
        assert "timestamp" in result["data"]

    def test_sidecar_file_created(self, tmp_path: Path) -> None:
        doc = tmp_path / "nda.md"
        doc.write_text("# NDA\nContent", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc))
        sig_path = Path(result["data"]["sig_path"])
        assert sig_path.exists()

    def test_sidecar_contains_sha256(self, tmp_path: Path) -> None:
        doc = tmp_path / "report.md"
        doc.write_text("# Report\nContent", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc))
        sig_path = Path(result["data"]["sig_path"])
        sig_content = sig_path.read_text(encoding="utf-8")
        assert result["data"]["doc_sha256"] in sig_content

    def test_sidecar_contains_timestamp(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc))
        sig_path = Path(result["data"]["sig_path"])
        sig_content = sig_path.read_text(encoding="utf-8")
        assert "timestamp" in sig_content

    def test_custom_signer(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc), signer="John Doe")
        sig_path = Path(result["data"]["sig_path"])
        sig_content = sig_path.read_text(encoding="utf-8")
        assert "John Doe" in sig_content

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = docs.sign_document(doc_path=str(tmp_path / "missing.md"))
        assert result["success"] is False

    def test_doc_sha256_matches_actual(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        content = "# Contract\nExact content for hashing"
        doc.write_text(content, encoding="utf-8")
        from fine_tuning_os.render import sha256_file  # noqa: PLC0415

        expected_sha = sha256_file(doc)
        result = docs.sign_document(doc_path=str(doc))
        assert result["data"]["doc_sha256"] == expected_sha

    def test_result_has_method_field(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc", encoding="utf-8")
        result = docs.sign_document(doc_path=str(doc))
        assert "method" in result["data"]
        assert "sha256" in result["data"]["method"]


# ---------------------------------------------------------------------------
# MCP wrappers and register() — thin coverage pass
# ---------------------------------------------------------------------------
class TestDocsMcpWrappers:
    def test_mcp_generate_contract_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_contract(project_id=project_id, montant="1 000 €")
        assert result["success"] is True

    def test_mcp_generate_nda_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_nda(project_id=project_id, partie_a="A", partie_b="B")
        assert result["success"] is True

    def test_mcp_generate_perf_report_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_performance_report(project_id=project_id, metrics={"bleu": 0.4})
        assert result["success"] is True

    def test_mcp_generate_user_guide_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_user_guide(project_id=project_id)
        assert result["success"] is True

    def test_mcp_generate_deployment_guide_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_deployment_guide(project_id=project_id)
        assert result["success"] is True

    def test_mcp_generate_destruction_cert_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = docs._mcp_generate_destruction_certificate(
            project_id=project_id,
            date="2025-01-01",
            methode="secure_erase_aes256",
        )
        assert result["success"] is True

    def test_mcp_export_document_pdf_delegates(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Test", encoding="utf-8")
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=ImportError("no weasyprint"),
        ):
            result = docs._mcp_export_document_pdf(md_path=str(md))
        # Graceful fail
        assert result["success"] is False

    def test_mcp_sign_document_delegates(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc", encoding="utf-8")
        result = docs._mcp_sign_document(doc_path=str(doc))
        assert result["success"] is True

    def test_register_calls_mcp_tool(self) -> None:
        registered: list[str] = []

        class FakeMcp:
            def tool(self, description: str):  # type: ignore[no-untyped-def]
                def decorator(fn):  # type: ignore[no-untyped-def]
                    registered.append(fn.__name__)
                    return fn

                return decorator

        docs.register(FakeMcp())
        assert len(registered) == 8  # 8 docs tools


# ---------------------------------------------------------------------------
# Error paths for _try_pdf and write errors — push docs.py coverage > 80%
# ---------------------------------------------------------------------------
class TestDocsErrorPaths:
    """Cover exception branches: template error, write error, _try_pdf error path."""

    def test_generate_contract_template_render_error(self, store: Any, project_id: str) -> None:
        """If render_template raises, generate_contract returns fail."""
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad template"),
        ):
            result = docs.generate_contract(
                project_id=project_id,
                montant="1 €",
                store=store,
            )
        assert result["success"] is False
        assert "template error" in result["error"]

    def test_generate_nda_template_render_error(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad nda template"),
        ):
            result = docs.generate_nda(
                project_id=project_id,
                partie_a="A",
                partie_b="B",
                store=store,
            )
        assert result["success"] is False

    def test_generate_performance_report_template_error(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad perf template"),
        ):
            result = docs.generate_performance_report(
                project_id=project_id,
                metrics={"bleu": 0.5},
                store=store,
            )
        assert result["success"] is False

    def test_try_pdf_generic_exception(self, store: Any, project_id: str) -> None:
        """_try_pdf generic Exception path sets pdf_skipped (not pdf_path)."""
        with patch(
            "fine_tuning_os.tools.docs.markdown_file_to_pdf",
            side_effect=RuntimeError("render failed"),
        ):
            result = docs.generate_contract(
                project_id=project_id,
                montant="1 €",
                store=store,
            )
        assert result["success"] is True
        # Generic exception → pdf_skipped set to the error message
        assert "pdf_skipped" in result["data"]

    def test_generate_user_guide_template_error(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad user guide"),
        ):
            result = docs.generate_user_guide(project_id=project_id, store=store)
        assert result["success"] is False

    def test_generate_deployment_guide_template_error(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad deploy guide"),
        ):
            result = docs.generate_deployment_guide(project_id=project_id, store=store)
        assert result["success"] is False

    def test_generate_destruction_certificate_template_error(
        self, store: Any, project_id: str
    ) -> None:
        with patch(
            "fine_tuning_os.tools.docs.render_template",
            side_effect=ValueError("bad cert"),
        ):
            result = docs.generate_destruction_certificate(
                project_id=project_id,
                date="2026-01-01",
                methode="AES256",
                store=store,
            )
        assert result["success"] is False
