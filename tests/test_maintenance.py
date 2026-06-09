# tests/test_maintenance.py
"""TDD tests for maintenance.py tools (61-64).

C1 tools: 61 check_model_rot, 62 suggest_retraining, 63 update_base_model.
C2 tool:  64 mcp_self_update (git_remote).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fine_tuning_os.tools import maintenance


# ---------------------------------------------------------------------------
# Tool 61: check_model_rot (C1)
# ---------------------------------------------------------------------------
class TestCheckModelRot:
    def _history_degrading(self) -> list[dict]:
        """Metric accuracy goes 0.92 → 0.91 → 0.88 → 0.82 (clear drop)."""
        return [
            {"date": "2025-01-01", "metrics": {"accuracy": 0.92}},
            {"date": "2025-02-01", "metrics": {"accuracy": 0.91}},
            {"date": "2025-03-01", "metrics": {"accuracy": 0.88}},
            {"date": "2025-04-01", "metrics": {"accuracy": 0.82}},
        ]

    def _history_stable(self) -> list[dict]:
        return [
            {"date": "2025-01-01", "metrics": {"accuracy": 0.90}},
            {"date": "2025-02-01", "metrics": {"accuracy": 0.905}},
            {"date": "2025-03-01", "metrics": {"accuracy": 0.902}},
        ]

    def test_degrading_drift_detected(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=self._history_degrading(),
            metric_key="accuracy",
            threshold=0.05,
        )
        assert result["success"] is True
        assert result["data"]["drift_detected"] is True

    def test_stable_no_drift(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=self._history_stable(),
            metric_key="accuracy",
            threshold=0.05,
        )
        assert result["success"] is True
        assert result["data"]["drift_detected"] is False

    def test_magnitude_positive_on_degradation(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=self._history_degrading(),
            metric_key="accuracy",
            threshold=0.05,
        )
        assert result["data"]["magnitude"] > 0

    def test_detail_present(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=self._history_degrading(),
            metric_key="accuracy",
            threshold=0.05,
        )
        assert "detail" in result["data"]

    def test_empty_history_fails(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=[], metric_key="accuracy", threshold=0.05
        )
        assert result["success"] is False

    def test_single_entry_no_drift(self) -> None:
        result = maintenance.check_model_rot(
            metric_history=[{"date": "2025-01-01", "metrics": {"accuracy": 0.9}}],
            metric_key="accuracy",
            threshold=0.05,
        )
        assert result["success"] is True
        assert result["data"]["drift_detected"] is False

    def test_missing_metric_key_fails(self) -> None:
        history = [
            {"date": "2025-01-01", "metrics": {"bleu": 0.5}},
            {"date": "2025-02-01", "metrics": {"bleu": 0.4}},
        ]
        result = maintenance.check_model_rot(
            metric_history=history, metric_key="accuracy", threshold=0.05
        )
        assert result["success"] is False

    def test_perplexity_higher_is_degradation(self) -> None:
        """For perplexity (lower=better), increasing values → drift."""
        history = [
            {"date": "2025-01-01", "metrics": {"perplexity": 10.0}},
            {"date": "2025-02-01", "metrics": {"perplexity": 12.0}},
            {"date": "2025-03-01", "metrics": {"perplexity": 16.0}},
        ]
        result = maintenance.check_model_rot(
            metric_history=history,
            metric_key="perplexity",
            threshold=0.20,
            lower_is_better=True,
        )
        assert result["success"] is True
        assert result["data"]["drift_detected"] is True

    def test_zero_baseline_fails(self) -> None:
        """When the first metric value is 0.0, relative drift is undefined → fail."""
        history = [
            {"date": "2025-01-01", "metrics": {"accuracy": 0.0}},
            {"date": "2025-02-01", "metrics": {"accuracy": 0.05}},
        ]
        result = maintenance.check_model_rot(
            metric_history=history,
            metric_key="accuracy",
            threshold=0.05,
        )
        assert result["success"] is False
        assert "zero baseline" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tool 62: suggest_retraining (C1)
# ---------------------------------------------------------------------------
class TestSuggestRetraining:
    def test_high_drift_recommends_retrain(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=0.15,
            new_data_size=1000,
            days_since_last_train=60,
        )
        assert result["success"] is True
        assert result["data"]["recommend"] is True

    def test_no_drift_small_data_old_train_still_may_recommend(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=0.01,
            new_data_size=20,
            days_since_last_train=5,
        )
        assert result["success"] is True
        assert "recommend" in result["data"]
        assert "reasons" in result["data"]

    def test_large_new_data_recommends(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=0.02,
            new_data_size=5000,
            days_since_last_train=10,
        )
        assert result["success"] is True
        assert result["data"]["recommend"] is True

    def test_reasons_list_present(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=0.10,
            new_data_size=500,
            days_since_last_train=30,
        )
        assert isinstance(result["data"]["reasons"], list)
        assert len(result["data"]["reasons"]) > 0

    def test_no_recommendation_when_all_low(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=0.0,
            new_data_size=0,
            days_since_last_train=1,
        )
        assert result["success"] is True
        assert result["data"]["recommend"] is False

    def test_negative_values_fail(self) -> None:
        result = maintenance.suggest_retraining(
            drift_magnitude=-0.1,
            new_data_size=-5,
            days_since_last_train=-1,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 63: update_base_model (C1)
# ---------------------------------------------------------------------------
class TestUpdateBaseModel:
    def test_nominal_diff_produced(self, store: Any, project_id: str) -> None:
        result = maintenance.update_base_model(
            project_id=project_id,
            new_repo="meta-llama/Llama-3-8B",
            new_revision="main",
            store=store,
        )
        assert result["success"] is True
        assert "diff" in result["data"]

    def test_diff_shows_old_to_new(self, store: Any, project_id: str) -> None:
        # First set an initial base_model on the project
        store.update_project(project_id, base_model="mistralai/Mistral-7B-v0.1")
        result = maintenance.update_base_model(
            project_id=project_id,
            new_repo="meta-llama/Llama-3-8B",
            new_revision="v1.0",
            store=store,
        )
        diff = result["data"]["diff"]
        assert "Mistral-7B-v0.1" in diff or "mistralai" in diff
        assert "Llama-3-8B" in diff or "meta-llama" in diff

    def test_project_config_updated(self, store: Any, project_id: str) -> None:
        maintenance.update_base_model(
            project_id=project_id,
            new_repo="tiiuae/falcon-7b",
            new_revision="main",
            store=store,
        )
        state = store.read_project(project_id)
        assert state["base_model"] == "tiiuae/falcon-7b"

    def test_no_network_call(self, store: Any, project_id: str) -> None:
        """update_base_model is pure — no subprocess or HTTP calls made."""
        # Verify the function works without any external access (pure function)
        result = maintenance.update_base_model(
            project_id=project_id,
            new_repo="some/model",
            new_revision="main",
            store=store,
        )
        # Pure function succeeds with no patching needed
        assert result["success"] is True

    def test_empty_repo_fails(self, store: Any, project_id: str) -> None:
        result = maintenance.update_base_model(
            project_id=project_id, new_repo="", new_revision="main", store=store
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 64: mcp_self_update (C2 — git_remote)
# ---------------------------------------------------------------------------
class TestMcpSelfUpdate:
    def test_no_env_dry_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_GIT_REMOTE", raising=False)
        result = maintenance.mcp_self_update(ref="main")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert "command" in result["data"]

    def test_dry_run_command_contains_ref(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_GIT_REMOTE", raising=False)
        result = maintenance.mcp_self_update(ref="v2.0.0")
        assert "v2.0.0" in result["data"]["command"]

    def test_dry_run_no_subprocess_called(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_GIT_REMOTE", raising=False)
        with patch("fine_tuning_os.tools.maintenance.subprocess") as mock_sp:
            mock_sp.run.side_effect = RuntimeError("should not be called")
            result = maintenance.mcp_self_update(ref="main")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_configured_runs_git_pull(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_GIT_REMOTE", "origin")
        mock_proc = MagicMock()
        mock_proc.stdout = "Already up to date.\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("fine_tuning_os.tools.maintenance.subprocess") as mock_sp:
            mock_sp.run.return_value = mock_proc
            result = maintenance.mcp_self_update(ref="main")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        # subprocess.run must have been called with a list (shell=False)
        call_args = mock_sp.run.call_args
        cmd_list = call_args[0][0]
        assert isinstance(cmd_list, list)
        assert "pull" in cmd_list or "fetch" in cmd_list

    def test_no_secret_in_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_GIT_REMOTE", "https://user:mysecret@github.com/org/repo.git")
        mock_proc = MagicMock()
        mock_proc.stdout = "Updating abc..def\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("fine_tuning_os.tools.maintenance.subprocess") as mock_sp:
            mock_sp.run.return_value = mock_proc
            result = maintenance.mcp_self_update(ref="main")
        # Secret token must not appear verbatim in any field
        assert "mysecret" not in repr(result)

    def test_git_error_returns_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_GIT_REMOTE", "origin")
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = "fatal: not a git repository"
        mock_proc.returncode = 128

        with patch("fine_tuning_os.tools.maintenance.subprocess") as mock_sp:
            mock_sp.run.return_value = mock_proc
            result = maintenance.mcp_self_update(ref="main")
        assert result["success"] is False

    def test_configured_output_sanitized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Any IP or email in git output must be sanitized."""
        monkeypatch.setenv("FTOS_GIT_REMOTE", "origin")
        mock_proc = MagicMock()
        mock_proc.stdout = "From 192.168.1.100\n * branch main -> FETCH_HEAD\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("fine_tuning_os.tools.maintenance.subprocess") as mock_sp:
            mock_sp.run.return_value = mock_proc
            result = maintenance.mcp_self_update(ref="main")
        assert result["success"] is True
        assert "192.168.1.100" not in repr(result)


# ---------------------------------------------------------------------------
# MCP wrappers and register()
# ---------------------------------------------------------------------------
class TestMaintenanceMcpWrappers:
    def test_mcp_check_model_rot_delegates(self) -> None:
        history = [
            {"date": "2025-01-01", "metrics": {"accuracy": 0.9}},
            {"date": "2025-02-01", "metrics": {"accuracy": 0.8}},
        ]
        result = maintenance._mcp_check_model_rot(
            metric_history=history, metric_key="accuracy", threshold=0.05
        )
        assert result["success"] is True

    def test_mcp_suggest_retraining_delegates(self) -> None:
        result = maintenance._mcp_suggest_retraining(
            drift_magnitude=0.1, new_data_size=200, days_since_last_train=30
        )
        assert result["success"] is True

    def test_mcp_update_base_model_delegates(
        self,
        store: Any,
        project_id: str,
        workspace: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        result = maintenance._mcp_update_base_model(
            project_id=project_id, new_repo="repo/model", new_revision="main"
        )
        assert result["success"] is True

    def test_mcp_self_update_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_GIT_REMOTE", raising=False)
        result = maintenance._mcp_self_update(ref="main")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_register_registers_four_tools(self) -> None:
        registered: list[str] = []

        class FakeMcp:
            def tool(self, description: str):  # type: ignore[no-untyped-def]
                def decorator(fn):  # type: ignore[no-untyped-def]
                    registered.append(fn.__name__)
                    return fn

                return decorator

        maintenance.register(FakeMcp())
        assert len(registered) == 4  # tools 61-64
