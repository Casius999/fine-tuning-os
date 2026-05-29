# tests/test_server.py
from fine_tuning_os import server


def test_health_reports_name_and_version(monkeypatch, tmp_path):
    monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path / "ws"))
    out = server.ftos_health()
    assert out["success"] is True
    assert out["data"]["name"] == "fine-tuning-os"
    assert out["data"]["version"] == server.__version__
    assert out["data"]["workspace"].endswith("ws")


def test_health_targets_are_booleans_no_secrets(monkeypatch):
    monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")
    out = server.ftos_health()
    targets = out["data"]["targets_configured"]
    assert targets["slack"] is False
    assert targets["hf"] is True
    # the secret value must never appear anywhere in the response
    assert "hf_secret_value" not in repr(out)


def test_mcp_instance_named():
    assert server.mcp.name == "fine-tuning-os"
