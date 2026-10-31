#!/usr/bin/env bash
# Phase 0 spike: prove the hardened GPU sandbox works on this machine before anything depends on it.
#   1. CUDA is visible   2. no network   3. no secrets in env   4. read-only root, writable output
#   5. a short NYU2 training run finishes with real (non-null) metrics
#   6. a failing job is reported as failed (the checker can actually fail)
# Phase 3: generated code from /job/code is checked, loaded and trained (docs/design/experiments.md).
#   7. the depth_unet example trains a dry run with real metrics and ARP-METRIC lines on stdout
#   8. the refused example (import os) ends failed with error_code code.refused, without training
#   9. the wrong_shape example ends with error_code code.shape_mismatch
#  10. the depth_blocks example, built from the harness's blocks, trains a dry run
#  11. the wrong_channels example fails in its forward pass, reported with the shape trace
# Usage: scripts/sandbox-smoke.sh [config]   (default: nyu2-smoke.yaml; use nyu2-epoch.yaml for a full epoch)
set -euo pipefail

cd "$(dirname "$0")/.."
IMAGE="${SANDBOX_IMAGE:-arp-sandbox-pytorch:dev}"
DATASET_DIR="${DATASET_DIR:-/mnt/d/DATASET/nyu2/nyu2_metric_ready}"
MEMORY="${SANDBOX_MEMORY:-4g}"
CONFIG="${1:-nyu2-smoke.yaml}"
VOLUME="arp-smoke-out-$$"

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }

[[ -d "$DATASET_DIR/h5" ]] || { echo "Dataset not found at $DATASET_DIR (set DATASET_DIR)"; exit 1; }

echo "Building $IMAGE ..."
build_log="$(mktemp)"
if ! docker build --progress=plain -t "$IMAGE" sandbox/pytorch >"$build_log" 2>&1; then
  tail -40 "$build_log"
  rm -f "$build_log"
  fail "image build failed (output above)"
fi
rm -f "$build_log"

# The same flags the executor will use (docs/adr/0006-gpu-sandbox-hardened-docker.md).
HARDENING=(
  --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g
  --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges
  --pids-limit 256 --memory "$MEMORY" --memory-swap "$MEMORY" --cpus 3 --shm-size 2g
  --gpus device=0 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility
)

docker volume create "$VOLUME" >/dev/null
trap 'docker volume rm -f "$VOLUME" >/dev/null' EXIT

sandbox() {  # sandbox <entrypoint> [args...]
  docker run "${HARDENING[@]}" -v "$VOLUME:/workspace/out" -v "$DATASET_DIR:/data/nyu2:ro" \
    --entrypoint "$1" "$IMAGE" "${@:2}"
}

# Like sandbox(), with the example's code mounted read-only at /job/code as the executor will do.
# Uses the image's default entrypoint (python -m harness.train); args after the code dir pass through.
sandbox_code() {  # sandbox_code <code_dir> [train args...]
  docker run "${HARDENING[@]}" -v "$VOLUME:/workspace/out" -v "$DATASET_DIR:/data/nyu2:ro" \
    -v "$PWD/$1:/job/code:ro" "$IMAGE" "${@:2}"
}

# Prints "<status> <error_code>" from a results.json, for the generated-code checks.
READ_STATUS='import json, sys
r = json.load(open(sys.argv[1]))
print(r.get("status"), r.get("error_code"))'

# Passes only for status "ok" with every validation metric measured. Uses `python -c`, not a
# heredoc: `docker run` without -i has no stdin, so `python -` would run nothing and "pass".
CHECK_RESULTS='import json, sys
result = json.load(open(sys.argv[1]))
print(json.dumps({k: result.get(k) for k in ("status", "error", "val_metrics", "dataset_warnings", "duration_s")}, indent=2))
metrics = result.get("val_metrics") or {}
sys.exit(0 if result.get("status") == "ok" and metrics and all(v is not None for v in metrics.values()) else 1)'

echo "1/11 CUDA is visible inside the sandbox"
sandbox python -c "import torch, sys; ok = torch.cuda.is_available(); print('   ', torch.__version__, 'cuda', torch.version.cuda, torch.cuda.get_device_name(0) if ok else 'NO GPU'); sys.exit(0 if ok else 1)" \
  && pass "GPU available" || fail "CUDA not available (check nvidia-ctk and the Windows NVIDIA driver)"

echo "2/11 Network is blocked"
if sandbox python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)" >/dev/null 2>&1; then
  fail "the sandbox reached the internet"
fi
pass "no network"

echo "3/11 No secrets in the environment"
if sandbox sh -c 'env | grep -iE "key|token|secret|passw"'; then fail "secret-like variables present"; fi
pass "environment clean"

echo "4/11 Read-only root, writable output"
if sandbox sh -c 'touch /opt/harness/probe' >/dev/null 2>&1; then fail "root filesystem is writable"; fi
pass "root filesystem read-only"
sandbox sh -c 'touch /workspace/out/.probe && rm /workspace/out/.probe' && pass "output folder writable" || fail "output folder not writable"

echo "5/11 NYU2 training ($CONFIG)"
sandbox python -m harness.train --config "/opt/harness/configs/$CONFIG" || true
sandbox python -c "$CHECK_RESULTS" /workspace/out/results.json \
  && pass "training produced real metrics" || fail "training failed (see results above)"

echo "6/11 A failing job is reported as failed"
sandbox python -m harness.train --config /opt/harness/configs/missing.yaml --out /workspace/out/negative >/dev/null 2>&1 || true
if sandbox python -c "$CHECK_RESULTS" /workspace/out/negative/results.json >/dev/null; then
  fail "a broken job was reported as successful"
fi
pass "failure detected (no fake success)"

GEN_CONFIG=/opt/harness/configs/generated-smoke.yaml

echo "7/11 Generated depth_unet trains a dry run with live metrics"
metrics_log="$(sandbox_code sandbox/pytorch/examples/depth_unet \
  --config "$GEN_CONFIG" --dry-run --out /workspace/out/depth_unet 2>&1)" || true
echo "$metrics_log" | grep -q '^ARP-METRIC ' || { echo "$metrics_log" | tail -20; fail "no ARP-METRIC lines on stdout"; }
echo "$metrics_log" | grep -m1 '^ARP-METRIC ' | sed 's/^/    /'
sandbox python -c "$CHECK_RESULTS" /workspace/out/depth_unet/results.json \
  && pass "generated model+loss trained with real metrics" || fail "depth_unet dry run failed"

echo "8/11 Generated refused example (import os) is rejected before training"
refused_log="$(sandbox_code sandbox/pytorch/examples/refused \
  --config "$GEN_CONFIG" --dry-run --out /workspace/out/refused 2>&1)" || true
if echo "$refused_log" | grep -q '^ARP-METRIC '; then fail "the refused example trained anyway"; fi
status_code="$(sandbox python -c "$READ_STATUS" /workspace/out/refused/results.json)"
echo "    $status_code"
[[ "$status_code" == "failed code.refused" ]] \
  && pass "refused with code.refused, no training" \
  || fail "expected 'failed code.refused', got '$status_code'"

echo "9/11 Generated wrong_shape example fails the shape check"
sandbox_code sandbox/pytorch/examples/wrong_shape \
  --config "$GEN_CONFIG" --dry-run --out /workspace/out/wrong_shape >/dev/null 2>&1 || true
status_code="$(sandbox python -c "$READ_STATUS" /workspace/out/wrong_shape/results.json)"
echo "    $status_code"
[[ "$status_code" == "failed code.shape_mismatch" ]] \
  && pass "shape mismatch reported as code.shape_mismatch" \
  || fail "expected 'failed code.shape_mismatch', got '$status_code'"

echo "10/11 Generated depth_blocks (the harness's blocks) trains a dry run"
sandbox_code sandbox/pytorch/examples/depth_blocks \
  --config "$GEN_CONFIG" --dry-run --out /workspace/out/depth_blocks >/dev/null 2>&1 || true
sandbox python -c "$CHECK_RESULTS" /workspace/out/depth_blocks/results.json \
  && pass "the blocks example trained with real metrics" || fail "depth_blocks dry run failed"

echo "11/11 Generated wrong_channels fails its forward pass, reported with the shape trace"
sandbox_code sandbox/pytorch/examples/wrong_channels \
  --config "$GEN_CONFIG" --dry-run --out /workspace/out/wrong_channels >/dev/null 2>&1 || true
READ_ERROR='import json, sys
r = json.load(open(sys.argv[1]))
print(r.get("status"), r.get("error_code"))
print(r.get("error", ""))'
report="$(sandbox python -c "$READ_ERROR" /workspace/out/wrong_channels/results.json)"
echo "$report" | head -4 | sed 's/^/    /'
[[ "$(echo "$report" | head -1)" == "failed train.error" ]] \
  && echo "$report" | grep -q "The forward pass failed inside: Model (Model) > up (UpBlock)" \
  && pass "the forward error came with where it failed and the shapes" \
  || fail "expected 'failed train.error' with the shape trace"
