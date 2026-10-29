#!/usr/bin/env bash
# Checks that this machine is ready for development. Safe to run any time; changes nothing.
set -uo pipefail

ok=0
check() {  # check <label> <command...>   (prints the command's last output line, e.g. after a pull)
  local label="$1"; shift
  if output="$("$@" 2>&1)"; then
    printf '  \033[32m✓\033[0m %-28s %s\n' "$label" "$(grep -v '^\s*$' <<<"$output" | tail -1)"
  else
    printf '  \033[31m✗\033[0m %-28s %s\n' "$label" "$(grep -v '^\s*$' <<<"$output" | tail -1)"
    ok=1
  fi
}
warn_unless() {  # warn_unless <label> <command...>   (recommended, not required)
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  \033[32m✓\033[0m %s\n' "$label"
  else
    printf '  \033[33m!\033[0m %s\n' "$label"
  fi
}
version_at_least() {  # version_at_least <minimum> <command...>
  local minimum="$1"; shift
  local found
  found="$("$@" 2>&1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)" || return 1
  [[ -n "$found" && "$(printf '%s\n%s\n' "$minimum" "$found" | sort -V | head -1)" == "$minimum" ]] \
    && echo "$found" || { echo "found ${found:-nothing}, need >= $minimum"; return 1; }
}

echo "Tools"
check "uv >= 0.13"               version_at_least 0.13 uv --version
check "node >= 24"               version_at_least 24.0 node --version
check "pnpm >= 12"               version_at_least 12.0 pnpm --version
check "docker"                   docker version --format '{{.Server.Version}}'
check "docker compose"           docker compose version --short
check "nvidia-ctk >= 1.20.1"     version_at_least 1.20.1 nvidia-ctk --version

echo "GPU"
check "GPU inside a container"   docker run --rm --gpus all ubuntu:24.04 nvidia-smi --query-gpu=name,driver_version --format=csv,noheader

echo "Machine"
mem_gb="$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo)"
warn_unless "memory $mem_gb GiB (recommended >= 9: set memory=10GB in %UserProfile%\\.wslconfig)" \
  awk -v m="$mem_gb" 'BEGIN { exit (m >= 9) ? 0 : 1 }'
dataset="${DATASET_DIR:-/mnt/d/DATASET/nyu2/nyu2_metric_ready}"
check "NYU2 dataset"             test -d "$dataset/h5"

if [[ $ok -eq 0 ]]; then echo "All good."; else echo "Fix the ✗ items (see scripts/setup-prereqs.sh)."; fi
exit $ok
