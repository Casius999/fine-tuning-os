# tests/test_models.py
"""Tests for shared Pydantic DTOs (models.py)."""

import pytest
from pydantic import ValidationError

from fine_tuning_os.models import Column, DataSchema, SplitRatios, TrainingParams


class TestColumn:
    def test_basic(self):
        c = Column(name="text", dtype="str")
        assert c.name == "text"
        assert c.dtype == "str"


class TestDataSchema:
    def test_basic(self):
        schema = DataSchema(
            columns=[Column(name="text", dtype="str"), Column(name="label", dtype="int")],
            task_type="classification",
        )
        assert schema.task_type == "classification"
        assert len(schema.columns) == 2


class TestTrainingParams:
    def test_defaults(self):
        p = TrainingParams(base_model="mistralai/Mistral-7B-v0.3")
        assert p.framework == "unsloth"
        assert p.lora_rank == 16
        assert p.lr == 2e-4
        assert p.batch_size == 2
        assert p.epochs == 1
        assert p.scheduler == "cosine"
        assert p.max_seq_len == 2048

    def test_custom(self):
        p = TrainingParams(base_model="x", framework="axolotl", lora_rank=32)
        assert p.lora_rank == 32
        assert p.framework == "axolotl"


class TestSplitRatios:
    def test_defaults_sum_to_one(self):
        r = SplitRatios()
        assert abs(r.train + r.val + r.test - 1.0) < 1e-9

    def test_custom_valid(self):
        r = SplitRatios(train=0.7, val=0.15, test=0.15)
        assert abs(r.train + r.val + r.test - 1.0) < 1e-9

    def test_invalid_sum_raises(self):
        with pytest.raises(ValidationError):
            SplitRatios(train=0.9, val=0.1, test=0.1)
