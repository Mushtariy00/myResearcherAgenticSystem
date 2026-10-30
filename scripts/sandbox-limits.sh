#!/usr/bin/env bash
# Phase 3 exit check: the training container's resource limits hold (docs/PLAN.md, Phase 3;
# docs/design/experiments.md, "Verification"). Each check runs a small, bounded, benign workload
# in a fresh hardened container and confirms that the limit stops it:
#   1. process limit   2. output quota   3. read-only root   4. memory limit
#   5. no network      6. no secrets     7. unprivileged user
# It uses the existing image (make sandbox-build) and never builds one. Exits non-zero on any FAIL.
# Usage: scripts/sandbox-limits.sh
set -euo pipefail

IMAGE="${SANDBOX_IMAGE:-arp-sandbox-pytorch:dev}"
PIDS_LIMIT=128
RUN_TIMEOUT=60                 # seconds per container, whatever its workload does
LABEL="arp.sandbox-limits=$$"  # marks this run's containers, so any left behind can be removed

# The executor's flags (docs/adr/0006-gpu-sandbox-hardened-docker.md), as in sandbox-smoke.sh,
# with the limits under test: 128 processes, 2 GiB of memory and no swap, and the job's output
# folder as a 512 MiB tmpfs (docs/design/experiments.md). No check needs the GPU; its flags stay
# so that this is the container a job gets.
# tmpfs-mode=1777: without it, Docker gives the tmpfs the mode of the image's /workspace/out (755)
# but not its owner (10001), so the sandbox user could not write its results.
HARDENING=(
  --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g
  --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges
  --pids-limit "$PIDS_LIMIT" --memory 2g --memory-swap 2g --cpus 3 --shm-size 2g
  --gpus device=0 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility
  --mount type=tmpfs,destination=/workspace/out,tmpfs-size=536870912,tmpfs-mode=1777
)

CHECKS=(check_processes check_output_quota check_read_only_root check_memory check_network
  check_secrets check_user)
step=0
check_ok=true
title() { step=$((step + 1)); check_ok=true; printf '%d/%d %s\n' "$step" "${#CHECKS[@]}" "$1"; }
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; check_ok=false; }

# Ctrl-C ends the whole run, not just the current container. On exit, whatever the reason,
# remove any container of this run that is still there.
trap 'exit 130' INT TERM
trap 'docker ps -aq --filter "label=$LABEL" | xargs -r docker rm -f >/dev/null 2>&1 || true' EXIT

# sandbox <entrypoint> [args...]: runs one fresh container and sets $out (its output), $rc (its
# exit code, 124 when it timed out) and ${facts[name]} from the "name: value" lines it printed.
# Snippets use `python -c`, not a heredoc: `docker run` without -i has no stdin.
runs=0
declare -A facts
sandbox() {
  local name="arp-limits-$$-$((runs += 1))" start=$SECONDS key value
  rc=0
  # --foreground lets Ctrl-C reach the container. A timeout kills only the docker client while
  # the container keeps running (its PID 1 ignores signals), so it is removed here by name. The
  # killed client's 137 would look like an OOM kill, so a run that lasted the whole timeout is 124.
  out="$(timeout --foreground --signal=KILL "$RUN_TIMEOUT" docker run "${HARDENING[@]}" \
    --name "$name" --label "$LABEL" --entrypoint "$1" "$IMAGE" "${@:2}" 2>&1)" || rc=$?
  docker rm -f "$name" >/dev/null 2>&1 || true
  if ((SECONDS - start >= RUN_TIMEOUT)); then rc=124; fi
  facts=()
  while read -r key value; do
    if [[ $key == *: ]]; then facts["${key%:}"]="$value"; fi
  done <<<"$out"
}

# How the last container ended, when that explains a FAIL: a timeout or a non-zero exit.
outcome() {
  if ((rc == 124)); then
    echo " (timed out after $RUN_TIMEOUT s)"
  elif ((rc != 0)); then
    echo " (exit $rc: $(tail -n 1 <<<"$out"))"
  fi
}

# 1. Starts up to 400 short sleeps, stops at the first failed fork, then kills and reaps them all.
# Only EAGAIN means the PID limit; any other error is raised, so the check cannot pass by accident.
SPAWN_SLEEPS='import errno, subprocess
children, stopped_by = [], "nothing"
try:
    for _ in range(400):
        children.append(subprocess.Popen(["sleep", "30"]))
except OSError as error:
    if error.errno != errno.EAGAIN:
        raise
    stopped_by = error.strerror
for child in children:
    child.kill()
    child.wait()
print(f"started: {len(children)}")
print(f"stopped_by: {stopped_by}")'

check_processes() {
  title "Process limit (--pids-limit $PIDS_LIMIT)"
  sandbox python -c "$SPAWN_SLEEPS"
  local started="${facts[started]:-}"
  if [[ $rc -eq 0 && $started =~ ^[0-9]+$ ]] && ((started < PIDS_LIMIT)); then
    pass "$started of 400 sleeps started, then a fork failed (${facts[stopped_by]:-?}); the container exited cleanly"
  else
    fail "${started:-no} sleeps started (stopped by: ${facts[stopped_by]:-?})$(outcome)"
  fi
}

# 2. Writes zeros 1 MiB at a time, up to the given size, and reports how far it got and why.
FILL='import sys
path, size = sys.argv[1], int(sys.argv[2]) << 20
block, written, error = bytes(1 << 20), 0, "none"
try:
    with open(path, "wb", buffering=0) as target:
        while written < size:
            written += target.write(block)
except OSError as e:
    error = e.strerror
print(f"written_mib: {written >> 20}")
print(f"error: {error}")'

check_output_quota() {
  title "Output quota (tmpfs: 512 MiB at /workspace/out, 1 GiB at /tmp)"
  fill_stops /workspace/out 700 600
  fill_stops /tmp 1200 1200
}

# fill_stops <folder> <MiB to write> <MiB it must stop below>, in a fresh container each.
fill_stops() {
  sandbox python -c "$FILL" "$1/fill" "$2"
  local written="${facts[written_mib]:-}" error="${facts[error]:-}"
  if [[ $rc -eq 0 && $error == "No space left on device" && $written =~ ^[0-9]+$ ]] && ((written < $3)); then
    pass "$1: writing $2 MiB failed at $written MiB ($error)"
  else
    fail "$1: writing $2 MiB stopped at ${written:-?} MiB (${error:-no result})$(outcome)"
  fi
}

# 3. Tries to create, write and delete a file in each folder; reports "writable" or the error.
TRY_WRITES='import os, sys
for folder in sys.argv[1:]:
    path = os.path.join(folder, "limits-probe")
    try:
        with open(path, "w") as probe:
            probe.write("probe")
        os.remove(path)
        print(f"{folder}: writable")
    except OSError as e:
        print(f"{folder}: {e.strerror}")'

check_read_only_root() {
  title "Read-only root (--read-only)"
  sandbox python -c "$TRY_WRITES" /opt/harness /workspace /workspace/out /tmp
  local folder
  # Only EROFS proves the read-only root: these folders belong to root, so uid 10001 would be
  # refused on a writable root too, with "Permission denied".
  for folder in /opt/harness /workspace; do
    if [[ ${facts[$folder]:-} == "Read-only file system" ]]; then
      pass "$folder: creating a file fails (Read-only file system)"
    else
      fail "$folder: ${facts[$folder]:-no result$(outcome)}, expected Read-only file system"
    fi
  done
  for folder in /workspace/out /tmp; do
    if [[ ${facts[$folder]:-} == writable ]]; then
      pass "$folder stays writable"
    else
      fail "$folder is not writable: ${facts[$folder]:-no result$(outcome)}"
    fi
  done
}

# 4. Holds 256 MiB more at each step, up to 3 GiB, and reports each step as it goes.
HOG='held = []
for step in range(1, 13):
    held.append(b"x" * (256 << 20))  # filled, so every page is really in memory
    print(f"holding_mib: {step * 256}", flush=True)
print("finished: held all 3072 MiB")'

# The running Compose containers (the dev stack) with their start times: one that was killed or
# restarted shows up as missing or changed.
dev_stack() {
  local ids
  mapfile -t ids < <(docker ps -q --filter label=com.docker.compose.project)
  if ((${#ids[@]} == 0)); then return 0; fi
  docker inspect --format '{{slice .Name 1}} {{.State.StartedAt}}' "${ids[@]}" 2>/dev/null | sort || true
}

check_memory() {
  title "Memory limit (--memory 2g, --memory-swap 2g)"
  local before after changed
  before="$(dev_stack)"
  sandbox python -c "$HOG"
  # 137 is SIGKILL: the OOM killer of the container's cgroup stopped the snippet.
  if [[ $rc -eq 137 && -z ${facts[finished]:-} ]]; then
    pass "allocating 3 GiB in 256 MiB steps was killed (exit 137) after holding ${facts[holding_mib]:-0} MiB"
  else
    fail "the 3 GiB allocation was not stopped: ${facts[finished]:-no result}$(outcome)"
  fi
  after="$(dev_stack)"
  changed="$(comm -23 <(printf '%s\n' "$before") <(printf '%s\n' "$after") | cut -d' ' -f1 | paste -sd' ' -)"
  if [[ -z $before ]]; then
    pass "the host kept running (no dev stack was running to watch)"
  elif [[ -z $changed ]]; then
    pass "the host and the dev stack kept running ($(wc -l <<<"$before") containers, none restarted)"
  else
    fail "dev stack containers stopped or restarted: $changed"
  fi
}

# 5. Tries DNS, HTTPS by name, and TCP to an address (no DNS needed); reports "reached" or why not.
TRY_NETWORK='import socket, urllib.request
def attempt(name, action):
    try:
        action()
        print(f"{name}: reached")
    except OSError as e:
        print(f"{name}: blocked, {e}")
attempt("dns", lambda: socket.getaddrinfo("example.com", 443))
attempt("https", lambda: urllib.request.urlopen("https://example.com", timeout=5))
attempt("tcp", lambda: socket.create_connection(("1.1.1.1", 443), timeout=5).close())'

check_network() {
  title "No network (--network none)"
  sandbox python -c "$TRY_NETWORK"
  blocked dns "DNS resolution of example.com"
  blocked https "HTTPS request to example.com"
  blocked tcp "TCP connection to 1.1.1.1:443 (no DNS needed)"
}

# blocked <fact> <what was tried>
blocked() {
  local result="${facts[$1]:-no result$(outcome)}"
  if [[ $result == "blocked, "* ]]; then
    pass "$2 fails (${result#blocked, })"
  else
    fail "$2: $result"
  fi
}

# 6. Lists the names, never the values, of variables that look like secrets.
SECRET_NAMES='import os, re
found = sorted(name for name in os.environ if re.search("key|token|secret|passw", name, re.I))
print(f"variables: {len(os.environ)}")
print("secret_like: " + (" ".join(found) or "none"))'

check_secrets() {
  title "No secrets in the environment"
  sandbox python -c "$SECRET_NAMES"
  if [[ $rc -eq 0 && ${facts[secret_like]:-} == none ]]; then
    pass "none of the ${facts[variables]:-?} variables has key, token, secret or passw in its name"
  else
    fail "secret-like variables: ${facts[secret_like]:-no result$(outcome)}"
  fi
}

# 7. The user id, then the capability sets, no_new_privs and the seccomp mode of a process.
USER_FACTS='echo "uid: $(id -u)"; grep -E "^(Cap[A-Za-z]+|NoNewPrivs|Seccomp):" /proc/self/status'

check_user() {
  title "Unprivileged user (--user 10001, --cap-drop ALL, no-new-privileges)"
  sandbox sh -c "$USER_FACTS"
  if [[ ${facts[uid]:-} == 10001 ]]; then
    pass "id -u is 10001"
  else
    fail "id -u is ${facts[uid]:-unknown$(outcome)}"
  fi
  local set held=""
  for set in CapInh CapPrm CapEff CapBnd CapAmb; do
    if [[ ${facts[$set]:-} != 0000000000000000 ]]; then held+=" $set=${facts[$set]:-missing}"; fi
  done
  if [[ -z $held ]]; then
    pass "no capabilities: CapInh, CapPrm, CapEff, CapBnd and CapAmb are all 0"
  else
    fail "capabilities set:$held"
  fi
  # no-new-privileges and the default seccomp profile are ADR 0006 flags too.
  if [[ ${facts[NoNewPrivs]:-} == 1 && ${facts[Seccomp]:-} == 2 ]]; then
    pass "no_new_privs is set and the seccomp filter is on"
  else
    fail "NoNewPrivs is ${facts[NoNewPrivs]:-?} and Seccomp ${facts[Seccomp]:-?}, expected 1 and 2"
  fi
}

docker image inspect "$IMAGE" >/dev/null || { echo "Image $IMAGE is not available (make sandbox-build)"; exit 1; }
image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
image_id="${image_id#sha256:}"
echo "Limits of $IMAGE (${image_id:0:12}): a fresh container per run, $RUN_TIMEOUT s at most each"
passed=0
failed=0
for check in "${CHECKS[@]}"; do
  "$check"
  if $check_ok; then passed=$((passed + 1)); else failed=$((failed + 1)); fi
done
echo "Summary: $passed passed, $failed failed in $SECONDS s"
if ((failed > 0)); then exit 1; fi
