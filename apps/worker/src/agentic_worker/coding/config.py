"""config.json of a coding output: what the code passed its smoke test with.

The coding stage writes it into its output, next to model.py (and loss.py), so the reviewer sees
it; the experiment stage trains the approved code with it. A reviewer who approves with edits may
change it, so the experiment stage validates it again and keeps every value within its bounds.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_FILE = "config.json"

type ModelKwarg = int | float | str | bool


class TrainingChoices(BaseModel):
    """The coding agent's training settings, within the harness's bounds."""

    model_config = ConfigDict(extra="forbid")

    learning_rate: float = Field(default=1e-3, gt=0, le=0.1)
    optimizer: Literal["adam", "adamw", "sgd"] = "adam"
    weight_decay: float = Field(default=0.0, ge=0, le=0.1)
    clip_grad_norm: float | None = Field(default=None, gt=0, le=100)


class SmokeMeasure(BaseModel):
    """What the passing smoke test measured (its job's results.json)."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    batch_size: int = Field(ge=1)
    peak_gpu_memory_mb: int | None = Field(default=None, ge=0)
    steps_per_second: float | None = Field(default=None, ge=0)
    param_count: int | None = Field(default=None, ge=0)


class CodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str  # a registered dataset the harness trains on (agentic_worker.gpu)
    model_kwargs: dict[str, ModelKwarg] = Field(default_factory=dict, max_length=32)
    # "generated" when the code has a loss.py; else one of the harness's own losses.
    loss: Literal["generated", "l1", "mse", "smooth_l1"]
    training: TrainingChoices = Field(default_factory=TrainingChoices)
    smoke: SmokeMeasure
