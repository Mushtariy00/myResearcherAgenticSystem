#!/usr/bin/env bash
# Phase 3: the Docker socket proxy (docker-proxy in infra/compose/compose.yaml) passes the GPU
# executor's calls and refuses the rest (docs/adr/0006-gpu-sandbox-hardened-docker.md). Every
# request goes through the proxy's socket, as the executor's do:
#   1. the executor's calls get through   2. every other call is refused
#   3. bind mounts only from the jobs folder and the dataset folders
# Containers are created from the sandbox image to see what gets through; none is started, and
# each is removed again. Run it with `make docker-proxy-check` once `make up` has started the
# proxy: the Makefile passes the folders the proxy got. Exits non-zero on any FAIL.
# Usage: scripts/docker-proxy-check.sh
set -euo pipefail

SOCKET="${ARP_DOCKER_SOCKET:-.data/docker-proxy/docker.sock}"
V="/${ARP_DOCKER_API_VERSION:-v1.47}"
IMAGE="${ARP_SANDBOX_IMAGE:-arp-sandbox-pytorch:dev}"
JOBS_DIR="${ARP_JOBS_DIR:?run it with make docker-proxy-check}"
ALLOWLIST="${ARP_DOCKER_BIND_ALLOWLIST:?run it with make docker-proxy-check}"
RUN="arp-proxy-check-$$"  # names whatever a mistake would create
LABEL="arp.docker-proxy-check=$$"
MISSING="$RUN-missing"  # a container that doesn't exist: only the proxy can answer for it
# A job container's name that no container has: the proxy lets it through, and Docker answers.
MISSING_JOB="arp-job-00000000-0000-0000-0000-000000000000"

step=0
passed=0
failed=0
title() { step=$((step + 1)); printf '%d/3 %s\n' "$step" "$1"; }
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; passed=$((passed + 1)); }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; failed=$((failed + 1)); }

answer="$(mktemp)"
spec="$(mktemp)"
probe=""
# On exit, whatever the reason, remove anything of this run's that is still there, through
# Docker's own socket: a broken proxy must not leave it behind.
cleanup() {
  docker ps -aq --filter "label=$LABEL" | xargs -r docker rm -f -v >/dev/null 2>&1 || true
  docker volume rm -f "$RUN" >/dev/null 2>&1 || true
  docker network rm "$RUN" >/dev/null 2>&1 || true
  rm -f "$answer" "$spec"
  if [[ -n $probe ]]; then rmdir "$probe" 2>/dev/null || true; fi
}
trap 'exit 130' INT TERM
trap cleanup EXIT

# call <method> <path> [curl options...]: one request through the proxy. Sets $status (000 when
# the socket can't be reached) and leaves the answer's body in $answer.
call() {
  : >"$answer"
  status="$(curl -sS --max-time 20 --unix-socket "$SOCKET" -o "$answer" -w '%{http_code}' \
    -X "$1" "${@:3}" "http://docker$2" 2>/dev/null || true)"
}

# The start of the last answer, to explain a FAIL.
detail() { if [[ -s $answer ]]; then printf ' (%s)' "$(head -c 160 "$answer" | tr -d '\r\n')"; fi; }

# expect <status> <what> <method> <path> [curl options...]: PASS when the call gets <status>.
expect() {
  local want="$1" what="$2"
  call "${@:3}"
  if [[ $status == "$want" ]]; then
    pass "$what: $status"
  else
    fail "$what: $status, expected $want$(detail)"
  fi
}

json_string() { local s="${1//\\/\\\\}"; printf '"%s"' "${s//\"/\\\"}"; }

# write_spec [HostConfig members]: a container for the sandbox image with this run's label. It
# is never started, and would only run `true` if it were.
write_spec() {
  printf '{"Image": %s, "Entrypoint": ["true"], "Labels": {"arp.docker-proxy-check": "%s"},
    "NetworkDisabled": true, "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": true,
    "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"]%s}}\n' \
    "$(json_string "$IMAGE")" "$$" "${1:+, $1}" >"$spec"
}

# bind <host folder>: a read-only bind mount of it, as the executor's template writes one.
bind() {
  printf '"Mounts": [{"Type": "bind", "Source": %s, "Target": "/mnt/probe", "ReadOnly": true}]' \
    "$(json_string "$1")"
}

# Every container is created with a job container's name, as the executor's are: the proxy
# lets a single container be reached only by such a name.
creates=0
created=""  # the name of the last container created
create() {
  creates=$((creates + 1))
  created="arp-job-$(cat /proc/sys/kernel/random/uuid)"
  call POST "$V/containers/create?name=$created" -H 'Content-Type: application/json' \
    --data-binary "@$spec"
}
created_id() { sed -n 's/.*"Id":"\([0-9a-f]*\)".*/\1/p' "$answer"; }

check_executor_calls() {
  title "The executor's calls get through (agentic_executor.docker), for job containers only"
  local filters='%7B%22label%22%3A%5B%22arp.job%22%5D%7D' id  # {"label":["arp.job"]}
  expect 200 "list containers by label" GET "$V/containers/json?all=1&filters=$filters"
  write_spec "$(bind "$probe")"
  create
  id="$(created_id)"
  if [[ $status != 201 || -z $id ]]; then
    fail "create a container: $status, expected 201$(detail)"
    return
  fi
  pass "create a container named as a job's (a bind from the jobs folder): $status"
  expect 200 "inspect it" GET "$V/containers/$created/json"
  expect 200 "read its logs" GET "$V/containers/$created/logs?stdout=1&stderr=1"
  expect 200 "read a file out of it (archive)" GET "$V/containers/$created/archive?path=/etc/passwd"
  expect 200 "wait for it to stop (it never ran)" POST "$V/containers/$created/wait?condition=not-running"
  expect 304 "stop it (Docker: not running)" POST "$V/containers/$created/stop?t=2"
  expect 409 "kill it (Docker: not running)" POST "$V/containers/$created/kill"
  expect 404 "start a missing job container (Docker: no such container)" POST "$V/containers/$MISSING_JOB/start"
  expect 403 "inspect it by its id rather than its name" GET "$V/containers/$id/json"
  expect 403 "inspect a container that isn't a job's" GET "$V/containers/$MISSING/json"
  expect 403 "stop a container that isn't a job's" POST "$V/containers/$MISSING/stop?t=2"
  expect 403 "remove a container that isn't a job's" DELETE "$V/containers/$MISSING?force=1"
  expect 204 "remove it with its volumes" DELETE "$V/containers/$created?force=1&v=1"
}

check_other_calls() {
  title "Every other call is refused"
  local json=(-H 'Content-Type: application/json' --data-binary)
  expect 403 "GET /images/json" GET "$V/images/json"
  expect 403 "GET /info" GET "$V/info"
  expect 403 "POST /images/create (a pull)" POST "$V/images/create?fromImage=$RUN&tag=none"
  expect 403 "POST /volumes/create" POST "$V/volumes/create" "${json[@]}" "{\"Name\": \"$RUN\"}"
  expect 403 "POST /networks/create" POST "$V/networks/create" "${json[@]}" "{\"Name\": \"$RUN\"}"
  expect 403 "POST /build" POST "$V/build?t=$RUN"
  expect 403 "POST /containers/{id}/exec" POST "$V/containers/$MISSING/exec" "${json[@]}" \
    '{"Cmd": ["true"]}'
  expect 403 "POST /containers/{id}/update (its limits)" POST "$V/containers/$MISSING/update" \
    "${json[@]}" '{"Memory": 0}'
  expect 405 "PUT /containers/{id}/archive (files into it)" PUT \
    "$V/containers/$MISSING/archive?path=/tmp" --data-binary ''
  expect 403 "GET /containers/json without an API version" GET /containers/json
}

# refused <HostConfig members> <what>: a create the proxy must refuse before Docker sees it.
refused() {
  write_spec "$1"
  create
  if [[ $status == 403 ]]; then pass "$2: $status"; else fail "$2: $status, expected 403$(detail)"; fi
}

# allowed <host folder>: a create with a read-only bind of it gets through and is removed again.
allowed() {
  local id
  write_spec "$(bind "$1")"
  create
  id="$(created_id)"
  if [[ $status != 201 || -z $id ]]; then
    local hint=""
    if [[ $status == 403 ]]; then hint=" (the proxy has another list: make up restarts it)"; fi
    fail "a bind of $1: $status, expected 201$(detail)$hint"
    return
  fi
  call DELETE "$V/containers/$created?force=1&v=1"
  if [[ $status == 204 ]]; then
    pass "a bind of $1: 201, then removed"
  else
    fail "a bind of $1: created, but removing it gave $status$(detail)"
  fi
}

check_bind_mounts() {
  title "Bind mounts only from the jobs folder and the dataset folders"
  refused "$(bind /var/run/docker.sock)" "a bind of /var/run/docker.sock"
  refused "$(bind /etc)" "a bind of /etc"
  refused "$(bind /)" "a bind of /"
  refused "$(bind "$JOBS_DIR/../../..")" "a bind of the jobs folder/../../.. (climbs out of it)"
  refused '"Binds": ["/etc:/mnt/probe:ro"]' "/etc as a legacy bind (HostConfig.Binds)"
  refused '"Mounts": [{"Type": "volume", "Target": "/mnt/probe", "VolumeOptions": {"DriverConfig":
    {"Name": "local", "Options": {"type": "none", "o": "bind", "device": "/etc"}}}}]' \
    "/etc as a local volume with o=bind"
  allowed "$probe"
  local folders folder
  IFS=, read -ra folders <<<"$ALLOWLIST"
  for folder in "${folders[@]}"; do
    if [[ $folder == "$JOBS_DIR" ]]; then continue; fi
    if [[ -d $folder ]]; then
      allowed "$folder"
    else
      fail "$folder is in the list, but there is no such folder"
    fi
  done
  if ((${#folders[@]} == 1)); then echo "  (no dataset folder in the list: ARP_DATASET_NYU2 is empty)"; fi
}

[[ -S $SOCKET ]] || { echo "No proxy socket at $SOCKET: start the proxy with make up"; exit 1; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "Image $IMAGE is not available (make sandbox-build)"; exit 1; }
mkdir -p "$JOBS_DIR"
probe="$(mktemp -d "$JOBS_DIR/.docker-proxy-check.XXXXXX")"
echo "Docker socket proxy at $SOCKET (API ${V#/}); bind mounts from $ALLOWLIST"
check_executor_calls
check_other_calls
check_bind_mounts
echo "Summary: $passed passed, $failed failed in $SECONDS s"
if ((failed > 0)); then exit 1; fi
