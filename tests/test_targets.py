# tests/test_targets.py
import pytest

from fine_tuning_os.targets import _get_target_config, gate, resolve_target


def test_resolve_returns_false_when_unset(monkeypatch):
    monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
    assert resolve_target("slack") is False


def test_resolve_returns_true_when_set(monkeypatch):
    monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.example/abc")
    assert resolve_target("slack") is True


def test_resolve_requires_all_vars(monkeypatch):
    monkeypatch.setenv("FTOS_SSH_HOST", "bastion.acme.fr")
    monkeypatch.delenv("FTOS_SSH_KEY", raising=False)
    assert resolve_target("ssh") is False


def test_resolve_empty_string_counts_as_missing(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    assert resolve_target("hf") is False


def test_resolve_never_returns_secret_values(monkeypatch):
    # Zero-Data: the public resolver exposes presence only, never the value.
    monkeypatch.setenv("FTOS_CALENDLY_TOKEN", "super-secret")
    result = resolve_target("calendly")
    assert result is True
    assert "super-secret" not in repr(result)


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        resolve_target("nope")


def test_get_target_config_returns_values_when_set(monkeypatch):
    monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.example/abc")
    assert _get_target_config("slack") == {"FTOS_SLACK_WEBHOOK": "https://hooks.example/abc"}


def test_get_target_config_none_when_partial(monkeypatch):
    monkeypatch.setenv("FTOS_SSH_HOST", "bastion.acme.fr")
    monkeypatch.delenv("FTOS_SSH_KEY", raising=False)
    assert _get_target_config("ssh") is None


def test_get_target_config_unknown_kind_raises():
    with pytest.raises(ValueError):
        _get_target_config("nope")


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
