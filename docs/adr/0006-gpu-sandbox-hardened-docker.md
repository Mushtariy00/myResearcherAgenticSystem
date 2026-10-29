# ADR 0006 — Hardened Docker containers for GPU experiments

- Status: accepted (2026-10-30)

## Context
Generated ML code must run on a real GPU without access to secrets, the network or the host.
In the legacy system it ran as a plain subprocess with the user's full environment.

Constraints:
- **The GPU:** the dev GPU is a GTX 1060 (Pascal).
  - PyTorch 2.15 (28 Oct 2026) dropped CUDA 12.6 wheels, which Pascal needs.
  - R580 is the last Pascal driver branch.
  - gVisor's GPU support (nvproxy) doesn't cover Pascal.
- **NVIDIA Container Toolkit escapes:** older versions had container-escape CVEs
  (CVE-2025-23266 "NVIDIAScape", CVE-2026-24260).

## Decision
- **One fresh container per job** from a pinned image: `pytorch/pytorch:2.14.1-cuda12.6-cudnn9-runtime`
  plus our harness. Agents never choose images, write Dockerfiles or `pip install`.
- **Flags:**
  - `--network none --read-only --tmpfs /tmp --user 10001 --cap-drop ALL`
  - `--security-opt no-new-privileges`, default seccomp
  - `--pids-limit`, `--memory` = `--memory-swap`, `--cpus`, `--shm-size 2g`
  - `--gpus device=0`
  - the dataset mounted read-only; a separate output volume per job; a wall-clock kill
  - no env secrets, no docker.sock, no `--privileged`
- **The harness owns** data splits, loading, metrics and the training loop. Agents write only
  model and loss modules. There are no silent fallbacks (the legacy loop fell back to "generic"
  code and synthetic data), and missing metrics are `null`, never 0.0.
- **Only the `executor` service talks to Docker**, through a socket proxy, and only with its own
  container template. The job id is the container label, so the executor adopts or reaps
  containers after a restart.
- NVIDIA Container Toolkit **1.20.1 or newer**, patched promptly.

## Consequences
- Isolation still shares the host kernel and driver. We move to gVisor `runsc --nvproxy` once the
  server has a supported GPU (Turing or newer; Ampere with at least 16 GB recommended).
- The Phase 0 spike must prove these flags work with the GPU under WSL2 before anything depends
  on them.

## Alternatives considered
- **Kata Containers**: needs whole-GPU VFIO passthrough and IOMMU.
- **Firecracker**: no GPU support.
- **E2B**: CPU only.
- **Modal / SkyPilot**: kept for cloud bursts later.
