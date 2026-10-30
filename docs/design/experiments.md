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
- Hardware: a GTX 1060 6 GB. The NYU2 export is at `/mnt/d/DATASET/nyu2/nyu2_metric_ready` (h5
  files, read through WSL's drvfs).
- **The export's training depths are not in metres** (found by the harness's unit check, Phase 3
  step 4):
  - they are the NYU2 training set's 8-bit PNG values divided by 1000, as if they were
    millimetres: every one is a multiple of 0.001 up to 0.255, median 0.076;
  - validation is real millimetres / 1000, median 2.75 m;
  - so every metric of a model trained on the export means little.
  - `make nyu2-fix` copies it with the training depths in metres (stored × 1000 / 255 × 10;
    validation unchanged), beside the export on D:. That copy is dataset version 2026.10, and
    ARP_DATASET_NYU2 points at it.
  - Not into WSL's own ext4 disk: that is a VHDX file on a Windows drive, which grows with what
    is written into it and doesn't shrink by itself. A first copy there filled C: (2026-10-31),
    and the WSL disk had to move to D:.

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
- **Docker access:** through a socket proxy in compose (`docker-proxy`, wollomatic
  socket-proxy, pinned).
  - It serves a Unix socket only the host user can open (`.data/docker-proxy/docker.sock`,
    mode 0600). A TCP proxy would not do: WSL forwards localhost ports to Windows, where any
    process, a browser too, could reach it.
  - It allows exactly the executor's calls (GET, POST and DELETE on `/containers/...`) and
    refuses the rest: images, exec, volumes, networks, build, info.
  - Containers may bind-mount only the jobs folder and the dataset folders
    (`-allowbindmountfrom`, from the Makefile). A dataset added later with another folder must
    be added there too.
  - It doesn't check the rest of a create request (privileged mode, capabilities, devices), so
    the executor's template stays the authority on what a container may do.
  - `make docker-proxy-check` shows what gets through and what is refused.
- **Template:** the executor creates containers from its own template alone (ADR 0006 flags,
  `apps/executor/src/agentic_executor/template.py`, every key pinned by its test):
  `--gpus device=0`, `--network none`, read-only root, `--tmpfs /tmp`, user 10001,
  `--cap-drop ALL`, no-new-privileges, `--pids-limit`, memory = memory-swap, `--cpus`,
  `--shm-size 2g`, `--init`.
- **Mounts:**
  - the dataset read-only, at `/data/<name>`;
  - the job's code (`ARP_DATA_DIR/jobs/<id>/code`) and config (`config.json`) read-only;
  - `/workspace/out`: an anonymous volume of the local driver with tmpfs options (size 512m,
    uid and gid 10001, mode 0700), created inline by the create call and removed with the
    container (`DELETE ?v=1`).
    - It is a hard quota, which WSL's ext4 can't give a bind mount.
    - It must be a volume and not a plain tmpfs mount. Docker's archive API reads a running
      container's volumes but not its tmpfs mounts: on Docker 29.9 it returned an empty folder.
    - Its contents are gone once the container stops.
  - tmpfs contents count against the container's memory: a job that fills `/tmp` (1 GiB) and
    its output (512 MiB) has that much less of its `--memory`. Size the memory for the model
    plus both.
- **The job wrapper:** jobs run through `harness.job`, which runs harness.train in a child
  process and is the only writer of the container's output.
  - Metric records reach it on a pipe of their own and go out as `ARP-METRIC` lines.
  - The training's own lines that start with `ARP-` are indented, so generated code can't fake
    a metric or the end of the job.
  - `ARP-DONE {"exit_code": n}` marks the end. Then it waits (up to 15 minutes) until the
    executor has copied the output and stops the container.
- **Container lifecycle:** stop, kill and remove containers through the Docker API, never by
  killing a client process. A `timeout` around `docker run` stops the client, and the
  container keeps running.
- **Queue:** claims the next job with `FOR UPDATE SKIP LOCKED`, at concurrency 1, after a
  VRAM preflight (`nvidia-smi`; it waits while another process holds the GPU).
- **Live metrics:** the harness writes its metric records as JSON lines to stdout, and the
  executor follows the container's logs. Epoch lines become run events
  (`experiment.epoch {epoch, train, val}`) for live curves.
- **At the end:** after `ARP-DONE`, while the container still runs, it copies `/workspace/out`
  out through the archive API into `ARP_DATA_DIR/jobs/<id>/out`: results.json, metrics.jsonl,
  and best.pt if it is under 200 MB, nothing else. Then it records the result and removes the
  container. A container that stops before its output is copied has lost it (`job.lost`).
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
Both run as real stages with `ARP_LLM_STAGES=real` and `ARP_GPU_STAGES=real`, sharing
`agentic_worker.gpu.GpuJobs`. It submits a job once, waits while the user has 2 jobs queued, and
polls the job to its end. Its progress lines say queued, running, and the executor not running.
Only a cancel of the run cancels the job; a timed-out or shut-down activity leaves it running for
the next try. The activity timeouts are 2 h (coding) and 8 h (experiment).
- **Coding** (`coding@1`, role `coding.write`, then `coding.repair`; `agentic_worker.coding`):
  - from the approved method (the recommended option and the implementation focus), the
    dataset's contract and the contract above, the LLM writes `model.py` (and `loss.py`) in
    fenced blocks (code inside JSON strings breaks), plus a JSON block of choices: the model
    kwargs, the loss and the training settings;
  - before any GPU time: the allowlist checker, and the contract (the classes the harness
    builds and the arguments it builds them with);
  - then a smoke job: a dry run of 2 + 2 batches at batch size 2;
  - a failure goes back to the LLM with the findings, or the job's error and log tail, as data;
    at most 3 tries, then the stage fails with `coding.smoke_failed`. A failure of the GPU host
    (`job.bad_input`, `job.start_failed`, `job.lost`) fails it at once: another try of the code
    would fail the same way;
  - the output is CodingOutput: the files, entrypoint `model.py:Model`, the smoke test, and
    `config.json` with the choices and what the smoke test measured (parameters, peak GPU
    memory, steps per second), which the experiment stage trains with.
  - Coding is never auto-approved.
- **Experiment** (`experiment@1`, `agentic_worker.experiment`):
  - the plan: the approved code and its config.json (validated again, since a reviewer may edit
    it on approval), `ARP_EXPERIMENT_EPOCHS` (3) epochs of `ARP_EXPERIMENT_STEPS_PER_EPOCH`
    (1000) steps and full validation. The batch size comes from the smoke test's memory per
    sample and the GPU's free memory in the executor's heartbeat (60% of it, a power of two
    from 2 to 16);
  - one train job; an attempt that runs again waits on the job as it was submitted;
  - the output is ExperimentOutput: series from the job's experiment.epoch events (the worker
    reads the database, never the executor's files), final metrics (null when not measured),
    the log tail, and provenance (image digest, sha256 of code and config, dataset version,
    seed, GPU name, GPU-seconds);
  - status `succeeded | failed | timeout | cancelled` mirrors the job, honestly. A failed
    training is still an output, for the reviewer to judge.
- **Writing:** it stops flagging `writing.simulated_results` once coding and experiment are
  real (their outputs are no longer `stage.demo`).

## API and web

- `GET /gpu/queue` reads `gpu_jobs` in the executor's order, with each job's kind, progress
  (from its latest progress record) and an estimate, and the GPU's readings from the executor's
  heartbeat: `gpu` is null and `executor_alive` false once the heartbeat is a minute old.
- `GET /datasets` reads the enabled rows of `datasets`.
- Artifacts:
  - the code files from CodingOutput;
  - from the training job's files on the GPU host: the full log, metrics.jsonl as CSV, and
    the checkpoint (best.pt), each streamed as an attachment with nosniff. Their sha256 comes
    from the job's provenance (`outputs_sha256`, recorded as the executor copied them).
  - Without the job's files (another host, an older job), the artifacts derived from the
    stage output stay: the log tail and the per-epoch series as CSV.
- The web keeps its stage views. The experiment view gains live curves from
  `experiment.epoch` events, translated like the other progress lines.

## Verification

- **Unit tests:**
  - the AST checker (allowed and refused code, obfuscation attempts);
  - the harness loading generated modules;
  - the executor against a fake Docker API: claim, adopt or reap, cancel compare-and-set,
    timeout, the archive copy.
- **Limit checks on this machine (`make sandbox-limits`, 7 checks in about 6 s):**
  - process count stops at the PID limit;
  - writes stop at the output and /tmp quotas;
  - the root is read-only;
  - memory over the limit is killed while the host and the dev stack keep running;
  - no DNS, HTTPS or raw TCP;
  - no secret-like variables;
  - uid 10001 with no capabilities, no_new_privs and seccomp.
  Each check was also run with its limit weakened, to show it can fail.
- **The socket proxy (`make docker-proxy-check`, 28 checks):**
  - the executor's calls get through;
  - images, info, pulls, volumes, networks, build, exec, update and unversioned paths are
    refused, as is a PUT to archive;
  - bind mounts of the Docker socket, `/etc`, `/` or a `..` path out of the jobs folder are
    refused, and so are legacy `Binds` and bind-type volume options.
  Against a proxy that allows everything, every refusal check fails, which shows the checks
  can fail.
- **Live, the executor (`make executor-check`, 17 checks in about 2 minutes):** it starts an
  executor of its own and submits jobs for a throwaway project, which it removes at the end.
  - A smoke job of the depth_unet example succeeds with real metrics, its provenance, its
    outputs and one epoch event (17 s, 13 GPU seconds), and its container is removed.
  - Refused code fails as code.refused, without a container.
  - A cancel during training ends the job 1.0 s after the request.
  - An executor killed mid-training leaves the container running. The next one adopts it:
    the job succeeds with one container all along, and each epoch event is sent once.
- **Live, the stages (`make stages-check`, 9 checks in about 3 minutes):** the real coding and
  experiment runners, with only the LLM's answer scripted (the depth_unet example), so it needs
  no LLM quota.
  - The coding stage's smoke test passes on the GPU in 16 s; config.json records 12,097
    parameters and a 422 MB peak at batch 2.
  - The experiment plans batch size 8 from that, trains 2 epochs of 100 steps in 167 s, and
    outputs real validation curves, final metrics and provenance.
- **Live, still to do:**
  - killing the worker mid-job resumes without a second job;
  - an NYU2 run from the UI to real metrics, with the LLM writing the code.

## Order of work

1. **Harness (done):** generated modules, stdout metric lines, load-time checks
   (sandbox/pytorch), and the shared AST checker (packages/core). Rebuild the image.
2. **Executor (done):** the tables and their migration, the socket proxy in compose, the
   executor service, the security tests and the Make targets (`make executor`,
   `make docker-proxy-check`, `make executor-check`).
3. **Worker stages (done):** coding (LLM, checks, smoke loop) and experiment
   (`make stages-check`).
4. **API and web:** the queue, datasets and artifacts become real; live curves.
5. The exit checks, then delete `legacy/`.
