# Phase 3 design: real code and real experiments

Status: draft (2026-10-30). This replaces the simulated coding and experiment stages
(`stage.demo`) with:
- generated model code, checked and smoke-tested in the GPU sandbox;
- real training runs on the lab GPU.

The output contracts (`CodingOutput`, `ExperimentOutput`) do not change, so the web app needs
no change for them.

## Goal and exit criteria (docs/PLAN.md, Phase 3)

- An NYU2 run started from the UI gets:
  - real code from the coding agent;
  - a smoke test that really ran;
  - a training job with real metrics, curves and full provenance.
- Sandbox tests pass: a fork bomb, a disk fill, network access and secrets in the environment
  are all contained.
- A cancel kills a running job in 5 s or less.
- Restarting the worker or the executor never duplicates a container.
- `legacy/` is deleted at the end of the phase.

## What exists (Phase 0)

- `sandbox/pytorch` and its image `arp-sandbox-pytorch:dev`:
  - PyTorch 2.14.1 with CUDA 12.6, the last line for Pascal GPUs; extra libraries h5py,
    pydantic, PyYAML, and no torchvision;
  - the harness, which owns data loading, the splits, the loss choices, the metrics (loss,
    RMSE, MAE, AbsRel, with null when not measured) and the training loop;
  - a typed, bounded `ExperimentConfig`, a `--dry-run` mode of 2 + 2 batches, and an honest
    `results.json` (`status`, metrics, provenance).
- `scripts/sandbox-smoke.sh` proves the hardened flags of ADR 0006 on this machine: the GPU is
  visible, there is no network, no secrets, the root is read-only, the output is writable, and
  a failure is reported as one.
- Hardware: a GTX 1060 6 GB. The NYU2 data is at `/mnt/d/DATASET/nyu2/nyu2_metric_ready` (h5
  files). Reading through WSL's drvfs is slow; copying the data to the ext4 disk is advised.

## The generated code contract

The coding agent writes only these files. Everything else is the harness's.

- `model.py` defines `class Model(torch.nn.Module)`.
  - `__init__(**kwargs)` takes scalar kwargs from the config.
  - `forward(x)` maps a `(B, 3, H, W)` normalised RGB batch to `(B, 1, H, W)` depth in
    metres, at the same H and W.
- `loss.py` (optional) defines `class Loss(torch.nn.Module)` with
  `forward(prediction, target, valid_mask)` returning a scalar. The harness keeps computing the
  metrics itself, so a custom loss can't fake them.
- **Allowed imports:** `torch`, `torch.nn`, `torch.nn.functional`, `math`, `typing`,
  `dataclasses`, `functools`, `collections`, `__future__`.
- **Refused:**
  - any other import;
  - `open`, `exec`, `eval`, `compile`, `__import__`, `globals`, `getattr` / `setattr` with
    dunder names;
  - attribute access to `__subclasses__`, `__globals__`, `__builtins__`;
  - files over 20 KB.
- **Checked twice:**
  - statically by the worker (an AST allowlist, before anything runs);
  - again by the harness when it loads the module, by source path, as an isolated module
    (`architecture: "generated"`) from a read-only `/job/code`.
  The sandbox (no network, read-only root, no secrets) is the last line, not the first.
- **Smoke test:** a dry run. It checks the parameter count (at most 50 M), the output shape
  on a real batch, a finite loss, and the step time.

## GPU jobs

Table `gpu_jobs`:
- id (uuid), stage_run_id, run_id, user_id, kind (`smoke` | `train`), ordinal (the repair
  loop's try), unique (stage_run_id, kind, ordinal);
- status: `queued → starting → running → succeeded | failed | timeout | cancelled`;
- cancel_requested, compare-and-set;
- container_id, lease_until, exit_code, gpu_seconds;
- result (results.json), provenance (image digest, code and config sha256, dataset version,
  seed, GPU name);
- created, started and finished timestamps.

Table `datasets`: name, version, host_path, checksum, contract (JSON), enabled. nyu2 is
registered by a migration and a setting (`ARP_DATASET_NYU2`).

### The executor (`apps/executor`, a new uv member)

The only component that talks to Docker:
- **Docker access:** through a socket proxy in compose (tecnativa docker-socket-proxy,
  pinned) with only `CONTAINERS` and `POST` enabled; no exec, no networks, no volumes. It
  creates containers from its own template alone (ADR 0006 flags): `--gpus device=0`,
  `--network none`, read-only root, `--tmpfs /tmp`, user 10001, `--cap-drop ALL`,
  no-new-privileges, `--pids-limit`, memory = memory-swap, `--cpus`, `--shm-size 2g`.
- **Mounts:**
  - the dataset read-only;
  - the job's code (`ARP_DATA_DIR/jobs/<id>/code`) read-only;
  - a size-limited tmpfs for `/workspace/out`. It is a hard quota that WSL's ext4 can't give
    a bind mount, and it is charged to the container's memory.
- **Queue:** claims the next job with `FOR UPDATE SKIP LOCKED`, at concurrency 1, after a
  VRAM preflight (`nvidia-smi`; it waits while another process holds the GPU).
- **Live metrics:** the harness writes its metric records as JSON lines to stdout, and the
  executor follows the container's logs. Epoch lines become run events
  (`experiment.epoch {epoch, train, val}`) for live curves.
- **At the end:** it copies `/workspace/out` out through the archive API (results.json,
  metrics.jsonl, and best.pt if it is under 200 MB) into `ARP_DATA_DIR/jobs/<id>/out`,
  records the result, and removes the container.
- **Labels:** `arp.job=<id>`. At start-up it adopts the containers of running jobs and reaps
  unknown ones. A running job without a container is marked failed (`job.lost`); a starting
  one is requeued.
- **Cancel:** the worker sets cancel_requested. The executor checks every second, kills the
  container with a 2 s grace period, and the job ends `cancelled` within 5 s.
- **Limits:** a wall clock per kind (smoke 10 min, train up to `ARP_MAX_TRAIN_HOURS`, default
  6) ends a job as `timeout`. There are at most 2 queued jobs per user. A GPU-hours quota per
  user comes later.

## The stages (worker)

Each stage stays one `execute_stage` activity, as the literature stage does, so the workflow's
command sequence doesn't change. The activity heartbeats while it waits for its job, and its
timeout is the job's limit plus the queue wait.

- **A crash resumes:** an activity that runs again finds its job by
  (stage_run_id, kind, ordinal) and waits on it instead of submitting a new one.
- **A cancel stops the job:** a cancelled activity sets cancel_requested and waits for the
  job to stop (`WAIT_CANCELLATION_COMPLETED`).
- **Coding** (`coding@1`, role `coding.write`, then `coding.repair`):
  - from the approved method (the recommended option and the implementation focus) and the
    contract above, the LLM writes `model.py` (and `loss.py`) plus the model kwargs;
  - the AST check, then a smoke job;
  - a failure goes back to the LLM with the error and the log tail, at most 3 tries; then
    the stage fails with `coding.smoke_failed`;
  - the output is CodingOutput (files, entrypoint `model.py:Model`, smoke_test).
  - Coding is never auto-approved.
- **Experiment:**
  - the bounded config comes from the approved code, RunConfig.dataset and the method: epochs
    capped, batch size from free VRAM;
  - one train job;
  - the output is ExperimentOutput: series from the epoch records, final metrics (null when
    not measured), the log tail, and provenance (image digest, sha256 of code and config,
    dataset version, seed, GPU name, GPU-seconds);
  - status `succeeded | failed | timeout | cancelled` mirrors the job, honestly.
- **Writing:** it stops flagging `writing.simulated_results` once coding and experiment are
  real.

## API and web

- `GET /gpu/queue` reads `gpu_jobs` (with the position and an estimate), and
  `GET /datasets` reads `datasets`; both are demo today.
- Artifacts:
  - the code files from CodingOutput;
  - from the job outputs: the log, metrics.jsonl as CSV, and the checkpoint, each an
    attachment with nosniff;
  - the ones that exist today are generated.
- The web keeps its stage views. The experiment view gains live curves from
  `experiment.epoch` events, translated like the other progress lines.

## Verification

- **Unit tests:**
  - the AST checker (allowed and refused code, obfuscation attempts);
  - the harness loading generated modules;
  - the executor against a fake Docker API: claim, adopt or reap, cancel compare-and-set,
    timeout, the archive copy.
- **Sandbox tests on this machine (`make sandbox-security`)**: a fork bomb stops at the PID
  limit; a disk fill stops at the tmpfs limit and the read-only root; no network; no secrets;
  writes outside the output folder fail.
- **Live:**
  - a cancel during training ends within 5 s;
  - killing the worker or the executor mid-job resumes without a second container;
  - an NYU2 run from the UI to real metrics.

## Order of work

1. **Harness:** generated modules, stdout metric lines, load-time checks (sandbox/pytorch),
   and the shared AST checker (packages/core). Rebuild the image.
2. **Executor:** the tables and their migration, the socket proxy in compose, the executor
   service, the security tests and the Make targets.
3. **Worker stages:** coding (LLM, checks, smoke loop) and experiment.
4. **API and web:** the queue, datasets and artifacts become real; live curves.
5. The exit checks, then delete `legacy/`.
