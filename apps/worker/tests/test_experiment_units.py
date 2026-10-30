"""The experiment stage's pure parts: the training plan and its batch-size rule, and the output
built from a job's row and its epoch events, both made by hand here."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from llm_stages_testkit import (
    TRAIN_CONFIG_SHA256,
    TRAIN_GPU,
    TRAIN_IMAGE_ID,
    TRAIN_MODEL_PY,
    depth_metrics,
    epoch_payload,
    failed_results,
    train_code_config,
    train_provenance,
    train_results,
    trained_coding,
)

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.schemas import CodingOutput
from agentic_db.models import Dataset, GpuJob
from agentic_worker.coding.config import CodeConfig, SmokeMeasure
from agentic_worker.experiment.output import (
    METRICS,
    code_sha256,
    experiment_output,
    finished_line,
    ran_config,
    source_hashes,
)
from agentic_worker.experiment.plan import (
    FreeMemory,
    approved_code,
    batch_size,
    free_memory,
    plan_training,
)
from agentic_worker.stages import StageFailedError

NYU2 = Dataset(name="nyu2", version="2026.05", title="NYU Depth V2")
CODE = {"model.py": TRAIN_MODEL_PY}
PLAN = plan_training(
    CodeConfig.model_validate(train_code_config()),
    epochs=3,
    steps_per_epoch=1000,
    memory=free_memory(None),
)
CONFIG = PLAN.harness_config("nyu2")
QUEUED_AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
STARTED_AT = QUEUED_AT + timedelta(minutes=2)
FINISHED_AT = STARTED_AT + timedelta(minutes=46)
# (train, val) of each epoch.
EPOCHS = [
    (depth_metrics(0.61, 0.92, 0.70, 0.25), depth_metrics(0.66, 0.98, 0.74, 0.27)),
    (depth_metrics(0.45, 0.71, 0.54, 0.19), depth_metrics(0.52, 0.80, 0.60, 0.21)),
    (depth_metrics(0.38, 0.63, 0.47, 0.16), depth_metrics(0.47, 0.74, 0.55, 0.19)),
]


def _job(**values: Any) -> GpuJob:
    """A training job that ended, as its row reads; ``values`` change it."""
    row: dict[str, Any] = {
        "id": uuid.UUID(int=1),
        "stage_run_id": uuid.UUID(int=2),
        "run_id": uuid.UUID(int=3),
        "user_id": "bob",
        "kind": GpuJobKind.TRAIN,
        "ordinal": 1,
        "status": GpuJobStatus.SUCCEEDED,
        "dataset": "nyu2",
        "code": CODE,
        "config": CONFIG,
        "timeout_seconds": 21_600,
        "created_at": QUEUED_AT,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
        "exit_code": 0,
        "gpu_seconds": 2_712.4,
        "result": train_results(EPOCHS[-1][1], best_val_loss=0.47),
        "provenance": train_provenance(CODE),
        "log_tail": "epoch 2 train {...} val {...}\nwrote results.json",
    }
    return GpuJob(**(row | values))


def _payloads(epochs: list[tuple[dict[str, float | None], dict[str, float | None]]]) -> list[Any]:
    return [epoch_payload(uuid.UUID(int=1), n, train, val) for n, (train, val) in enumerate(epochs)]


# --- the plan ------------------------------------------------------------------------------------

SAMPLE = {
    "index": 0,
    "name": TRAIN_GPU,
    "memory_total_mb": 6144,
    "memory_used_mb": 1024,
    "utilization_percent": 2,
    "sampled_at": "2026-10-30T09:00:00+00:00",
}


@pytest.mark.parametrize(
    ("status", "mb", "source"),
    [
        (
            None,
            4608,
            "an assumed 4608 MB free (no GPU reading from the executor: a 6144 MB card with "
            "1536 MB in use)",
        ),
        ({"alive_at": "2026-10-30T09:00:00+00:00", "gpu": None, "job_id": None}, 4608, None),
        (
            {"gpu": SAMPLE, "job_id": None},
            5120,
            f"the 5120 MB free on the {TRAIN_GPU} when the executor last sampled it",
        ),
        (
            {"gpu": SAMPLE, "job_id": str(uuid.UUID(int=9))},
            4608,
            f"an assumed 4608 MB free on the {TRAIN_GPU} (it was running another job when last "
            "sampled, so 1536 of its 6144 MB are taken as in use)",
        ),
        ({"gpu": SAMPLE | {"memory_used_mb": 7000}, "job_id": None}, 0, None),
        ({"gpu": SAMPLE | {"memory_total_mb": "6144"}, "job_id": None}, 4608, None),
        ({"gpu": SAMPLE | {"memory_total_mb": 0}, "job_id": None}, 4608, None),
        (
            {"gpu": {"memory_total_mb": 8192, "memory_used_mb": 0}},
            8192,
            "the 8192 MB free on the GPU when the executor last sampled it",
        ),
    ],
)
def test_free_memory_comes_from_the_executors_heartbeat(
    status: dict[str, Any] | None, mb: int, source: str | None
) -> None:
    memory = free_memory(status)
    assert memory.mb == mb
    assert source is None or memory.source == source


def test_the_batch_takes_60_percent_of_the_free_memory_a_smoke_sample_needs() -> None:
    smoke = SmokeMeasure(job_id="smoke", batch_size=2, peak_gpu_memory_mb=410)
    chosen = batch_size(smoke, free_memory({"gpu": SAMPLE | {"memory_used_mb": 1536}}))
    # 60% of 4608 MB is 2764.8 MB: 13 samples of 205 MB.
    assert chosen.value == 8
    assert chosen.reason == (
        "Batch size 8: the smoke test peaked at 410 MB of GPU memory with 2 samples, about "
        f"205 MB a sample, and 60% of the 4608 MB free on the {TRAIN_GPU} when the executor "
        "last sampled it is room for 13, rounded down to a power of two."
    )


@pytest.mark.parametrize(
    ("peak_mb", "smoke_batch", "free_mb", "expected", "said"),
    [
        (None, 2, 4608, 4, "Batch size 4, the default: the smoke test measured no GPU memory."),
        (0, 2, 4608, 4, "Batch size 4, the default: "),
        (410, 2, 100_000, 16, "is room for 292, more than the cap of 16."),
        (4000, 2, 4608, 2, "is room for only 1; 2 is the minimum."),
        (410, 2, 0, 2, "is room for only 0; 2 is the minimum."),
        (100, 1, 2700, 16, "with 1 sample, about 100 MB a sample, and 60% of x is room for 16."),
        (100, 1, 2900, 16, "is room for 17, more than the cap of 16."),
        (100, 1, 1550, 8, "is room for 9, rounded down to a power of two."),
        (300, 1, 2100, 4, "is room for 4."),
        (100, 1, 1100, 4, "is room for 6, rounded down to a power of two."),
        (100, 1, 550, 2, "is room for 3, rounded down to a power of two."),
        (9, 2, 50, 4, "about 4.5 MB a sample"),
    ],
)
def test_the_batch_size_rule_at_its_edges(
    peak_mb: int | None, smoke_batch: int, free_mb: int, expected: int, said: str
) -> None:
    smoke = SmokeMeasure(job_id="smoke", batch_size=smoke_batch, peak_gpu_memory_mb=peak_mb)
    chosen = batch_size(smoke, FreeMemory(free_mb, "x"))
    assert chosen.value == expected
    assert said in chosen.reason
    assert chosen.reason.startswith(f"Batch size {expected}")


def test_the_plan_bounds_the_code_config_by_the_settings() -> None:
    config = CodeConfig.model_validate(
        train_code_config(loss="generated", model_kwargs={"base_channels": 32, "bins": True})
    )
    plan = plan_training(config, epochs=3, steps_per_epoch=1000, memory=FreeMemory(4608, "x"))
    assert plan.harness_config("nyu2") == {
        "task": "nyu2_depth",
        "seed": 42,
        "require_gpu": True,
        "model": {"architecture": "generated", "kwargs": {"base_channels": 32, "bins": True}},
        "data": {
            "dataset": "nyu2",
            "batch_size": 8,
            "num_workers": 2,
            "split_file_template": "{root}/splits/nyu/{split}.txt",
        },
        "training": {
            "learning_rate": 0.0003,
            "optimizer": "adamw",
            "weight_decay": 0.0001,
            "clip_grad_norm": None,
            "loss": "generated",
            "epochs": 3,
            "max_train_steps": 1000,
            "max_val_steps": None,  # the whole validation split, every epoch
        },
    }
    assert plan.progress() == (
        {"epochs": 3, "steps": 1000, "batch_size": 8},
        "Training plan: 3 epochs of up to 1000 steps at batch size 8",
    )


def test_the_approved_code_is_model_and_loss_with_their_config() -> None:
    coding = trained_coding(train_code_config(loss="generated"), loss=True)
    code = approved_code(CodingOutput.model_validate(coding))
    assert sorted(code.files) == ["loss.py", "model.py"]  # not config.json, not the README
    assert code.files["model.py"] == TRAIN_MODEL_PY
    assert (code.config.loss, code.config.smoke.peak_gpu_memory_mb) == ("generated", 410)


def _edited(coding: dict[str, Any], path: str, content: str | None) -> CodingOutput:
    """``coding`` with the file at ``path`` replaced (or removed with None)."""
    files = [file for file in coding["files"] if file["path"] != path]
    if content is not None:
        files.append({"path": path, "language": "json", "role": "config", "content": content})
    return CodingOutput.model_validate({**coding, "files": files})


@pytest.mark.parametrize(
    ("coding", "error"),
    [
        (_edited(trained_coding(), "config.json", None), "the approved code has no config.json"),
        (_edited(trained_coding(), "model.py", None), "the approved code has no model.py"),
        (
            _edited(trained_coding(), "config.json", "{not json"),
            "config.json: the file: Invalid JSON",
        ),
        (
            _edited(
                trained_coding(),
                "config.json",
                json.dumps(train_code_config(training={"learning_rate": 5})),
            ),
            "config.json: training.learning_rate: Input should be less than or equal to 0.1",
        ),
        (
            _edited(trained_coding(), "config.json", json.dumps(train_code_config(epochs=40))),
            "config.json: epochs: Extra inputs are not permitted",
        ),
        (
            CodingOutput.model_validate(trained_coding(train_code_config(loss="generated"))),
            "config.json asks for the generated loss, and the code has no loss.py",
        ),
    ],
)
def test_code_that_could_not_train_as_approved_fails_the_stage(
    coding: CodingOutput, error: str
) -> None:
    with pytest.raises(StageFailedError) as raised:
        approved_code(coding)
    assert str(raised.value).startswith(f"experiment.invalid_code_config: {error}")


# --- the output ----------------------------------------------------------------------------------


def test_a_job_that_succeeded_reports_its_curves_metrics_and_provenance() -> None:
    job = _job()
    output = experiment_output(job, _payloads(EPOCHS), dataset=NYU2, batch_reason=PLAN.batch.reason)
    assert output.status == "succeeded"
    # Validation first in each pair, so the web's headline metric reads the validation split.
    assert [(series.name, series.split) for series in output.series] == [
        (name, split) for name in METRICS for split in ("val", "train")
    ]
    assert not any(series.higher_is_better for series in output.series)
    curves = {(s.name, s.split): [(p.epoch, p.value) for p in s.points] for s in output.series}
    assert curves["rmse", "val"] == [(0, 0.98), (1, 0.80), (2, 0.74)]
    assert curves["loss", "train"] == [(0, 0.61), (1, 0.45), (2, 0.38)]
    assert output.final_metrics == {"loss": 0.47, "rmse": 0.74, "mae": 0.55, "abs_rel": 0.19}
    assert output.config == {
        "epochs": 3,
        "steps_per_epoch": 1000,
        "batch_size": 8,
        "learning_rate": 0.0003,
        "optimizer": "adamw",
        "weight_decay": 0.0001,
        "loss": "l1",
        "seed": 42,
        "model.base_channels": 16,
    }
    assert output.logs_tail == job.log_tail
    provenance = output.provenance
    model_sha = hashlib.sha256(TRAIN_MODEL_PY.encode()).hexdigest()
    assert provenance.code_sha256 == hashlib.sha256(f"model.py\0{model_sha}\n".encode()).hexdigest()
    assert (provenance.image_digest, provenance.config_sha256) == (
        TRAIN_IMAGE_ID,
        TRAIN_CONFIG_SHA256,
    )
    assert (provenance.dataset, provenance.dataset_version, provenance.seed) == (
        "nyu2",
        "2026.05",
        42,
    )
    assert (provenance.gpu_name, provenance.gpu_seconds) == (TRAIN_GPU, 2712.4)
    assert (provenance.started_at, provenance.finished_at) == (STARTED_AT, FINISHED_AT)
    assert output.summary == (
        "Training on NYU Depth V2 (nyu2, version 2026.05) succeeded: 3 epochs completed. "
        "Validation after the last epoch: loss 0.47, RMSE 0.74, MAE 0.55, AbsRel 0.19. The best "
        "validation loss was 0.47. It ran 3 epochs of up to 1000 steps at batch size 8, "
        "validating on the whole validation split after each epoch, with seed 42 (47584 "
        f"training and 654 validation samples); 45.2 GPU-minutes on the {TRAIN_GPU}. Batch size "
        "8: the smoke test peaked at 410 MB of GPU memory with 2 samples, about 205 MB a "
        "sample, and 60% of an assumed 4608 MB free (no GPU reading from the executor: a 6144 "
        "MB card with 1536 MB in use) is room for 13, rounded down to a power of two."
    )
    assert finished_line(output, None) == (
        {"status": "succeeded", "epochs": 3},
        "Training succeeded: 3 epochs",
    )


def test_a_job_that_ran_out_of_memory_keeps_what_its_epochs_measured() -> None:
    error = "OutOfMemoryError: CUDA out of memory.\n  Tried to allocate 1.50 GiB"
    job = _job(
        status=GpuJobStatus.FAILED,
        error_code="train.oom",
        error=error,
        result=failed_results("train.oom", error),
        exit_code=1,
        gpu_seconds=95.0,
    )
    output = experiment_output(
        job, _payloads(EPOCHS[:1]), dataset=NYU2, batch_reason=PLAN.batch.reason
    )
    assert output.status == "failed"
    assert output.summary.startswith(
        "Training on NYU Depth V2 (nyu2, version 2026.05) failed (train.oom) after 1 of 3 epochs: "
        "OutOfMemoryError: CUDA out of memory. Tried to allocate 1.50 GiB. Validation after the "
        "last completed epoch: loss 0.66, RMSE 0.98, MAE 0.74, AbsRel 0.27. It was set to run 3 "
        "epochs of up to 1000 steps at batch size 8"
    )
    assert "1.6 GPU-minutes" in output.summary
    assert output.final_metrics == EPOCHS[0][1]
    assert [len(series.points) for series in output.series] == [1] * 8
    assert finished_line(output, job.error_code) == (
        {"status": "failed", "epochs": 1},
        "Training failed (train.oom) after 1 epoch",
    )


def test_a_job_that_failed_before_its_container_has_honest_placeholders() -> None:
    error = "Dataset nyu2 has no folder on this machine: set ARP_DATASET_NYU2"
    job = _job(
        status=GpuJobStatus.FAILED,
        error_code="job.bad_input",
        error=error,
        result=None,
        provenance=None,
        started_at=None,
        exit_code=None,
        gpu_seconds=None,
        log_tail=None,
    )
    output = experiment_output(job, [], dataset=NYU2, batch_reason=None)
    assert (output.series, output.final_metrics, output.logs_tail) == ([], {}, "")
    provenance = output.provenance
    assert provenance.image_digest == "unknown"
    # The hashes are of what the stage submitted: per file as the executor would take them.
    assert provenance.code_sha256 == code_sha256(source_hashes(CODE))
    canonical = json.dumps(CONFIG, sort_keys=True, ensure_ascii=False)
    assert provenance.config_sha256 == hashlib.sha256(canonical.encode()).hexdigest()
    assert provenance.dataset_version == "2026.05"  # the registered version
    assert (provenance.started_at, provenance.finished_at) == (QUEUED_AT, FINISHED_AT)
    assert (provenance.gpu_seconds, provenance.gpu_name, provenance.seed) == (0.0, None, 42)
    assert output.summary == (
        "Training on NYU Depth V2 (nyu2, version 2026.05) failed (job.bad_input) before its "
        f"first epoch: {error}. Nothing was measured. It was set to run 3 epochs of up to 1000 "
        "steps at batch size 8, validating on the whole validation split after each epoch, with "
        "seed 42. Batch size 8, chosen when an earlier try of this attempt submitted the job. The "
        "job's provenance is incomplete: the image digest is unknown; the code hash is of the "
        "code as submitted; the config hash is of the config as submitted; it never started, so "
        "its start time is when it was queued."
    )


def test_hashes_the_executor_could_not_take_come_from_what_was_submitted() -> None:
    recorded = train_provenance(CODE, code_sha256={}, config_sha256=None, dataset=None)
    job = _job(provenance=recorded)
    output = experiment_output(job, _payloads(EPOCHS), dataset=None, batch_reason=None)
    assert output.provenance.image_digest == TRAIN_IMAGE_ID
    assert output.provenance.code_sha256 == code_sha256(source_hashes(CODE))
    assert output.provenance.dataset_version == "unknown"
    assert output.summary.startswith("Training on nyu2 (version unknown) succeeded")
    assert output.summary.endswith(
        "The job's provenance is incomplete: the code hash is of the code as submitted; the "
        "config hash is of the config as submitted; the dataset version is unknown."
    )


@pytest.mark.parametrize(
    ("status", "error", "epochs", "said", "line"),
    [
        (
            GpuJobStatus.TIMEOUT,
            "Stopped at the job's time limit of 21600 s",
            2,
            "stopped at its time limit after 2 of 3 epochs: Stopped at the job's time limit of "
            "21600 s. Validation after the last completed epoch: loss 0.52, RMSE 0.8, MAE 0.6, "
            "AbsRel 0.21.",
            "Training stopped at its time limit after 2 epochs",
        ),
        (
            GpuJobStatus.CANCELLED,
            None,
            1,
            "was cancelled after 1 of 3 epochs. Validation after the last completed epoch: loss "
            "0.66,",
            "Training was cancelled after 1 epoch",
        ),
        (
            GpuJobStatus.CANCELLED,
            None,
            0,
            "was cancelled before its first epoch. Nothing was measured.",
            "Training was cancelled after 0 epochs",
        ),
    ],
)
def test_a_job_that_timed_out_or_was_cancelled_says_how_far_it_got(
    status: GpuJobStatus, error: str | None, epochs: int, said: str, line: str
) -> None:
    job = _job(status=status, error=error, result=None, exit_code=None)
    output = experiment_output(
        job, _payloads(EPOCHS[:epochs]), dataset=NYU2, batch_reason=PLAN.batch.reason
    )
    assert output.status == status.value
    assert said in output.summary
    assert output.final_metrics == (EPOCHS[epochs - 1][1] if epochs else {})
    assert finished_line(output, None) == ({"status": status.value, "epochs": epochs}, line)


def test_metrics_and_epochs_that_were_not_measured_stay_null() -> None:
    train = depth_metrics(0.5, 0.8, 0.6, 0.2)
    payloads = [
        # Epoch 0: rmse not measured, mae not a number, abs_rel missing.
        epoch_payload(uuid.UUID(int=1), 0, train, {})
        | {"val": {"loss": 0.66, "rmse": None, "mae": "n/a"}},
        # Epoch 1's record never arrived; epoch 2 came twice, and the later one counts.
        epoch_payload(uuid.UUID(int=1), 2, train, depth_metrics(0.9, 0.9, 0.9, 0.9)),
        epoch_payload(uuid.UUID(int=1), 2, train, depth_metrics(0.47, 0.74, 0.55, 0.19)),
        # Records no epoch of the job's: past its 3 epochs, or not an epoch at all.
        epoch_payload(uuid.UUID(int=1), 5, train, depth_metrics(0.1, 0.1, 0.1, 0.1)),
        {**epoch_payload(uuid.UUID(int=1), 0, train, train), "epoch": True},
        {**epoch_payload(uuid.UUID(int=1), 0, train, train), "epoch": -1},
    ]
    results = train_results(depth_metrics(0.47, None, 0.55, 0.19), best_val_loss=None)
    output = experiment_output(
        _job(result=results), payloads, dataset=NYU2, batch_reason=PLAN.batch.reason
    )
    curves = {(s.name, s.split): [p.value for p in s.points] for s in output.series}
    assert curves["loss", "val"] == [0.66, None, 0.47]
    assert curves["rmse", "val"] == [None, None, 0.74]
    assert curves["mae", "val"] == [None, None, 0.55]
    assert curves["abs_rel", "val"] == [None, None, 0.19]
    assert curves["loss", "train"] == [0.5, None, 0.5]
    assert output.final_metrics == {"loss": 0.47, "rmse": None, "mae": 0.55, "abs_rel": 0.19}
    assert "Validation after the last epoch: loss 0.47, RMSE not measured, MAE 0.55," in (
        output.summary
    )
    assert "RMSE 0" not in output.summary and "best validation loss" not in output.summary
    assert "No metrics arrived for 1 of the 3 epochs, so their points in the curves are null." in (
        output.summary
    )


def test_a_job_that_succeeded_has_a_point_for_every_epoch_it_ran() -> None:
    output = experiment_output(
        _job(), _payloads(EPOCHS[:1]), dataset=NYU2, batch_reason=PLAN.batch.reason
    )
    assert [[p.epoch for p in s.points] for s in output.series] == [[0, 1, 2]] * 8
    assert [p.value for p in output.series[0].points] == [0.66, None, None]
    assert "No metrics arrived for 2 of the 3 epochs" in output.summary


def test_the_code_hash_names_the_set_of_files() -> None:
    files = {"model.py": "a" * 64, "loss.py": "b" * 64}
    lines = f"loss.py\0{'b' * 64}\nmodel.py\0{'a' * 64}\n"
    assert code_sha256(files) == hashlib.sha256(lines.encode()).hexdigest()
    assert code_sha256(dict(reversed(files.items()))) == code_sha256(files)
    assert source_hashes({"model.py": "x = 'é'\n"}) == {
        "model.py": hashlib.sha256("x = 'é'\n".encode()).hexdigest()
    }


def test_the_config_of_what_ran_is_flat() -> None:
    config = json.loads(json.dumps(CONFIG))
    config["training"]["clip_grad_norm"] = 1.5
    config["model"]["kwargs"] = {"base_channels": 16, "bins": True, "act": "relu"}
    assert ran_config(config) == {
        "epochs": 3,
        "steps_per_epoch": 1000,
        "batch_size": 8,
        "learning_rate": 0.0003,
        "optimizer": "adamw",
        "weight_decay": 0.0001,
        "clip_grad_norm": 1.5,
        "loss": "l1",
        "seed": 42,
        "model.base_channels": 16,
        "model.bins": True,
        "model.act": "relu",
    }
    assert ran_config({}) == {}


def test_a_job_that_has_not_ended_has_no_output() -> None:
    with pytest.raises(ValueError, match="has not ended"):
        experiment_output(_job(status=GpuJobStatus.RUNNING), [], dataset=NYU2, batch_reason=None)
