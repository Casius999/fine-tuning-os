# tests/test_client.py
"""TDD tests for client.py tools (55-60).

C1 tools: 55 onboard_client, 58 log_project_event,
          59 request_client_approval, 60 generate_invoice.
C2 tools: 56 send_status_update (smtp|slack), 57 schedule_meeting (calendly).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fine_tuning_os.tools import client


# ---------------------------------------------------------------------------
# Tool 55: onboard_client (C1)
# ---------------------------------------------------------------------------
class TestOnboardClient:
    def test_nominal_creates_project_json(self, store: Any, workspace: Path) -> None:
        result = client.onboard_client(
            company="ACME Corp",
            needs="Fine-tune a coding assistant",
            store=store,
        )
        assert result["success"] is True
        project_id = result["data"]["project_id"]
        state = result["data"]["state"]
        assert state["status"] == "onboarded"
        # project.json must exist
        pdir = workspace / project_id
        assert (pdir / "project.json").exists()

    def test_state_contains_company(self, store: Any) -> None:
        result = client.onboard_client(
            company="TechStart",
            needs="Summarisation model",
            store=store,
        )
        assert result["data"]["state"]["client"] == "TechStart"

    def test_state_contains_needs(self, store: Any) -> None:
        result = client.onboard_client(
            company="MedCorp",
            needs="Clinical NER",
            store=store,
        )
        assert result["data"]["state"]["needs"] == "Clinical NER"

    def test_state_contains_contact_email(self, store: Any) -> None:
        result = client.onboard_client(
            company="HealthCo",
            needs="Diagnosis assistant",
            contact_email="pm@healthco.com",
            store=store,
        )
        assert result["data"]["state"]["contact_email"] == "pm@healthco.com"

    def test_custom_base_model_persisted(self, store: Any) -> None:
        result = client.onboard_client(
            company="BigTech",
            needs="Code gen",
            base_model="codellama-7b",
            store=store,
        )
        assert result["data"]["state"]["base_model"] == "codellama-7b"

    def test_empty_company_fails(self, store: Any) -> None:
        result = client.onboard_client(company="", needs="x", store=store)
        assert result["success"] is False

    def test_returns_project_id(self, store: Any) -> None:
        result = client.onboard_client(company="Co", needs="y", store=store)
        assert "project_id" in result["data"]
        assert result["data"]["project_id"]


# ---------------------------------------------------------------------------
# Tool 56: send_status_update (C2 — smtp | slack)
# ---------------------------------------------------------------------------
class TestSendStatusUpdate:
    def test_no_env_dry_run_smtp(
        self,
        store: Any,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without SMTP or Slack env → dry_run + message, no network."""
        for v in (
            "FTOS_SMTP_HOST",
            "FTOS_SMTP_USER",
            "FTOS_SMTP_PASSWORD",
            "FTOS_SLACK_WEBHOOK",
        ):
            monkeypatch.delenv(v, raising=False)

        result = client.send_status_update(
            project_id=project_id,
            subject="Phase 1 done",
            body="Training complete",
            store=store,
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "message" in result["data"]

    def test_dry_run_no_smtp_called(
        self,
        store: Any,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """smtplib must never be called in dry_run path."""
        for v in (
            "FTOS_SMTP_HOST",
            "FTOS_SMTP_USER",
            "FTOS_SMTP_PASSWORD",
            "FTOS_SLACK_WEBHOOK",
        ):
            monkeypatch.delenv(v, raising=False)

        with patch("fine_tuning_os.tools.client.smtplib") as mock_smtp:
            mock_smtp.SMTP.side_effect = RuntimeError("should not be called")
            result = client.send_status_update(
                project_id=project_id,
                subject="Test",
                body="Body",
                store=store,
            )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_smtp_configured_sanitizes_output(
        self,
        store: Any,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Configured SMTP path must sanitize any provider response text."""
        monkeypatch.setenv("FTOS_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("FTOS_SMTP_USER", "user@example.com")
        monkeypatch.setenv("FTOS_SMTP_PASSWORD", "s3cr3t")
        monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)

        with patch("fine_tuning_os.tools.client.smtplib") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.SMTP.return_value.__enter__ = lambda s: mock_server
            mock_smtp.SMTP.return_value.__exit__ = MagicMock(return_value=False)

            result = client.send_status_update(
                project_id=project_id,
                subject="Update",
                body="Trained model",
                recipient="client@example.com",
                store=store,
            )
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        # No secret value in output
        assert "s3cr3t" not in repr(result)

    def test_slack_configured_sanitizes(
        self,
        store: Any,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Configured Slack path: httpx POST, sanitize response, no secret in output."""
        monkeypatch.delenv("FTOS_SMTP_HOST", raising=False)
        monkeypatch.delenv("FTOS_SMTP_USER", raising=False)
        monkeypatch.delenv("FTOS_SMTP_PASSWORD", raising=False)
        monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.slack.com/T00/B00/secret_token")

        mock_resp = MagicMock()
        mock_resp.text = "ok"
        mock_resp.status_code = 200

        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            result = client.send_status_update(
                project_id=project_id,
                subject="Update",
                body="Done",
                store=store,
            )
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        assert "secret_token" not in repr(result)

    def test_invalid_project_id_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for v in ("FTOS_SMTP_HOST", "FTOS_SMTP_USER", "FTOS_SMTP_PASSWORD", "FTOS_SLACK_WEBHOOK"):
            monkeypatch.delenv(v, raising=False)
        result = client.send_status_update(project_id="", subject="x", body="y")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 57: schedule_meeting (C2 — calendly)
# ---------------------------------------------------------------------------
class TestScheduleMeeting:
    def test_no_env_dry_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_CALENDLY_TOKEN", raising=False)
        result = client.schedule_meeting(duration=30, window="2025-07-01/2025-07-07")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert "command" in result["data"]

    def test_dry_run_no_httpx_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_CALENDLY_TOKEN", raising=False)
        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.get.side_effect = RuntimeError("should not be called")
            result = client.schedule_meeting(duration=60, window="next-week")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_configured_fetches_link_sanitized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_CALENDLY_TOKEN", "cal_token_secret")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "scheduling_url": "https://calendly.com/acme/30min",
            "owner": "user@acme.com",
        }
        mock_resp.status_code = 200

        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            result = client.schedule_meeting(duration=30, window="2025-07-01/2025-07-07")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        # Secret token must not appear in output
        assert "cal_token_secret" not in repr(result)

    def test_configured_sanitizes_email_in_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_CALENDLY_TOKEN", "token_xyz")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "scheduling_url": "https://calendly.com/u/30",
            "owner_email": "boss@company.com",
        }
        mock_resp.status_code = 200

        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            result = client.schedule_meeting(duration=30, window="any")
        assert result["success"] is True
        # Email from response should be sanitized
        assert "boss@company.com" not in repr(result)


# ---------------------------------------------------------------------------
# Tool 58: log_project_event (C1)
# ---------------------------------------------------------------------------
class TestLogProjectEvent:
    def test_nominal_appends_to_events_jsonl(
        self, store: Any, project_id: str, workspace: Path
    ) -> None:
        result = client.log_project_event(
            project_id=project_id,
            event_type="milestone",
            payload={"name": "training_complete"},
            store=store,
        )
        assert result["success"] is True
        assert "event_id" in result["data"]
        events_path = workspace / project_id / "events.jsonl"
        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1

    def test_event_contains_type_and_payload(
        self, store: Any, project_id: str, workspace: Path
    ) -> None:
        client.log_project_event(
            project_id=project_id,
            event_type="approval_received",
            payload={"approved_by": "pm"},
            store=store,
        )
        events_path = workspace / project_id / "events.jsonl"
        record = json.loads(events_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert record["type"] == "approval_received"
        assert record["payload"]["approved_by"] == "pm"

    def test_event_id_matches_returned_id(
        self, store: Any, project_id: str, workspace: Path
    ) -> None:
        result = client.log_project_event(
            project_id=project_id,
            event_type="test",
            payload={},
            store=store,
        )
        events_path = workspace / project_id / "events.jsonl"
        record = json.loads(events_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert record["id"] == result["data"]["event_id"]

    def test_multiple_events_appended(self, store: Any, project_id: str, workspace: Path) -> None:
        client.log_project_event(project_id=project_id, event_type="a", payload={}, store=store)
        client.log_project_event(project_id=project_id, event_type="b", payload={}, store=store)
        events_path = workspace / project_id / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 2

    def test_invalid_project_fails(self, store: Any) -> None:
        result = client.log_project_event(
            project_id="../../etc",
            event_type="test",
            payload={},
            store=store,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 59: request_client_approval (C1)
# ---------------------------------------------------------------------------
class TestRequestClientApproval:
    def test_nominal_returns_approval_id(self, store: Any, project_id: str) -> None:
        result = client.request_client_approval(
            project_id=project_id,
            question="Approve the training dataset?",
            artifacts=["data/train.jsonl"],
            store=store,
        )
        assert result["success"] is True
        assert "approval_id" in result["data"]
        assert result["data"]["status"] == "pending"

    def test_approval_persisted_in_project_json(
        self, store: Any, project_id: str, workspace: Path
    ) -> None:
        client.request_client_approval(
            project_id=project_id,
            question="Approve model?",
            artifacts=[],
            store=store,
        )
        state = store.read_project(project_id)
        assert "approvals" in state
        assert len(state["approvals"]) >= 1

    def test_approval_status_is_pending(self, store: Any, project_id: str) -> None:
        result = client.request_client_approval(
            project_id=project_id,
            question="Review contract?",
            artifacts=["contract.md"],
            store=store,
        )
        state = store.read_project(project_id)
        approval = next(a for a in state["approvals"] if a["id"] == result["data"]["approval_id"])
        assert approval["status"] == "pending"

    def test_question_in_state(self, store: Any, project_id: str) -> None:
        q = "Approve the final model weights?"
        result = client.request_client_approval(
            project_id=project_id,
            question=q,
            artifacts=[],
            store=store,
        )
        state = store.read_project(project_id)
        approval = next(a for a in state["approvals"] if a["id"] == result["data"]["approval_id"])
        assert approval["question"] == q

    def test_event_logged(self, store: Any, project_id: str, workspace: Path) -> None:
        client.request_client_approval(
            project_id=project_id,
            question="Approve?",
            artifacts=[],
            store=store,
        )
        events_path = workspace / project_id / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        types = [json.loads(line)["type"] for line in lines]
        assert "approval_requested" in types

    def test_multiple_approvals_tracked(self, store: Any, project_id: str) -> None:
        client.request_client_approval(
            project_id=project_id, question="Q1", artifacts=[], store=store
        )
        client.request_client_approval(
            project_id=project_id, question="Q2", artifacts=[], store=store
        )
        state = store.read_project(project_id)
        assert len(state["approvals"]) == 2

    def test_empty_question_fails(self, store: Any, project_id: str) -> None:
        result = client.request_client_approval(
            project_id=project_id, question="", artifacts=[], store=store
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 60: generate_invoice (C1)
# ---------------------------------------------------------------------------
class TestGenerateInvoice:
    def test_nominal_md_written(self, store: Any, project_id: str, workspace: Path) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[{"desc": "Fine-tuning", "qty": 1, "pu": 5000, "montant": 5000}],
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]
        assert Path(result["data"]["md_path"]).exists()

    def test_sha256_present(self, store: Any, project_id: str) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[{"desc": "Training", "qty": 1, "pu": 3000, "montant": 3000}],
            store=store,
        )
        assert len(result["data"]["sha256"]) == 64

    def test_invoice_contains_line_desc(self, store: Any, project_id: str) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[{"desc": "GPU Cloud Access", "qty": 5, "pu": 200, "montant": 1000}],
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "GPU Cloud Access" in content

    def test_pdf_skipped_gracefully(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.client.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = client.generate_invoice(
                project_id=project_id,
                lines=[{"desc": "Service", "qty": 1, "pu": 1000, "montant": 1000}],
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]

    def test_empty_lines_fails(self, store: Any, project_id: str) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[],
            store=store,
        )
        assert result["success"] is False

    def test_invoice_in_deliverables(self, store: Any, project_id: str, workspace: Path) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[{"desc": "Consulting", "qty": 1, "pu": 500, "montant": 500}],
            store=store,
        )
        md_path = Path(result["data"]["md_path"])
        assert "deliverables" in str(md_path)

    def test_custom_conditions_in_content(self, store: Any, project_id: str) -> None:
        result = client.generate_invoice(
            project_id=project_id,
            lines=[{"desc": "Work", "qty": 1, "pu": 100, "montant": 100}],
            conditions_paiement="Paiement à 15 jours.",
            store=store,
        )
        content = Path(result["data"]["md_path"]).read_text(encoding="utf-8")
        assert "15 jours" in content


# ---------------------------------------------------------------------------
# MCP wrappers and register()
# ---------------------------------------------------------------------------
class TestClientMcpWrappers:
    def test_mcp_onboard_client_delegates(
        self, store: Any, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        result = client._mcp_onboard_client(company="TestCo", needs="LLM project")
        assert result["success"] is True

    def test_mcp_log_project_event_delegates(
        self,
        store: Any,
        project_id: str,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        result = client._mcp_log_project_event(project_id=project_id, event_type="test", payload={})
        assert result["success"] is True

    def test_mcp_request_client_approval_delegates(
        self,
        store: Any,
        project_id: str,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        result = client._mcp_request_client_approval(
            project_id=project_id,
            question="Approve?",
            artifacts=[],
        )
        assert result["success"] is True

    def test_mcp_generate_invoice_delegates(
        self,
        store: Any,
        project_id: str,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        result = client._mcp_generate_invoice(
            project_id=project_id,
            lines=[{"desc": "Service", "qty": 1, "pu": 100, "montant": 100}],
        )
        assert result["success"] is True

    def test_register_registers_six_tools(self) -> None:
        registered: list[str] = []

        class FakeMcp:
            def tool(self, description: str):  # type: ignore[no-untyped-def]
                def decorator(fn):  # type: ignore[no-untyped-def]
                    registered.append(fn.__name__)
                    return fn

                return decorator

        client.register(FakeMcp())
        assert len(registered) == 6  # tools 55-60


# ---------------------------------------------------------------------------
# Error / edge paths to push client.py coverage >= 88%
# ---------------------------------------------------------------------------
class TestClientErrorPaths:
    def test_onboard_client_store_write_error(
        self, store: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If init_project raises OSError, onboard_client returns fail."""
        with patch.object(store, "init_project", side_effect=OSError("disk full")):
            result = client.onboard_client(company="FailCo", needs="x", store=store)
        assert result["success"] is False

    def test_send_status_update_template_error(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for v in ("FTOS_SMTP_HOST", "FTOS_SMTP_USER", "FTOS_SMTP_PASSWORD", "FTOS_SLACK_WEBHOOK"):
            monkeypatch.delenv(v, raising=False)
        with patch("fine_tuning_os.tools.client.render_template", side_effect=ValueError("bad")):
            result = client.send_status_update(
                project_id=project_id, subject="S", body="B", store=store
            )
        assert result["success"] is False

    def test_send_status_update_smtp_error(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SMTP configured but raises → fail."""
        monkeypatch.setenv("FTOS_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("FTOS_SMTP_USER", "u@example.com")
        monkeypatch.setenv("FTOS_SMTP_PASSWORD", "pass")
        monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
        with patch("fine_tuning_os.tools.client.smtplib") as mock_smtp:
            mock_smtp.SMTP.side_effect = OSError("connection refused")
            result = client.send_status_update(
                project_id=project_id, subject="S", body="B", store=store
            )
        assert result["success"] is False

    def test_send_status_update_slack_error(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Slack configured but raises → fail."""
        monkeypatch.delenv("FTOS_SMTP_HOST", raising=False)
        monkeypatch.delenv("FTOS_SMTP_USER", raising=False)
        monkeypatch.delenv("FTOS_SMTP_PASSWORD", raising=False)
        monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.slack.com/xxx")
        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.post.side_effect = OSError("network error")
            result = client.send_status_update(
                project_id=project_id, subject="S", body="B", store=store
            )
        assert result["success"] is False

    def test_send_status_update_slack_http_4xx_fails(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Slack returning HTTP 401 → raise_for_status → success=False."""
        monkeypatch.delenv("FTOS_SMTP_HOST", raising=False)
        monkeypatch.delenv("FTOS_SMTP_USER", raising=False)
        monkeypatch.delenv("FTOS_SMTP_PASSWORD", raising=False)
        monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.slack.com/xxx")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=MagicMock()
        )
        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            mock_httpx.HTTPStatusError = httpx.HTTPStatusError
            result = client.send_status_update(
                project_id=project_id, subject="S", body="B", store=store
            )
        assert result["success"] is False

    def test_schedule_meeting_calendly_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calendly configured but raises → fail."""
        monkeypatch.setenv("FTOS_CALENDLY_TOKEN", "tok")
        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.get.side_effect = OSError("timeout")
            result = client.schedule_meeting(duration=30, window="next-week")
        assert result["success"] is False

    def test_schedule_meeting_calendly_http_400_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calendly returning HTTP 400 → raise_for_status → success=False."""
        monkeypatch.setenv("FTOS_CALENDLY_TOKEN", "tok")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request", request=MagicMock(), response=MagicMock()
        )
        with patch("fine_tuning_os.tools.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.HTTPStatusError = httpx.HTTPStatusError
            result = client.schedule_meeting(duration=30, window="next-week")
        assert result["success"] is False

    def test_request_client_approval_read_fails(
        self, store: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """read_project raises → fail."""
        with patch.object(store, "read_project", side_effect=FileNotFoundError("not found")):
            result = client.request_client_approval(
                project_id="nonexistent",
                question="Q?",
                artifacts=[],
                store=store,
            )
        assert result["success"] is False

    def test_generate_invoice_template_error(self, store: Any, project_id: str) -> None:
        with patch("fine_tuning_os.tools.client.render_template", side_effect=ValueError("bad")):
            result = client.generate_invoice(
                project_id=project_id,
                lines=[{"desc": "x", "qty": 1, "pu": 100, "montant": 100}],
                store=store,
            )
        assert result["success"] is False

    def test_generate_invoice_try_pdf_generic_error(self, store: Any, project_id: str) -> None:
        with patch(
            "fine_tuning_os.tools.client.markdown_file_to_pdf",
            side_effect=RuntimeError("render failed"),
        ):
            result = client.generate_invoice(
                project_id=project_id,
                lines=[{"desc": "x", "qty": 1, "pu": 100, "montant": 100}],
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]
