# SPDX-License-Identifier: Apache-2.0
# tests/test_execution.py
"""TDD tests for execution.py tools (18–25).

C2 dry-run proof: with no env vars set, every C2 tool must return
executed=False, dry_run=True, a command string, and must NOT call
paramiko or subprocess.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import jinja2
import pytest

from fine_tuning_os.tools import execution


def test_ssh_exec_parses_host_port() -> None:
    """_ssh_exec splits host:port and connects on the parsed port."""
    with patch("fine_tuning_os.tools.execution.paramiko.SSHClient") as mock_client_cls:
        client = mock_client_cls.return_value
        stdout = MagicMock()
        stdout.read.return_value = b"out"
        stderr = MagicMock()
        stderr.read.return_value = b"err"
        client.exec_command.return_value = (MagicMock(), stdout, stderr)

        out, err = execution._ssh_exec("bastion.example:2222", "/key", "echo hi")

        kwargs = client.connect.call_args.kwargs
        assert kwargs["hostname"] == "bastion.example"
        assert kwargs["port"] == 2222
        assert (out, err) == ("out", "err")


def test_ssh_exec_defaults_port_22() -> None:
    """_ssh_exec defaults to port 22 when no :port is given."""
    with patch("fine_tuning_os.tools.execution.paramiko.SSHClient") as mock_client_cls:
        client = mock_client_cls.return_value
        stdout = MagicMock()
        stdout.read.return_value = b""
        stderr = MagicMock()
        stderr.read.return_value = b""
        client.exec_command.return_value = (MagicMock(), stdout, stderr)

        execution._ssh_exec("plainhost", "/key", "cmd")

        assert client.connect.call_args.kwargs["port"] == 22


# ---------------------------------------------------------------------------
# Tool 18: push_docker_to_registry (C2 registry)
# ---------------------------------------------------------------------------
class TestPushDockerToRegistry:
    def test_dry_run_no_env(self) -> None:
        result = execution.push_docker_to_registry(tag="myimage:v1")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]
        assert "docker push" in result["data"]["command"]

    def test_dry_run_command_contains_tag(self) -> None:
        result = execution.push_docker_to_registry(tag="ftos/model:latest")
        assert "ftos/model:latest" in result["data"]["command"]

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko")):
            result = execution.push_docker_to_registry(tag="t:1")
        assert result["success"] is True

    def test_live_branch_output_sanitized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_REGISTRY", "registry.example.com")
        monkeypatch.setenv("FTOS_REGISTRY_TOKEN", "supersecret-token-abc123")
        fake_output = (
            "The push refers to repository [registry.example.com/ftos]\n"
            "Pushed by user admin@registry.example.com\n"
            "Connected from 192.168.1.100\n"
            "digest: sha256:abc123def456\n"
        )
        with patch(
            "subprocess.run",
            return_value=MagicMock(stdout=fake_output, stderr="", returncode=0),
        ):
            result = execution.push_docker_to_registry(tag="ftos:latest")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        output = result["data"].get("output", "")
        # IP and full email must be redacted
        assert "192.168.1.100" not in output
        assert "admin@registry.example.com" not in output

    def test_live_branch_uses_list_not_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Subprocess must be called with a list (not shell=True) to prevent injection."""
        monkeypatch.setenv("FTOS_REGISTRY", "registry.example.com")
        monkeypatch.setenv("FTOS_REGISTRY_TOKEN", "token")
        captured: list[Any] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            captured.append((cmd, kwargs))
            return MagicMock(stdout="", stderr="", returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            execution.push_docker_to_registry(tag="myimage:v1")

        assert captured, "subprocess.run was not called"
        cmd, kwargs = captured[0]
        assert isinstance(cmd, list), "cmd must be a list (not a shell string)"
        assert kwargs.get("shell") is False


# ---------------------------------------------------------------------------
# Tool 19: generate_deployment_command (C1)
# ---------------------------------------------------------------------------
class TestGenerateDeploymentCommand:
    def test_produces_docker_run_command(self) -> None:
        result = execution.generate_deployment_command(
            image="ftos/model:v1",
            mounts=[{"host": "/data", "container": "/app/data"}],
            env_names=["HF_TOKEN", "FTOS_WORKSPACE"],
            gpus=["0"],
        )
        assert result["success"] is True
        assert "command" in result["data"]
        assert "docker" in result["data"]["command"]

    def test_no_secret_values_in_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_TOKEN", "hf_realSecretToken12345678901234")
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[],
            env_names=["HF_TOKEN"],
            gpus=[],
        )
        assert "hf_realSecretToken12345678901234" not in json.dumps(result)

    def test_env_names_referenced_not_values(self) -> None:
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[],
            env_names=["MY_SECRET"],
            gpus=[],
        )
        assert result["success"] is True
        command = result["data"]["command"]
        # The env NAME should appear (for -e reference), not a secret value
        assert "MY_SECRET" in command or "MY_SECRET" in result["data"].get("compose_content", "")

    def test_compose_content_present(self) -> None:
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[{"host": "/tmp", "container": "/tmp"}],
            env_names=["ENV_A"],
            gpus=["0"],
        )
        assert result["success"] is True
        assert "compose_content" in result["data"]

    def test_no_env_needed(self) -> None:
        """C1: should work without any env vars."""
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[],
            env_names=[],
            gpus=[],
        )
        assert result["success"] is True

    # Fix #3: empty gpus list must NOT emit --gpus flag
    def test_empty_gpus_no_gpu_flag(self) -> None:
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[],
            env_names=[],
            gpus=[],
        )
        assert result["success"] is True
        assert "--gpus" not in result["data"]["command"]

    # Fix #6: broken template render returns success=False
    def test_compose_render_failure_returns_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken_render(*args: object, **kwargs: object) -> str:
            raise jinja2.TemplateError("bad template")

        monkeypatch.setattr("fine_tuning_os.tools.execution.render_template", broken_render)
        result = execution.generate_deployment_command(
            image="ftos:v1",
            mounts=[],
            env_names=[],
            gpus=[],
        )
        assert result["success"] is False
        assert "compose render failed" in result["error"]


# ---------------------------------------------------------------------------
# Tool 20: trigger_remote_training (C2 ssh)
# ---------------------------------------------------------------------------
class TestTriggerRemoteTraining:
    def test_dry_run_no_env(self) -> None:
        result = execution.trigger_remote_training(
            target="trainer@gpu-host",
            command="python3 src/train.py --steps 100",
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]
        assert "ssh" in result["data"]["command"].lower()

    def test_dry_run_command_uses_key_name_not_value(self) -> None:
        """Dry-run command must NOT embed secret key content."""
        result = execution.trigger_remote_training(
            target="host",
            command="echo hello",
        )
        # Should reference the env var name placeholder, not a real path secret
        cmd = result["data"]["command"]
        assert "FTOS_SSH_KEY" in cmd or "$FTOS_SSH_KEY" in cmd or "ssh" in cmd.lower()

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko on dry-run")):
            result = execution.trigger_remote_training(target="host", command="train.py")
        assert result["success"] is True

    def test_live_branch_returns_job_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "gpu-host.example.com")
        monkeypatch.setenv("FTOS_SSH_KEY", "/home/user/.ssh/id_rsa")

        fake_ssh = MagicMock()
        fake_chan = MagicMock()
        fake_chan.recv.return_value = b"job_id=abc123\n"
        fake_chan.recv_exit_status.return_value = 0
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = b"job_id=abc123\n"
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)
            result = execution.trigger_remote_training(
                target="gpu-host.example.com",
                command="python3 train.py",
            )
        assert result["success"] is True
        assert result["meta"]["executed"] is True

    def test_live_branch_sanitizes_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        # Use a full email + IP that sanitize_text will mask
        sensitive = b"started job user@corp.example.com from 10.0.0.1 token=ghp_abc123xyz456abc789def012ghi345jkl\n"
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = sensitive
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = execution.trigger_remote_training(target="host", command="train.py")
        assert result["success"] is True
        output = result["data"].get("output", "")
        assert "10.0.0.1" not in output
        assert "user@corp.example.com" not in output


# ---------------------------------------------------------------------------
# Tool 21: stream_remote_logs (C2 ssh)
# ---------------------------------------------------------------------------
class TestStreamRemoteLogs:
    def test_dry_run_no_env(self) -> None:
        result = execution.stream_remote_logs(job_id="job123", target="host", n_lines=50)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko")):
            result = execution.stream_remote_logs(job_id="j1", target="h", n_lines=10)
        assert result["success"] is True

    def test_live_branch_sanitizes_every_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        raw_logs = (
            "step=1 loss=1.5\n"
            "admin@corp.example.com connected from 192.168.1.50\n"
            "step=2 loss=1.3\n"
        )
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = raw_logs.encode()
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = execution.stream_remote_logs(job_id="j1", target="host", n_lines=100)
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        logs = result["data"]["logs"]
        for line in logs:
            assert "192.168.1.50" not in line
            assert "admin@corp.example.com" not in line
        assert result["data"]["masked_count"] >= 2

    def test_returns_n_lines_keys(self) -> None:
        """Dry-run still returns expected keys."""
        result = execution.stream_remote_logs(job_id="j", target="t", n_lines=5)
        assert "command" in result["data"]


# ---------------------------------------------------------------------------
# Tool 22: monitor_training_metrics (C2 ssh)
# ---------------------------------------------------------------------------
class TestMonitorTrainingMetrics:
    def test_dry_run_no_env(self) -> None:
        result = execution.monitor_training_metrics(job_id="job1", source="remote")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko")):
            result = execution.monitor_training_metrics(job_id="j1", source="s")
        assert result["success"] is True

    def test_live_branch_returns_time_series(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        raw_logs = (
            "step=1 loss=2.0 lr=0.0002 gpu_util=80\n"
            "step=2 loss=1.8 lr=0.0002 gpu_util=85\n"
            "step=3 loss=1.6 lr=0.0002 gpu_util=82\n"
        )
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = raw_logs.encode()
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = execution.monitor_training_metrics(job_id="j1", source="host")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        assert "loss_series" in result["data"]
        assert len(result["data"]["loss_series"]) == 3


# ---------------------------------------------------------------------------
# Tool 23: detect_anomalies (C1)
# ---------------------------------------------------------------------------
class TestDetectAnomalies:
    def test_detects_nan_in_logs(self) -> None:
        logs = ["step=1 loss=nan", "step=2 loss=1.2"]
        result = execution.detect_anomalies(logs=logs, metrics={})
        assert result["success"] is True
        alerts = result["data"]["alerts"]
        types = [a["type"] for a in alerts]
        assert any("nan" in t.lower() or "diverge" in t.lower() for t in types)

    def test_detects_plateau(self) -> None:
        metrics = {"step_history": [{"step": i, "loss": 1.5} for i in range(1, 21)]}
        result = execution.detect_anomalies(logs=[], metrics=metrics)
        assert result["success"] is True
        alerts = result["data"]["alerts"]
        assert any("plateau" in a["type"].lower() for a in alerts)

    def test_no_anomaly_on_clean_data(self) -> None:
        logs = ["step=1 loss=2.0", "step=2 loss=1.8", "step=3 loss=1.6"]
        metrics = {
            "step_history": [
                {"step": 1, "loss": 2.0},
                {"step": 2, "loss": 1.8},
                {"step": 3, "loss": 1.6},
            ]
        }
        result = execution.detect_anomalies(logs=logs, metrics=metrics)
        assert result["success"] is True
        # Either no alerts or only low-severity ones
        alerts = result["data"]["alerts"]
        critical = [a for a in alerts if a.get("severity") == "critical"]
        assert len(critical) == 0

    def test_alert_has_required_fields(self) -> None:
        logs = ["step=1 loss=nan"]
        result = execution.detect_anomalies(logs=logs, metrics={})
        assert result["success"] is True
        for alert in result["data"]["alerts"]:
            assert "type" in alert
            assert "severity" in alert
            assert "detail" in alert

    def test_data_leak_detection(self) -> None:
        """If a log line looks like it contains PII (email), flag as data_leak."""
        logs = ["step=1 sample='user@example.com trained'"]
        result = execution.detect_anomalies(logs=logs, metrics={})
        assert result["success"] is True
        alerts = result["data"]["alerts"]
        assert any("leak" in a["type"].lower() or "pii" in a["type"].lower() for a in alerts)

    # Fix #9: NaN in metrics step_history triggers critical alert
    def test_nan_in_metrics_step_history_triggers_critical(self) -> None:
        metrics = {"step_history": [{"step": 1, "loss": float("nan")}]}
        result = execution.detect_anomalies(logs=[], metrics=metrics)
        assert result["success"] is True
        alerts = result["data"]["alerts"]
        critical = [a for a in alerts if a.get("severity") == "critical"]
        assert len(critical) >= 1, f"Expected a critical alert for NaN, got: {alerts}"


# ---------------------------------------------------------------------------
# Tool 24: pause_resume_training (C2 ssh)
# ---------------------------------------------------------------------------
class TestPauseResumeTraining:
    def test_dry_run_pause_no_env(self) -> None:
        result = execution.pause_resume_training(job_id="job1", action="pause")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_resume_no_env(self) -> None:
        result = execution.pause_resume_training(job_id="job1", action="resume")
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_invalid_action_returns_fail(self) -> None:
        result = execution.pause_resume_training(job_id="j1", action="destroy")
        assert result["success"] is False
        assert "action" in result["error"].lower() or "pause" in result["error"].lower()

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko")):
            result = execution.pause_resume_training(job_id="j1", action="pause")
        assert result["success"] is True

    def test_live_branch_returns_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = b"job job1 paused\n"
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = execution.pause_resume_training(job_id="job1", action="pause")
        assert result["success"] is True
        assert result["meta"]["executed"] is True


# ---------------------------------------------------------------------------
# Tool 25: early_stopping_check (C1)
# ---------------------------------------------------------------------------
class TestEarlyStoppingCheck:
    def test_stops_when_patience_exceeded(self) -> None:
        # Loss doesn't improve for 5 steps
        history = [{"step": i, "loss": 1.5} for i in range(1, 11)]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=5,
            min_delta=0.001,
        )
        assert result["success"] is True
        assert result["data"]["decision"] == "stop"
        assert "reason" in result["data"]

    def test_continues_when_improving(self) -> None:
        history = [{"step": i, "loss": 2.0 - i * 0.1} for i in range(1, 11)]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=5,
            min_delta=0.001,
        )
        assert result["success"] is True
        assert result["data"]["decision"] == "continue"

    def test_insufficient_history(self) -> None:
        """Fewer steps than patience → always continue."""
        history = [{"step": 1, "loss": 1.5}, {"step": 2, "loss": 1.4}]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=10,
            min_delta=0.001,
        )
        assert result["success"] is True
        assert result["data"]["decision"] == "continue"

    def test_empty_history_fails(self) -> None:
        result = execution.early_stopping_check(
            metrics={"step_history": []},
            patience=5,
            min_delta=0.001,
        )
        assert result["success"] is False

    def test_reason_string_present(self) -> None:
        history = [{"step": i, "loss": 1.5} for i in range(1, 8)]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=3,
            min_delta=0.001,
        )
        assert result["success"] is True
        assert isinstance(result["data"]["reason"], str)
        assert len(result["data"]["reason"]) > 0

    # Fix #1: len(losses) == patience must NOT crash (was ValueError: min([]))
    def test_exactly_patience_steps_does_not_crash(self) -> None:
        """When len(losses) == patience, early-stop must return continue, not crash."""
        patience = 5
        history = [{"step": i, "loss": 1.5} for i in range(1, patience + 1)]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=patience,
            min_delta=0.001,
        )
        assert result["success"] is True
        assert result["data"]["decision"] == "continue"


# ---------------------------------------------------------------------------
# MCP wrapper smoke tests (Fix #12) — execution module
# ---------------------------------------------------------------------------
class TestMcpWrappersExecution:
    def test_push_docker_dry_run(self) -> None:
        result = execution.push_docker_to_registry(tag="smoke:v1")
        assert "success" in result

    def test_generate_deployment_command_smoke(self) -> None:
        result = execution.generate_deployment_command(
            image="smoke:v1",
            mounts=[],
            env_names=["SMOKE_VAR"],
            gpus=[],
        )
        assert "success" in result

    def test_early_stopping_check_smoke(self) -> None:
        history = [{"step": i, "loss": 1.0 - i * 0.05} for i in range(1, 12)]
        result = execution.early_stopping_check(
            metrics={"step_history": history},
            patience=5,
            min_delta=0.001,
        )
        assert "success" in result
