# Phase 2 — Synthetic Data

> Tools 6-10 | Class: C1 (all)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Define the abstract data contract and generate a small, deterministic synthetic
dataset that mimics the schema of the real client data — without ever seeing
real content. The synthetic dataset is the only data the pipeline uses for
local testing (Phase 3) and for unsloth-server proof runs.

**Zero-Data principle:** these tools operate exclusively on schema descriptions
(column names, dtypes, task type) and generated placeholder values. They never
ingest, read, or transmit real client rows.

---

## Inputs

- Schema description: column names, types (`str`, `int`, `float`, `bool`),
  task type (`classification`, `generation`, `chat`, `instruct`, `seq2seq`)
- Sample size n (10-50) and random seed
- Split ratios

## Outputs

- `project.json` updated with `data_schema`
- `data/synthetic/dataset.jsonl` — n deterministic synthetic rows
- Schema validation report (conformance, mismatches)
- Anonymized preview file (`*.anon`)
- `src/split.py` — seeded split script

---

## Tool Sequence

### Step 1 — Describe the data schema

```
describe_expected_data_format(
    project_id="acme-ft-001",
    columns=[
        {"name": "instruction", "dtype": "str"},
        {"name": "output", "dtype": "str"}
    ],
    task_type="instruct"
)
# → {schema: {columns: [...], task_type: "instruct"}} persisted in project.json
```

**Key**: only structural information (names + types), never example values from
the real dataset. Ask the client for the column names over a call or email.

### Step 2 — Generate synthetic dataset

```
generate_synthetic_dataset(project_id="acme-ft-001", n=20, seed=42)
# → {path: ".../data/synthetic/dataset.jsonl", n: 20, seed: 42}
```

Generates 20 rows of the form `{"instruction": "synthetic_instruction_0000", "output": "synthetic_output_0000"}`.
Deterministic: same seed → identical file.

### Step 3 — Validate schema

```
validate_data_schema(
    file_path=".../data/synthetic/dataset.jsonl",
    project_id="acme-ft-001"
)
# → {conforms: true, rows_checked: 20, mismatches: []}
```

**Zero-Data note:** the validator reads only keys, types, and lengths — never
the string values. Safe to run on any file.

### Step 4 — Anonymize preview (optional, for debug)

If the client sends a small debug sample:
```
anonymize_dataset_preview(file_path="/tmp/client_sample.jsonl")
# → {anon_path: "/tmp/client_sample.jsonl.anon", masked_count: 14}
```
The `.anon` file may then be used for manual inspection; still do not pass
values to Claude directly.

### Step 5 — Split configuration

```
split_dataset_config(
    ratios={"train": 0.8, "val": 0.1, "test": 0.1},
    seed=42,
    stratify=False,
    project_id="acme-ft-001"
)
# → {content: "...", path: ".../src/split.py"}
```

The client runs `split.py` on their real data inside their enclave.

---

## Go/No-Go Gate

- [ ] `data_schema` persisted in `project.json`
- [ ] `validate_data_schema` reports `conforms: true` on synthetic file
- [ ] `split.py` rendered and committed
- [ ] Client confirmed schema matches their real data structure (written approval)

---

## Schema Design Tips

| Task type | Typical columns | Format notes |
|-----------|----------------|--------------|
| `instruct` | `instruction`, `output` | Alpaca-style |
| `chat` | `messages` (list of `{role, content}`) | ChatML / ShareGPT |
| `classification` | `text`, `label` | Label as string or int |
| `generation` | `prompt`, `completion` | Free-form |
| `seq2seq` | `source`, `target` | Translation/summarization |

Always agree on the schema with the client **in writing** before generating.
Mismatched schemas discovered at execution time cost expensive re-runs.

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| `describe_expected_data_format` before `create_project_structure` | `fail: project not found` | Run Phase 1 first |
| n outside [10,50] | `fail: n must be between 10 and 50` | Use valid range |
| Schema columns mismatch real data | `validate_data_schema` mismatches at client side | Re-describe schema |
| Seed not recorded | Non-reproducible synthetic set | Always store seed in `events.jsonl` via `log_project_event` |
