# tests/test_targets.py
import pytest

from fine_tuning_os.targets import gate, resolve_target


def test_resolve_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
    assert resolve_target("slack") is None


def test_resolve_returns_config_when_set(monkeypatch):
    monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.example/abc")
    assert resolve_target("slack") == {"FTOS_SLACK_WEBHOOK": "https://hooks.example/abc"}


def test_resolve_requires_all_vars(monkeypatch):
    monkeypatch.setenv("FTOS_SSH_HOST", "bastion.acme.fr")
    monkeypatch.delenv("FTOS_SSH_KEY", raising=False)
    assert resolve_target("ssh") is None


def test_resolve_empty_string_counts_as_missing(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    assert resolve_target("hf") is None


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        resolve_target("nope")


def test_gate_dry_run_when_unconfigured(monkeypatch):
    monkeypatch.delenv("FTOS_REGISTRY", raising=False)
    monkeypatch.delenv("FTOS_REGISTRY_TOKEN", raising=False)
    configured, meta = gate("registry")
    assert configured is False
    assert meta == {"executed": False, "dry_run": True}


def test_gate_live_when_configured(monkeypatch):
    monkeypatch.setenv("FTOS_REGISTRY", "reg.acme.fr")
    monkeypatch.setenv("FTOS_REGISTRY_TOKEN", "tok")
    configured, meta = gate("registry")
    assert configured is True
    assert meta == {"executed": True, "dry_run": False}
