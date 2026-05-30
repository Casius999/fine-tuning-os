# tests/test_pipeline.py
"""TDD tests for pipeline.py tools (11–17).

C2 dry-run proof: with no env vars set, every C2 tool must return
executed=False, dry_run=True, a command string, and must NOT call
subprocess or Docker.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fine_tuning_os.store import Store
from fine_tuning_os.tools import pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init(tmp_path: Path, project_id: str = "p1") -> tuple[Store, str]:
    s = Store(root=tmp_path)
    s.init_project(project_id, "ACME")
    return s, project_id


# ---------------------------------------------------------------------------
# Tool 11: build_docker_image
# ---------------------------------------------------------------------------
class TestBuildDockerImage:
    def test_dry_run_no_env(self, tmp_path: Path) -> None:
        """Without env vars, returns dry_run=True, executed=False, command present."""
        store, pid = _init(tmp_path)
        result = pipeline.build_docker_image(
            project_id=pid,
            base_image="nvidia/cuda:12.1.0-base-ubuntu22.04",
            tag="my-project:latest",
            store=store,
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]
        assert "docker build" in result["data"]["command"]
        assert "dockerfile_path" in result["data"]

    def test_dry_run_command_contains_tag(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.build_docker_image(
            project_id=pid,
            base_image="nvidia/cuda:12.1.0-base-ubuntu22.04",
            tag="ftos:test",
            store=store,
        )
        assert "ftos:test" in result["data"]["command"]

    def test_dry_run_renders_dockerfile(self, tmp_path: Path) -> None:
        """Dockerfile should be rendered and saved to project/docker/ even on dry-run."""
        store, pid = _init(tmp_path)
        result = pipeline.build_docker_image(
            project_id=pid,
            base_image="nvidia/cuda:12.1.0-base-ubuntu22.04",
            tag="ftos:v1",
            store=store,
        )
        assert result["success"] is True
        dockerfile_path = Path(result["data"]["dockerfile_path"])
        assert dockerfile_path.exists()
        content = dockerfile_path.read_text()
        assert "nvidia/cuda:12.1.0-base-ubuntu22.04" in content

    def test_dry_run_docker_not_called(self, tmp_path: Path) -> None:
        """subprocess.run must NOT be called on dry-run path."""
        store, pid = _init(tmp_path)
        with patch("subprocess.run", side_effect=AssertionError("should not call subprocess")):
            result = pipeline.build_docker_image(
                project_id=pid,
                base_image="nginx",
                tag="t:1",
                store=store,
            )
        assert result["success"] is True

    def test_cache_models_flag(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.build_docker_image(
            project_id=pid,
            base_image="ubuntu:22.04",
            tag="t:cache",
            cache_models=True,
            store=store,
        )
        assert result["success"] is True
        dockerfile_path = Path(result["data"]["dockerfile_path"])
        assert (
            "cache" in dockerfile_path.read_text().lower()
            or "MODEL_CACHE" in dockerfile_path.read_text()
        )


# ---------------------------------------------------------------------------
# Tool 12: test_docker_build
# ---------------------------------------------------------------------------
class TestTestDockerBuild:
    def test_dry_run_no_env(self, tmp_path: Path) -> None:
        result = pipeline.test_docker_build(image_tag="ftos:latest")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_command_has_pytest(self, tmp_path: Path) -> None:
        result = pipeline.test_docker_build(image_tag="ftos:latest")
        assert "pytest" in result["data"]["command"] or "docker" in result["data"]["command"]

    def test_dry_run_subprocess_not_called(self, tmp_path: Path) -> None:
        with patch("subprocess.run", side_effect=AssertionError("should not call subprocess")):
            result = pipeline.test_docker_build(image_tag="ftos:test")
        assert result["success"] is True

    def test_live_branch_sanitized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With local_python + docker configured, output must be sanitized."""
        monkeypatch.setenv("FTOS_LOCAL_PYTHON", "/usr/bin/python3")
        # Use a full email address that sanitize_text's EMAIL_RE will match
        fake_output = "test passed\ncontact admin@corp.example.com for access\n"
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch(
                "subprocess.run",
                return_value=MagicMock(stdout=fake_output, stderr="", returncode=0),
            ),
        ):
            result = pipeline.test_docker_build(image_tag="ftos:live")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        # The email address should be redacted
        output = result["data"].get("output", "")
        assert "admin@corp.example.com" not in output


# ---------------------------------------------------------------------------
# Tool 13: run_local_synthetic_train
# ---------------------------------------------------------------------------
class TestRunLocalSyntheticTrain:
    def test_dry_run_no_env(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.run_local_synthetic_train(project_id=pid, store=store)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_renders_train_script(self, tmp_path: Path) -> None:
        """train.py should be rendered even on dry-run."""
        store, pid = _init(tmp_path)
        result = pipeline.run_local_synthetic_train(project_id=pid, store=store)
        assert result["success"] is True
        train_path = tmp_path / pid / "src" / "train.py"
        assert train_path.exists()

    def test_dry_run_subprocess_not_called(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        with patch("subprocess.run", side_effect=AssertionError("no subprocess on dry-run")):
            result = pipeline.run_local_synthetic_train(project_id=pid, store=store)
        assert result["success"] is True

    def test_live_branch_returns_metrics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With FTOS_LOCAL_PYTHON set, subprocess runs and returns sanitized metrics."""
        store, pid = _init(tmp_path)
        monkeypatch.setenv("FTOS_LOCAL_PYTHON", "/usr/bin/python3")
        fake_output = json.dumps({"final_loss": 1.23, "steps": 5}) + "\n"
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout=fake_output, stderr="", returncode=0),
        ):
            result = pipeline.run_local_synthetic_train(project_id=pid, steps=5, store=store)
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        assert "output" in result["data"]

    def test_live_branch_sanitizes_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store, pid = _init(tmp_path)
        monkeypatch.setenv("FTOS_LOCAL_PYTHON", "/usr/bin/python3")
        sensitive = "loss=0.5 user@secret-corp.com step=1\n"
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout=sensitive, stderr="", returncode=0),
        ):
            result = pipeline.run_local_synthetic_train(project_id=pid, steps=2, store=store)
        assert result["success"] is True
        assert "user@secret-corp.com" not in result["data"].get("output", "")

    def test_steps_default(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.run_local_synthetic_train(project_id=pid, store=store)
        assert result["success"] is True
        assert "10" in result["data"]["command"]  # default 10 steps


# ---------------------------------------------------------------------------
# Tool 14: get_local_metrics
# ---------------------------------------------------------------------------
class TestGetLocalMetrics:
    def test_returns_metrics_when_file_exists(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        metrics = {"steps": 10, "final_loss": 0.5, "avg_time_per_step_s": 0.01}
        metrics_file = tmp_path / pid / "outputs" / "metrics.json"
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        metrics_file.write_text(json.dumps(metrics), encoding="utf-8")

        result = pipeline.get_local_metrics(project_id=pid, store=store)
        assert result["success"] is True
        assert result["data"]["steps"] == 10
        assert result["data"]["final_loss"] == 0.5

    def test_fails_when_no_metrics_file(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.get_local_metrics(project_id=pid, store=store)
        assert result["success"] is False
        assert "metrics" in result["error"].lower() or "not found" in result["error"].lower()

    def test_fails_on_invalid_json(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        metrics_file = tmp_path / pid / "outputs" / "metrics.json"
        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        metrics_file.write_text("not-json", encoding="utf-8")
        result = pipeline.get_local_metrics(project_id=pid, store=store)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 15: dry_run_remote_config
# ---------------------------------------------------------------------------
class TestDryRunRemoteConfig:
    def test_all_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_VAR_1", "value1")
        monkeypatch.setenv("MY_VAR_2", "value2")
        result = pipeline.dry_run_remote_config(
            deployment_spec={"env_names": ["MY_VAR_1", "MY_VAR_2"], "mount_points": []}
        )
        assert result["success"] is True
        assert "MY_VAR_1" in result["data"]["ok"]
        assert "MY_VAR_2" in result["data"]["ok"]
        assert result["data"]["missing"] == []

    def test_some_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NOT_SET_VAR", raising=False)
        monkeypatch.setenv("IS_SET_VAR", "yes")
        result = pipeline.dry_run_remote_config(
            deployment_spec={"env_names": ["IS_SET_VAR", "NOT_SET_VAR"], "mount_points": []}
        )
        assert result["success"] is True
        assert "NOT_SET_VAR" in result["data"]["missing"]
        assert "IS_SET_VAR" in result["data"]["ok"]

    def test_never_returns_secret_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_KEY", "super-secret-value-12345")
        result = pipeline.dry_run_remote_config(
            deployment_spec={"env_names": ["SECRET_KEY"], "mount_points": []}
        )
        assert "super-secret-value-12345" not in json.dumps(result)

    def test_empty_spec(self) -> None:
        result = pipeline.dry_run_remote_config(deployment_spec={})
        assert result["success"] is True
        assert result["data"]["ok"] == []
        assert result["data"]["missing"] == []


# ---------------------------------------------------------------------------
# Tool 16: optimize_hyperparams
# ---------------------------------------------------------------------------
class TestOptimizeHyperparams:
    def test_plateau_suggests_lr_change(self) -> None:
        # Flat loss = plateau
        metrics = {
            "step_history": [{"step": i, "loss": 1.5} for i in range(1, 21)],
            "final_loss": 1.5,
        }
        result = pipeline.optimize_hyperparams(metrics=metrics)
        assert result["success"] is True
        assert "proposed_config" in result["data"]
        justification = " ".join(result["data"].get("justifications", []))
        assert "plateau" in justification.lower() or "lr" in justification.lower()

    def test_good_convergence_no_critical_suggestion(self) -> None:
        history = [{"step": i, "loss": 2.0 * (0.8**i)} for i in range(1, 11)]
        metrics = {"step_history": history, "final_loss": history[-1]["loss"]}
        result = pipeline.optimize_hyperparams(metrics=metrics)
        assert result["success"] is True

    def test_nan_loss_handled(self) -> None:
        metrics = {"step_history": [{"step": 1, "loss": float("nan")}], "final_loss": float("nan")}
        result = pipeline.optimize_hyperparams(metrics=metrics)
        assert result["success"] is True
        justification = " ".join(result["data"].get("justifications", []))
        assert "nan" in justification.lower() or "diverge" in justification.lower()

    def test_output_has_required_keys(self) -> None:
        metrics = {
            "step_history": [{"step": i, "loss": 1.0 - i * 0.05} for i in range(1, 6)],
            "final_loss": 0.75,
        }
        result = pipeline.optimize_hyperparams(metrics=metrics)
        assert "proposed_config" in result["data"]
        assert "justifications" in result["data"]


# ---------------------------------------------------------------------------
# Tool 17: generate_unit_tests
# ---------------------------------------------------------------------------
class TestGenerateUnitTests:
    def test_creates_test_file(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.generate_unit_tests(
            project_id=pid,
            targets=["train", "split_dataset"],
            store=store,
        )
        assert result["success"] is True
        assert "file_paths" in result["data"]
        for fp in result["data"]["file_paths"]:
            assert Path(fp).exists()

    def test_test_file_contains_pytest_imports(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.generate_unit_tests(
            project_id=pid,
            targets=["train"],
            store=store,
        )
        assert result["success"] is True
        for fp in result["data"]["file_paths"]:
            content = Path(fp).read_text()
            assert "pytest" in content or "import" in content

    def test_no_targets_returns_fail(self, tmp_path: Path) -> None:
        store, pid = _init(tmp_path)
        result = pipeline.generate_unit_tests(
            project_id=pid,
            targets=[],
            store=store,
        )
        assert result["success"] is False
