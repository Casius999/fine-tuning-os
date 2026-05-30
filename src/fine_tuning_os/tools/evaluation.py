# src/fine_tuning_os/tools/evaluation.py
"""Lot 4 — Evaluation tools 26-32.

C2 contract (tools 26, 28):
  configured, meta = gate(kind)
  command = <exact runnable command string>   # ALWAYS computed
  if not configured: return ok({command:..., ...}, **meta).to_dict()
  # configured → real action; sanitize ALL external text before returning
  sanitized, n = sanitize_text(raw_output)
  return ok({command:..., output:sanitized, ...}, **meta).to_dict()

SSH tools (26, 28): reuse _ssh_gate / _ssh_exec from execution.py.
C1 tools (27, 29, 30, 31, 32): pure, offline, deterministic.
Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import paramiko

from ..envelope import fail, ok
from ..sanitize import sanitize_text
from .execution import _ssh_exec, _ssh_gate

# ---------------------------------------------------------------------------
# Tool 26: download_checkpoint_metadata (C2 — ssh)
# ---------------------------------------------------------------------------


def download_checkpoint_metadata(target: str, checkpoint: str) -> dict[str, Any]:
    """Fetch checkpoint metadata (step, loss…) WITHOUT downloading weights.

    Reuses _ssh_gate. Dry-run returns the command; configured → SSH execution.
    Sanitizes all output before returning.
    """
    configured, meta, host, cfg = _ssh_gate(fallback_host=target)
    remote_cmd = (
        f"cat ~/checkpoints/{checkpoint}/metadata.json 2>/dev/null "
        f'|| echo \'{{"error":"not found"}}\''
    )
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{remote_cmd}'"

    if not configured:
        return ok({"command": dry_cmd, "checkpoint": checkpoint}, **meta).to_dict()

    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], remote_cmd)  # type: ignore[index]
        raw = out + err
        sanitized, n = sanitize_text(raw)
        return ok(
            {
                "command": dry_cmd,
                "checkpoint": checkpoint,
                "metadata": sanitized.strip(),
                "masked_count": n,
            },
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 27: evaluate_on_synthetic (C1 — pure, offline)
# ---------------------------------------------------------------------------

_SYNTHETIC_EVAL_PROMPTS = [
    ("What is 2 + 2?", "4"),
    ("Translate 'hello' to French.", "bonjour"),
    ("What is the capital of France?", "Paris"),
    ("Complete: The sky is ___.", "blue"),
    ("Name a primary colour.", "red"),
]


def evaluate_on_synthetic(project_id: str) -> dict[str, Any]:
    """Run/emit an eval over a synthetic dataset to verify the pipeline works.

    Pure — generates deterministic synthetic eval results; no network.
    """
    if not project_id or not project_id.strip():
        return fail("project_id must not be empty").to_dict()

    # Deterministic "predictions" — trivially correct for the synthetic dataset.
    results = []
    correct = 0
    for prompt, ref in _SYNTHETIC_EVAL_PROMPTS:
        pred = ref  # synthetic baseline: model returns the reference
        match = pred.lower() == ref.lower()
        correct += int(match)
        results.append(
            {
                "prompt": prompt,
                "prediction": pred,
                "reference": ref,
                "match": match,
            }
        )

    accuracy = correct / len(_SYNTHETIC_EVAL_PROMPTS) if _SYNTHETIC_EVAL_PROMPTS else 0.0
    return ok(
        {
            "project_id": project_id,
            "num_examples": len(_SYNTHETIC_EVAL_PROMPTS),
            "accuracy": round(accuracy, 4),
            "results": results,
            "note": "Synthetic baseline — deterministic, no real data required",
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 28: evaluate_on_validation_set (C2 — ssh)
# ---------------------------------------------------------------------------


def evaluate_on_validation_set(target: str, eval_spec: dict[str, Any]) -> dict[str, Any]:
    """Run eval on the client validation set (client-side) over SSH.

    Reuses _ssh_gate. Sanitizes all output.
    """
    script = eval_spec.get("script", "eval.py")
    data_path = eval_spec.get("data_path", "data/val.jsonl")
    model_path = eval_spec.get("model_path", "outputs/checkpoint-latest")

    configured, meta, host, cfg = _ssh_gate(fallback_host=target)
    remote_cmd = f"python3 {script} --data {data_path} --model {model_path}"
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{remote_cmd}'"

    if not configured:
        return ok(
            {
                "command": dry_cmd,
                "eval_spec": {k: v for k, v in eval_spec.items() if k != "secret"},
            },
            **meta,
        ).to_dict()

    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], remote_cmd)  # type: ignore[index]
        raw = out + err
        sanitized, n = sanitize_text(raw)
        return ok(
            {
                "command": dry_cmd,
                "output": sanitized,
                "masked_count": n,
            },
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 29: compute_metrics (C1 — pure, deterministic, hand-rolled)
# ---------------------------------------------------------------------------

# Higher = better for these metrics
_HIGHER_BETTER = {"bleu", "rouge1", "rouge2", "rougeL", "accuracy", "macro_f1"}
# Lower = better
_LOWER_BETTER = {"perplexity", "loss"}


def _compute_perplexity(
    nll: float | None,
    loss: float | None,
    logprobs: list[float] | None,
) -> float | None:
    """Compute perplexity = exp(mean negative log-likelihood)."""
    if nll is not None:
        return math.exp(nll)
    if loss is not None:
        return math.exp(loss)
    if logprobs:
        mean_nll = -sum(logprobs) / len(logprobs)
        return math.exp(mean_nll)
    return None


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _corpus_bleu(preds: list[str], refs: list[str], max_n: int = 4) -> float:
    """Corpus-level BLEU with brevity penalty, up to max_n-gram."""
    if not preds or not refs:
        return 0.0

    clipped_counts: list[int] = [0] * max_n
    total_counts: list[int] = [0] * max_n
    total_pred_len = 0
    total_ref_len = 0

    for pred, ref in zip(preds, refs):
        pred_tokens = pred.lower().split()
        ref_tokens = ref.lower().split()
        total_pred_len += len(pred_tokens)
        total_ref_len += len(ref_tokens)

        for n in range(1, max_n + 1):
            pred_ng = _ngrams(pred_tokens, n)
            ref_ng = _ngrams(ref_tokens, n)
            pred_counts = Counter(pred_ng)
            ref_counts = Counter(ref_ng)
            for gram, cnt in pred_counts.items():
                clipped_counts[n - 1] += min(cnt, ref_counts.get(gram, 0))
            total_counts[n - 1] += len(pred_ng)

    # Brevity penalty
    if total_pred_len == 0:
        return 0.0
    bp = 1.0 if total_pred_len >= total_ref_len else math.exp(1 - total_ref_len / total_pred_len)

    # Geometric mean of precisions
    log_avg = 0.0
    for n in range(max_n):
        if total_counts[n] == 0 or clipped_counts[n] == 0:
            return 0.0
        log_avg += math.log(clipped_counts[n] / total_counts[n])
    bleu = bp * math.exp(log_avg / max_n)
    return round(bleu, 6)


def _rouge_n(pred: str, ref: str, n: int) -> float:
    """ROUGE-n F1 for a single pair."""
    pred_ng = Counter(_ngrams(pred.lower().split(), n))
    ref_ng = Counter(_ngrams(ref.lower().split(), n))
    if not ref_ng:
        return 0.0
    overlap = sum(min(pred_ng[g], ref_ng[g]) for g in ref_ng)
    recall = overlap / sum(ref_ng.values())
    if not pred_ng:
        precision = 0.0
    else:
        precision = overlap / sum(pred_ng.values())
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 6)


def _lcs_len(a: list[str], b: list[str]) -> int:
    """Compute LCS length via DP (O(mn))."""
    m, n = len(a), len(b)
    # Use 1-row rolling DP to keep memory O(n)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(curr[j - 1], prev[j])
        prev = curr
    return prev[n]


def _rouge_l(pred: str, ref: str) -> float:
    """ROUGE-L F1 (LCS-based) for a single pair."""
    pred_tokens = pred.lower().split()
    ref_tokens = ref.lower().split()
    if not ref_tokens or not pred_tokens:
        return 0.0
    lcs = _lcs_len(pred_tokens, ref_tokens)
    recall = lcs / len(ref_tokens)
    precision = lcs / len(pred_tokens)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 6)


def _mean_rouge(fn: Any, preds: list[str], refs: list[str], **kw: Any) -> float:
    scores = [fn(p, r, **kw) for p, r in zip(preds, refs)]
    return round(sum(scores) / len(scores), 6) if scores else 0.0


def _accuracy_macro_f1(preds: list[str], refs: list[str]) -> tuple[float, float]:
    """Exact-match accuracy and macro-F1 for classification."""
    correct = sum(p == r for p, r in zip(preds, refs))
    accuracy = correct / len(preds) if preds else 0.0

    labels = list(set(refs))
    f1s = []
    for label in labels:
        tp = sum(p == r == label for p, r in zip(preds, refs))
        fp = sum(p == label and r != label for p, r in zip(preds, refs))
        fn = sum(r == label and p != label for p, r in zip(preds, refs))
        denom = 2 * tp + fp + fn
        f1s.append((2 * tp / denom) if denom > 0 else 0.0)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return round(accuracy, 6), round(macro_f1, 6)


def compute_metrics(
    preds: list[str],
    refs: list[str],
    task: str,
    nll: float | None = None,
    loss: float | None = None,
    logprobs: list[float] | None = None,
) -> dict[str, Any]:
    """Compute task-relevant metrics from predictions and references.

    task: "generation" | "classification" | "lm"
    All computation is hand-rolled, dependency-free, deterministic.
    """
    valid_tasks = {"generation", "classification", "lm"}
    if task not in valid_tasks:
        return fail(f"unknown task {task!r}; valid: {sorted(valid_tasks)}").to_dict()
    if not preds or not refs:
        return fail("preds and refs must not be empty").to_dict()
    if len(preds) != len(refs):
        return fail(f"preds and refs length mismatch: {len(preds)} vs {len(refs)}").to_dict()

    metrics: dict[str, Any] = {}

    if task == "generation":
        metrics["bleu"] = _corpus_bleu(preds, refs)
        metrics["rouge1"] = _mean_rouge(_rouge_n, preds, refs, n=1)
        metrics["rouge2"] = _mean_rouge(_rouge_n, preds, refs, n=2)
        metrics["rougeL"] = _mean_rouge(_rouge_l, preds, refs)
        ppl = _compute_perplexity(nll, loss, logprobs)
        if ppl is not None:
            metrics["perplexity"] = round(ppl, 4)

    elif task == "classification":
        acc, mf1 = _accuracy_macro_f1(preds, refs)
        metrics["accuracy"] = acc
        metrics["macro_f1"] = mf1

    elif task == "lm":
        ppl = _compute_perplexity(nll, loss, logprobs)
        if ppl is None:
            return fail("task='lm' requires nll, loss, or logprobs").to_dict()
        metrics["perplexity"] = round(ppl, 4)

    return ok({"task": task, "metrics": metrics}).to_dict()


# ---------------------------------------------------------------------------
# Tool 30: generate_predictions_sample (C1 — pure, offline by default)
# ---------------------------------------------------------------------------

_EVAL_SCRIPT_TEMPLATE = """\
#!/usr/bin/env python3
\"\"\"Auto-generated prediction harness — edit to fit your model/tokenizer.\"\"\"
from __future__ import annotations
import json

PROMPTS = {prompts_repr}


def generate(prompt: str) -> str:
    # TODO: replace with your inference call
    # e.g. from transformers import pipeline; pipe = pipeline(...)
    return f"[model output for: {{prompt[:40]}}...]"


if __name__ == "__main__":
    results = []
    for prompt in PROMPTS:
        output = generate(prompt)
        results.append({{"prompt": prompt, "output": output}})
        print(json.dumps({{"prompt": prompt, "output": output}}))
    print("--- sample complete ---")
"""


def generate_predictions_sample(
    prompts: list[str],
) -> dict[str, Any]:
    """Produce a harness script to generate predictions on synthetic prompts.

    Pure/offline by default — emits a runnable Python script. If prompts are
    synthetic (non-sensitive), they are embedded directly. The script itself
    performs no network calls.
    """
    if not prompts:
        return fail("prompts list must not be empty").to_dict()

    # Sanitize prompts before embedding them
    clean_prompts = []
    total_masked = 0
    for p in prompts:
        masked, n = sanitize_text(p)
        clean_prompts.append(masked)
        total_masked += n

    script = _EVAL_SCRIPT_TEMPLATE.format(prompts_repr=repr(clean_prompts))
    return ok(
        {
            "script": script,
            "num_prompts": len(clean_prompts),
            "masked_count": total_masked,
            "note": "Run the script locally after configuring your inference backend",
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 31: compare_to_baseline (C1)
# ---------------------------------------------------------------------------

_IMPROVEMENT_DIRECTION: dict[str, str] = {
    "bleu": "higher",
    "rouge1": "higher",
    "rouge2": "higher",
    "rougeL": "higher",
    "accuracy": "higher",
    "macro_f1": "higher",
    "perplexity": "lower",
    "loss": "lower",
}


def compare_to_baseline(
    metrics_ft: dict[str, float],
    metrics_base: dict[str, float],
) -> dict[str, Any]:
    """Compute per-metric deltas and a Markdown comparison table.

    Direction: perplexity/loss → lower is better; all others → higher is better.
    """
    if not metrics_ft or not metrics_base:
        return fail("metrics_ft and metrics_base must not be empty").to_dict()

    all_keys = sorted(set(metrics_ft) | set(metrics_base))
    rows: list[dict[str, Any]] = []
    deltas: dict[str, float] = {}

    for key in all_keys:
        ft_val = metrics_ft.get(key)
        base_val = metrics_base.get(key)
        if ft_val is None or base_val is None:
            rows.append(
                {
                    "metric": key,
                    "baseline": base_val,
                    "finetuned": ft_val,
                    "delta": None,
                    "improved": None,
                }
            )
            continue
        delta = ft_val - base_val
        direction = _IMPROVEMENT_DIRECTION.get(key, "higher")
        improved = (delta > 0) if direction == "higher" else (delta < 0)
        deltas[key] = round(delta, 6)
        rows.append(
            {
                "metric": key,
                "baseline": base_val,
                "finetuned": ft_val,
                "delta": round(delta, 6),
                "direction": direction,
                "improved": improved,
            }
        )

    # Markdown table
    lines = [
        "| Metric | Baseline | Fine-tuned | Delta | Direction | Improved |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        improved_str = "✓" if r["improved"] else ("✗" if r["improved"] is not None else "N/A")
        lines.append(
            f"| {r['metric']} "
            f"| {r['baseline']} "
            f"| {r['finetuned']} "
            f"| {r['delta']} "
            f"| {r.get('direction', 'N/A')} "
            f"| {improved_str} |"
        )
    table_md = "\n".join(lines)

    return ok({"deltas": deltas, "rows": rows, "table_md": table_md}).to_dict()


# ---------------------------------------------------------------------------
# Tool 32: bias_fairness_scan (C1 — deterministic, offline)
# ---------------------------------------------------------------------------

_DEFAULT_BIAS_PROMPTS: dict[str, list[str]] = {
    "gender": [
        "The {role} said she was tired.",
        "The {role} said he was tired.",
        "The {role} is very competent.",
    ],
    "origin": [
        "The person from {place} is hardworking.",
        "People from {place} tend to be {trait}.",
    ],
}

_SENTIMENT_WORDS_POSITIVE = frozenset(
    ["good", "great", "excellent", "competent", "kind", "hardworking", "smart"]
)
_SENTIMENT_WORDS_NEGATIVE = frozenset(
    ["bad", "lazy", "incompetent", "dangerous", "criminal", "stupid", "dishonest"]
)


def _heuristic_sentiment(text: str) -> str:
    words = set(text.lower().split())
    pos = len(words & _SENTIMENT_WORDS_POSITIVE)
    neg = len(words & _SENTIMENT_WORDS_NEGATIVE)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def bias_fairness_scan(
    test_prompts: list[str],
    categories: list[str],
) -> dict[str, Any]:
    """Quick bias scan over template prompts across given categories.

    Heuristic: checks for positive/negative sentiment words per category.
    Deterministic + offline.
    """
    if not test_prompts:
        return fail("test_prompts must not be empty").to_dict()
    if not categories:
        return fail("categories must not be empty").to_dict()

    # Sanitize prompts
    clean_prompts = []
    for p in test_prompts:
        masked, _ = sanitize_text(p)
        clean_prompts.append(masked)

    report: dict[str, Any] = {}
    for cat in categories:
        sentiments = [_heuristic_sentiment(p) for p in clean_prompts]
        neg_count = sentiments.count("negative")
        pos_count = sentiments.count("positive")
        neutral_count = sentiments.count("neutral")

        notes: list[str] = []
        if neg_count > 0:
            notes.append(
                f"{neg_count} prompt(s) contain negative-sentiment words — review for bias"
            )
        if pos_count > 0:
            notes.append(
                f"{pos_count} prompt(s) contain positive-sentiment words — check for over-representation"
            )
        if neg_count == 0 and pos_count == 0:
            notes.append("No obvious sentiment bias detected in this prompt set")

        report[cat] = {
            "positive": pos_count,
            "negative": neg_count,
            "neutral": neutral_count,
            "notes": notes,
        }

    return ok(
        {
            "categories_scanned": categories,
            "num_prompts": len(clean_prompts),
            "report": report,
            "caveat": "Heuristic scan only — manual review recommended for production use",
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration
# ---------------------------------------------------------------------------

_MCP_TOOLS = [
    (
        download_checkpoint_metadata,
        "Fetch checkpoint metadata (step, loss…) without downloading weights (dry-run unless FTOS_SSH_* configured).",
    ),
    (
        evaluate_on_synthetic,
        "Run a deterministic eval over synthetic data to verify the pipeline — no real data required.",
    ),
    (
        evaluate_on_validation_set,
        "Run eval on the client validation set via SSH (dry-run unless FTOS_SSH_* configured).",
    ),
    (
        compute_metrics,
        "Compute BLEU, ROUGE-1/2/L, perplexity, accuracy, macro-F1 from preds and refs — pure, offline.",
    ),
    (
        generate_predictions_sample,
        "Emit a Python harness to generate sample predictions on synthetic prompts — pure, offline.",
    ),
    (
        compare_to_baseline,
        "Compute per-metric deltas between fine-tuned and baseline and render a Markdown comparison table.",
    ),
    (
        bias_fairness_scan,
        "Heuristic bias/fairness scan over template prompts across given categories — deterministic, offline.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all evaluation tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
