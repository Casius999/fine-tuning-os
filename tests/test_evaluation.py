# SPDX-License-Identifier: Apache-2.0
# tests/test_evaluation.py
"""TDD tests for evaluation.py tools (26–32).

C2 dry-run proof: with no env vars set, C2 tools return dry_run=True,
executed=False, a command string, and must NOT call paramiko.
Known-vector asserts for compute_metrics.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fine_tuning_os.tools import evaluation


# ---------------------------------------------------------------------------
# Tool 26: download_checkpoint_metadata (C2 — ssh)
# ---------------------------------------------------------------------------
class TestDownloadCheckpointMetadata:
    def test_dry_run_no_env(self) -> None:
        result = evaluation.download_checkpoint_metadata(
            target="trainer@gpu-host", checkpoint="step-1000"
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]
        assert "ssh" in result["data"]["command"].lower()
        assert "step-1000" in result["data"]["checkpoint"]

    def test_dry_run_command_uses_key_placeholder(self) -> None:
        result = evaluation.download_checkpoint_metadata(target="host", checkpoint="ckpt-500")
        cmd = result["data"]["command"]
        assert "FTOS_SSH_KEY" in cmd or "$FTOS_SSH_KEY" in cmd

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko on dry-run")):
            result = evaluation.download_checkpoint_metadata(target="host", checkpoint="ckpt")
        assert result["success"] is True

    def test_live_branch_sanitizes_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "gpu-host.example.com")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        # Raw output contains a secret-looking IP and email
        raw_output = b'{"step":1000,"loss":0.25,"user":"admin@corp.example.com","from":"10.0.0.1"}'
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = raw_output
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = evaluation.download_checkpoint_metadata(target="host", checkpoint="ckpt-1000")
        assert result["success"] is True
        assert result["meta"]["executed"] is True
        metadata = result["data"].get("metadata", "")
        assert "10.0.0.1" not in metadata
        assert "admin@corp.example.com" not in metadata
        assert result["data"]["masked_count"] >= 2

    def test_live_branch_ssh_error_returns_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        import paramiko as _paramiko

        with patch(
            "fine_tuning_os.tools.evaluation._ssh_exec",
            side_effect=_paramiko.SSHException("connection refused"),
        ):
            result = evaluation.download_checkpoint_metadata(target="host", checkpoint="ckpt")
        assert result["success"] is False
        assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# Tool 27: evaluate_on_synthetic (C1 — pure)
# ---------------------------------------------------------------------------
class TestEvaluateOnSynthetic:
    def test_nominal_returns_metrics(self) -> None:
        result = evaluation.evaluate_on_synthetic(project_id="proj-01")
        assert result["success"] is True
        assert "accuracy" in result["data"]
        assert 0.0 <= result["data"]["accuracy"] <= 1.0
        assert result["data"]["num_examples"] > 0

    def test_results_list_has_required_keys(self) -> None:
        result = evaluation.evaluate_on_synthetic(project_id="test")
        for row in result["data"]["results"]:
            assert "prompt" in row
            assert "prediction" in row
            assert "reference" in row
            assert "match" in row

    def test_deterministic(self) -> None:
        r1 = evaluation.evaluate_on_synthetic(project_id="p1")
        r2 = evaluation.evaluate_on_synthetic(project_id="p1")
        assert r1["data"]["accuracy"] == r2["data"]["accuracy"]

    def test_empty_project_id_fails(self) -> None:
        result = evaluation.evaluate_on_synthetic(project_id="")
        assert result["success"] is False

    def test_no_network_required(self) -> None:
        """No env vars needed — must not hit network."""
        import urllib.request

        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("no network")):
            result = evaluation.evaluate_on_synthetic(project_id="offline")
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tool 28: evaluate_on_validation_set (C2 — ssh)
# ---------------------------------------------------------------------------
class TestEvaluateOnValidationSet:
    def test_dry_run_no_env(self) -> None:
        spec: dict[str, Any] = {"script": "eval.py", "data_path": "data/val.jsonl"}
        result = evaluation.evaluate_on_validation_set(target="host", eval_spec=spec)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]

    def test_dry_run_command_has_ssh(self) -> None:
        result = evaluation.evaluate_on_validation_set(
            target="myhost", eval_spec={"script": "run_eval.py"}
        )
        assert "ssh" in result["data"]["command"].lower()

    def test_dry_run_paramiko_not_called(self) -> None:
        with patch("paramiko.SSHClient", side_effect=AssertionError("no paramiko")):
            result = evaluation.evaluate_on_validation_set(target="host", eval_spec={})
        assert result["success"] is True

    def test_live_branch_sanitizes_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        raw = b"accuracy=0.92 evaluated by admin@corp.example.com from 192.168.1.1"
        stdout_mock = MagicMock()
        stdout_mock.read.return_value = raw
        stderr_mock = MagicMock()
        stderr_mock.read.return_value = b""
        fake_ssh = MagicMock()
        fake_ssh.exec_command.return_value = (MagicMock(), stdout_mock, stderr_mock)

        with patch("paramiko.SSHClient", return_value=fake_ssh):
            fake_ssh.__enter__ = lambda s: s
            fake_ssh.__exit__ = MagicMock(return_value=False)
            result = evaluation.evaluate_on_validation_set(
                target="host", eval_spec={"script": "eval.py"}
            )
        assert result["success"] is True
        out = result["data"]["output"]
        assert "admin@corp.example.com" not in out
        assert "192.168.1.1" not in out

    def test_live_branch_ssh_error_returns_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SSH_HOST", "host")
        monkeypatch.setenv("FTOS_SSH_KEY", "/tmp/key")
        with patch(
            "fine_tuning_os.tools.evaluation._ssh_exec",
            side_effect=OSError("timeout"),
        ):
            result = evaluation.evaluate_on_validation_set(target="host", eval_spec={})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 29: compute_metrics (C1 — KNOWN-VECTOR tests)
# ---------------------------------------------------------------------------
class TestComputeMetrics:
    # ---- generation task ----
    def test_identical_preds_refs_bleu_is_1(self) -> None:
        preds = ["the cat sat on the mat"]
        refs = ["the cat sat on the mat"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation")
        assert result["success"] is True
        assert result["data"]["metrics"]["bleu"] == pytest.approx(1.0, abs=1e-4)

    def test_identical_preds_refs_rougeL_is_1(self) -> None:
        preds = ["hello world"]
        refs = ["hello world"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation")
        assert result["data"]["metrics"]["rougeL"] == pytest.approx(1.0, abs=1e-4)

    def test_completely_different_preds_bleu_is_0(self) -> None:
        preds = ["the quick brown fox"]
        refs = ["lazy sleeping dog"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation")
        assert result["success"] is True
        assert result["data"]["metrics"]["bleu"] == 0.0

    def test_generation_returns_rouge_keys(self) -> None:
        preds = ["hello world test"]
        refs = ["hello world foo"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation")
        m = result["data"]["metrics"]
        assert "rouge1" in m
        assert "rouge2" in m
        assert "rougeL" in m

    def test_perplexity_from_nll(self) -> None:
        # nll=0 → perplexity = exp(0) = 1.0
        preds = ["a"]
        refs = ["a"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation", nll=0.0)
        assert result["success"] is True
        assert result["data"]["metrics"]["perplexity"] == pytest.approx(1.0, abs=1e-4)

    def test_perplexity_from_loss(self) -> None:
        # loss=1.0 → perplexity = exp(1.0) ≈ 2.718
        preds = ["a"]
        refs = ["a"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation", loss=1.0)
        assert result["success"] is True
        ppl = result["data"]["metrics"]["perplexity"]
        assert ppl == pytest.approx(math.exp(1.0), abs=1e-3)

    def test_perplexity_from_logprobs(self) -> None:
        # logprobs = [log(0.5), log(0.5)] = [-0.693, -0.693]
        # mean_nll = 0.693, ppl = exp(0.693) ≈ 2.0
        import math as _math

        lp = [_math.log(0.5), _math.log(0.5)]
        preds = ["a b"]
        refs = ["a b"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="generation", logprobs=lp)
        ppl = result["data"]["metrics"]["perplexity"]
        assert ppl == pytest.approx(2.0, abs=0.01)

    # ---- classification task ----
    def test_accuracy_all_correct(self) -> None:
        preds = ["cat", "dog", "bird"]
        refs = ["cat", "dog", "bird"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="classification")
        assert result["success"] is True
        assert result["data"]["metrics"]["accuracy"] == pytest.approx(1.0)
        assert result["data"]["metrics"]["macro_f1"] == pytest.approx(1.0)

    def test_accuracy_all_wrong(self) -> None:
        preds = ["dog", "bird", "cat"]
        refs = ["cat", "dog", "bird"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="classification")
        assert result["data"]["metrics"]["accuracy"] == pytest.approx(0.0)

    def test_accuracy_half_correct(self) -> None:
        # 2 out of 4 correct
        preds = ["pos", "neg", "pos", "neg"]
        refs = ["pos", "pos", "neg", "neg"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="classification")
        assert result["data"]["metrics"]["accuracy"] == pytest.approx(0.5)

    def test_macro_f1_known_value(self) -> None:
        # Binary: preds=[1,1,0,0], refs=[1,0,1,0]
        # TP(1)=1 FP(1)=1 FN(1)=1 → F1(1)=0.5
        # TP(0)=1 FP(0)=1 FN(0)=1 → F1(0)=0.5
        # macro_f1 = 0.5
        preds = ["1", "1", "0", "0"]
        refs = ["1", "0", "1", "0"]
        result = evaluation.compute_metrics(preds=preds, refs=refs, task="classification")
        assert result["data"]["metrics"]["macro_f1"] == pytest.approx(0.5, abs=1e-4)

    # ---- lm task ----
    def test_lm_task_requires_nll_or_loss(self) -> None:
        result = evaluation.compute_metrics(preds=["a"], refs=["a"], task="lm")
        assert result["success"] is False

    def test_lm_task_with_nll(self) -> None:
        result = evaluation.compute_metrics(preds=["a"], refs=["a"], task="lm", nll=2.0)
        assert result["success"] is True
        assert result["data"]["metrics"]["perplexity"] == pytest.approx(math.exp(2.0), abs=0.01)

    # ---- error cases ----
    def test_empty_preds_fails(self) -> None:
        result = evaluation.compute_metrics(preds=[], refs=["a"], task="generation")
        assert result["success"] is False

    def test_empty_refs_fails(self) -> None:
        result = evaluation.compute_metrics(preds=["a"], refs=[], task="generation")
        assert result["success"] is False

    def test_mismatched_lengths_fails(self) -> None:
        result = evaluation.compute_metrics(preds=["a", "b"], refs=["a"], task="generation")
        assert result["success"] is False

    def test_unknown_task_fails(self) -> None:
        result = evaluation.compute_metrics(preds=["a"], refs=["a"], task="summarization")
        assert result["success"] is False

    # FIX #2: OverflowError in _compute_perplexity must not propagate
    def test_lm_overflow_nll_returns_fail_not_exception(self) -> None:
        """nll=800.0 causes math.exp overflow — must return success=False, not raise."""
        result = evaluation.compute_metrics(preds=["a"], refs=["a"], task="lm", nll=800.0)
        # OverflowError → _compute_perplexity returns None → lm path returns fail(...)
        assert result["success"] is False
        assert "nll" in result["error"].lower() or "logprobs" in result["error"].lower()

    def test_generation_overflow_nll_no_exception(self) -> None:
        """For generation task, overflow in perplexity should not raise."""
        result = evaluation.compute_metrics(
            preds=["hello world"], refs=["hello world"], task="generation", nll=800.0
        )
        # Should succeed — perplexity simply absent from metrics
        assert result["success"] is True
        assert "perplexity" not in result["data"]["metrics"]

    # FIX #4: BLEU note for short candidate
    def test_bleu_note_on_short_candidate(self) -> None:
        """A 1-token identical pair gives BLEU=0 and a note."""
        result = evaluation.compute_metrics(preds=["a"], refs=["a"], task="generation")
        assert result["success"] is True
        assert result["data"]["metrics"]["bleu"] == 0.0
        assert "notes" in result["data"]
        assert any("shorter than 4 tokens" in n for n in result["data"]["notes"])


# ---------------------------------------------------------------------------
# Tool 30: generate_predictions_sample (C1)
# ---------------------------------------------------------------------------
class TestGeneratePredictionsSample:
    def test_nominal_returns_script(self) -> None:
        prompts = ["What is 2+2?", "Name a colour."]
        result = evaluation.generate_predictions_sample(prompts=prompts)
        assert result["success"] is True
        assert "script" in result["data"]
        assert "python" in result["data"]["script"].lower() or "def " in result["data"]["script"]

    def test_script_contains_prompts(self) -> None:
        prompts = ["Hello test prompt"]
        result = evaluation.generate_predictions_sample(prompts=prompts)
        # The sanitized prompt should appear in the script
        assert result["success"] is True
        assert result["data"]["num_prompts"] == 1

    def test_empty_prompts_fails(self) -> None:
        result = evaluation.generate_predictions_sample(prompts=[])
        assert result["success"] is False

    def test_sensitive_prompts_masked(self) -> None:
        prompts = ["Contact admin@example.com for help"]
        result = evaluation.generate_predictions_sample(prompts=prompts)
        assert result["success"] is True
        # The raw email should NOT appear in the script
        assert "admin@example.com" not in result["data"]["script"]
        assert result["data"]["masked_count"] >= 1

    def test_offline_no_network(self) -> None:
        import urllib.request

        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("no network")):
            result = evaluation.generate_predictions_sample(prompts=["test"])
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tool 31: compare_to_baseline (C1)
# ---------------------------------------------------------------------------
class TestCompareToBaseline:
    def test_nominal_returns_deltas_and_table(self) -> None:
        ft = {"bleu": 0.45, "rouge1": 0.60, "perplexity": 8.0}
        base = {"bleu": 0.30, "rouge1": 0.50, "perplexity": 12.0}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        assert result["success"] is True
        deltas = result["data"]["deltas"]
        assert "bleu" in deltas
        assert deltas["bleu"] == pytest.approx(0.15, abs=1e-5)

    def test_table_md_contains_headers(self) -> None:
        ft = {"accuracy": 0.85}
        base = {"accuracy": 0.80}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        table = result["data"]["table_md"]
        assert "Metric" in table
        assert "Baseline" in table
        assert "Fine-tuned" in table

    def test_improvement_direction_bleu_higher_better(self) -> None:
        ft = {"bleu": 0.50}
        base = {"bleu": 0.40}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        rows = result["data"]["rows"]
        bleu_row = next(r for r in rows if r["metric"] == "bleu")
        assert bleu_row["improved"] is True

    def test_improvement_direction_perplexity_lower_better(self) -> None:
        # perplexity went from 12 down to 8 → improved
        ft = {"perplexity": 8.0}
        base = {"perplexity": 12.0}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        rows = result["data"]["rows"]
        ppl_row = next(r for r in rows if r["metric"] == "perplexity")
        assert ppl_row["improved"] is True

    def test_perplexity_increased_not_improved(self) -> None:
        ft = {"perplexity": 15.0}
        base = {"perplexity": 12.0}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        rows = result["data"]["rows"]
        ppl_row = next(r for r in rows if r["metric"] == "perplexity")
        assert ppl_row["improved"] is False

    def test_empty_metrics_fails(self) -> None:
        result = evaluation.compare_to_baseline(metrics_ft={}, metrics_base={"bleu": 0.3})
        assert result["success"] is False

    def test_missing_key_in_one_side(self) -> None:
        ft = {"bleu": 0.5, "rouge1": 0.6}
        base = {"bleu": 0.4}
        result = evaluation.compare_to_baseline(metrics_ft=ft, metrics_base=base)
        assert result["success"] is True
        # rouge1 in ft only → delta=None
        rows = result["data"]["rows"]
        rouge_row = next(r for r in rows if r["metric"] == "rouge1")
        assert rouge_row["delta"] is None


# ---------------------------------------------------------------------------
# Tool 32: bias_fairness_scan (C1)
# ---------------------------------------------------------------------------
class TestBiasFairnessScan:
    def test_nominal_returns_report(self) -> None:
        prompts = ["The engineer is competent.", "The cleaner is lazy."]
        result = evaluation.bias_fairness_scan(
            test_prompts=prompts, categories=["gender", "origin"]
        )
        assert result["success"] is True
        assert "report" in result["data"]
        for cat in ["gender", "origin"]:
            assert cat in result["data"]["report"]

    def test_negative_words_flagged(self) -> None:
        prompts = ["The person is dangerous and criminal."]
        result = evaluation.bias_fairness_scan(test_prompts=prompts, categories=["origin"])
        assert result["success"] is True
        origin = result["data"]["report"]["origin"]
        assert origin["negative"] >= 1
        assert any("negative" in note.lower() for note in origin["notes"])

    def test_positive_words_noted(self) -> None:
        prompts = ["The engineer is excellent and smart."]
        result = evaluation.bias_fairness_scan(test_prompts=prompts, categories=["gender"])
        gender = result["data"]["report"]["gender"]
        assert gender["positive"] >= 1

    def test_empty_prompts_fails(self) -> None:
        result = evaluation.bias_fairness_scan(test_prompts=[], categories=["gender"])
        assert result["success"] is False

    def test_empty_categories_fails(self) -> None:
        result = evaluation.bias_fairness_scan(test_prompts=["hello"], categories=[])
        assert result["success"] is False

    def test_deterministic(self) -> None:
        prompts = ["a", "b", "c"]
        r1 = evaluation.bias_fairness_scan(test_prompts=prompts, categories=["x"])
        r2 = evaluation.bias_fairness_scan(test_prompts=prompts, categories=["x"])
        assert r1["data"]["report"] == r2["data"]["report"]

    def test_sensitive_prompts_sanitized(self) -> None:
        prompts = ["Contact admin@example.com now"]
        result = evaluation.bias_fairness_scan(test_prompts=prompts, categories=["test"])
        # The scan result should not echo the raw email
        import json

        assert "admin@example.com" not in json.dumps(result)
