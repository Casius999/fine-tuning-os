# src/fine_tuning_os/models.py
"""Shared Pydantic v2 DTOs for Fine-Tuning OS Lot 2+."""

from __future__ import annotations

from pydantic import BaseModel, ValidationInfo, field_validator


class Column(BaseModel):
    """A single column descriptor in a data schema."""

    name: str
    dtype: str


class DataSchema(BaseModel):
    """Abstract schema: column list + task type. No real data content."""

    columns: list[Column]
    task_type: str  # e.g. "chat" | "instruct" | "classification"


class TrainingParams(BaseModel):
    """Hyper-parameters for a LoRA/QLoRA fine-tuning run."""

    base_model: str
    framework: str = "unsloth"
    lora_rank: int = 16
    lr: float = 2e-4
    batch_size: int = 2
    epochs: int = 1
    scheduler: str = "cosine"
    max_seq_len: int = 2048


class SplitRatios(BaseModel):
    """Train/val/test split ratios that must sum to 1.0."""

    train: float = 0.8
    val: float = 0.1
    test: float = 0.1

    @field_validator("test")
    @classmethod
    def ratios_sum_to_one(cls, test: float, info: ValidationInfo) -> float:
        data = info.data
        total = data.get("train", 0.0) + data.get("val", 0.0) + test
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"train+val+test must sum to 1.0, got {total}")
        return test
