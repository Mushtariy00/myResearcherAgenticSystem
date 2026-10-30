"""The GPU job contract: what the worker submits, how the executor runs it and what comes back
(docs/design/experiments.md). The worker, the executor and the API share these names.

A job's files on the GPU host, under ARP_DATA_DIR/jobs/<id>/:
- going in: code/ (model.py, optionally loss.py) and config.json, which the executor writes from
  the job's row and mounts read-only;
- coming back: out/ (the files in OUTPUT_FILES, copied out of the container) and log.txt (the
  container's output).
"""

from pathlib import Path

from agentic_core.enums import GpuJobKind

# Container labels. The executor owns every container labelled JOB_LABEL; after a restart it finds
# a job's container by this label.
JOB_LABEL = "arp.job"
KIND_LABEL = "arp.kind"
RUN_LABEL = "arp.run"

# The only files a job's code may hold, each at most agentic_core.codecheck.MAX_SOURCE_BYTES.
MODEL_FILE = "model.py"
LOSS_FILE = "loss.py"
CODE_FILES = frozenset({MODEL_FILE, LOSS_FILE})

MAX_QUEUED_PER_USER = 2  # a user's queued jobs; the worker waits before it submits another

# The wall clock of each kind of job. A job's timeout_seconds may ask for less, never for more.
SMOKE_TIMEOUT_SECONDS = 10 * 60
DEFAULT_MAX_TRAIN_HOURS = 6.0

# Paths inside the container (the executor's template and sandbox/pytorch/harness/job.py).
CODE_MOUNT = "/job/code"
CONFIG_MOUNT = "/job/config.json"
OUT_DIR = "/workspace/out"
DATA_ROOT = "/data"  # a dataset is mounted read-only at /data/<name>

# The harness's output lines the executor acts on. harness.job writes them, and it indents any
# line of the training's own output that starts with "ARP-", so generated code can't fake them.
METRIC_PREFIX = "ARP-METRIC "
DONE_PREFIX = "ARP-DONE "

# The files copied out of OUT_DIR, by their path under it, with the largest size copied. A file
# over its cap is left behind (and noted in the job's error); other files are never copied.
RESULTS_FILE = "results.json"
METRICS_FILE = "metrics.jsonl"
CHECKPOINT_FILE = "checkpoints/best.pt"
OUTPUT_FILES = {
    RESULTS_FILE: 4 * 1024**2,
    METRICS_FILE: 64 * 1024**2,
    CHECKPOINT_FILE: 200 * 1024**2,
}
LOG_FILE = "log.txt"

# error_code when the harness could not say why a job failed. Its own codes (code.refused,
# code.shape_mismatch, train.oom, ...) come from results.json.
JOB_BAD_INPUT = "job.bad_input"  # the job's code, config or dataset is not usable
JOB_START_FAILED = "job.start_failed"  # Docker refused to create or start the container
JOB_OOM_KILLED = "job.oom_killed"  # the container's memory limit killed the training
JOB_NO_RESULT = "job.no_result"  # training ended without a results.json
JOB_LOST = "job.lost"  # the container vanished, or stopped before its outputs were copied


def job_dir(data_dir: Path, job_id: object) -> Path:
    """Where a job's files live on the GPU host (see the module docstring)."""
    return data_dir / "jobs" / str(job_id)


def max_timeout_seconds(kind: GpuJobKind, max_train_hours: float = DEFAULT_MAX_TRAIN_HOURS) -> int:
    """The longest wall clock a job of this kind may have."""
    if kind is GpuJobKind.SMOKE:
        return SMOKE_TIMEOUT_SECONDS
    return round(max_train_hours * 3600)
