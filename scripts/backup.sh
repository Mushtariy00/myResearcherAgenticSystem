#!/usr/bin/env bash
# Backs up the system of record (docs/adr/0005-storage-postgres-filesystem.md) into a new
# directory ARP_BACKUP_DIR/arp-<UTC time> (default ~/.local/share/arp/backups):
#   database.dump  pg_dump -Fc of the whole database: our tables and Better Auth's auth schema
#   files.tar      ARP_DATA_DIR (the PDFs under papers/), without the backups themselves
#   manifest.json  time, Alembic head, row counts, files' count and bytes, sha256s, git commit
# Keeps the newest ARP_BACKUP_KEEP backups (default 7). When RESTIC_REPOSITORY is set, the new
# backup also goes off-box with restic. Prints the backup's path on stdout, progress on stderr.
# Exit status: 0 done, 1 no backup made, 2 local backup made but the restic copy failed.
# Usage: scripts/backup.sh   (make backup; docs/runbooks/backup-restore.md)
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/backup-common.sh
. scripts/backup-common.sh

umask 077  # the dump holds password hashes and session tokens: owner-only files
keep="${ARP_BACKUP_KEEP:-7}"
[[ $keep =~ ^[1-9][0-9]*$ ]] || die "ARP_BACKUP_KEEP must be a whole number above 0 (got '$keep')"
# A missing directory is more likely a wrong ARP_DATA_DIR than an empty library.
[[ -d $data_dir ]] || die "ARP_DATA_DIR $data_dir does not exist (mkdir -p it if there are no files yet)"
backups_in_data="$(realpath -m --relative-to="$data_dir" "$backup_root")"
[[ $backups_in_data != . ]] || die "ARP_BACKUP_DIR must not be ARP_DATA_DIR itself"
require_tools tar sha256sum flock
db="$(live_database)"

mkdir -p "$backup_root"
exec 9>"$backup_root/.lock"
flock -n 9 || die "another backup or restore is using $backup_root"

started="$(now_ms)"
while :; do  # the name is the time, so one backup per second (WSL2's clock even steps back)
  epoch="$(date -u +%s)"
  name="arp-$(date -u -d "@$epoch" +%Y%m%dT%H%M%SZ)"
  [[ -e $backup_root/$name ]] || break
  sleep 1
done
final="$backup_root/$name"
partial="$backup_root/.$name.partial"
# The backup is built under a hidden name and renamed when complete, so a directory named
# arp-<time> is always a whole backup. With the lock held, older partial ones are from crashes.
rm -rf -- "$backup_root"/.arp-*.partial
mkdir "$partial"
snapshot_errors="$(mktemp)"
trap 'rm -rf -- "$partial" "$snapshot_errors"' EXIT
say "Backing up database $db and $data_dir into $final"

# The dump and the manifest must describe the same moment, or a drill on a busy server would fail
# on rows written in between: one REPEATABLE READ transaction stays open, pg_dump reuses its
# snapshot, and the manifest's numbers are read inside it.
coproc snapshot { pg psql -X -q -A -t -F $'\t' -v ON_ERROR_STOP=1 -d "$db" 2>"$snapshot_errors"; }
# Bash unsets the coproc's variables when it exits; plain copies keep the error path working.
snapshot_out="${snapshot[0]}" snapshot_in="${snapshot[1]}" snapshot_pid="$snapshot_PID"
in_snapshot() {  # in_snapshot <statement;>: its rows into $rows
  local line
  rows=""
  printf '%s\n\\echo __arp_end__\n' "$1" >&"$snapshot_in"
  while IFS= read -r line <&"$snapshot_out"; do
    if [[ $line == __arp_end__ ]]; then
      rows="${rows%$'\n'}"
      return 0
    fi
    rows+="$line"$'\n'
  done
  cat "$snapshot_errors" >&2
  die "the database session holding the snapshot ended"
}
in_snapshot "BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;"
in_snapshot "SELECT pg_export_snapshot();"
snapshot_id="$rows"
in_snapshot "$alembic_head_sql"
alembic_head="$rows"
in_snapshot "$count_rows_sql"
tables="$rows"
in_snapshot "SELECT current_setting('server_version'), pg_encoding_to_char(encoding), datcollate,
                    datctype
               FROM pg_database WHERE datname = current_database();"
IFS=$'\t' read -r server_version encoding collate ctype <<<"$rows"

say "  database.dump"
pg pg_dump -Fc --snapshot="$snapshot_id" -d "$db" </dev/null >"$partial/database.dump"
in_snapshot "COMMIT;"
exec {snapshot_in}>&-  # end of input: psql exits
wait "$snapshot_pid" 2>/dev/null || true

# The files after the database: the worker writes a PDF before the row that names it, so every
# file the dump refers to is already on disk.
say "  files.tar"
excludes=(--no-wildcards-match-slash --exclude='.*.tmp')  # write_atomic's unfinished files
case "$backups_in_data" in
  .. | ../* | /*) ;;                                # the backups live elsewhere
  *) excludes+=(--exclude="./$backups_in_data") ;;  # e.g. the default, <data>/backups
esac
# Exit status 1 only means a file changed while tar read it: a PDF stored in the meantime, which
# the dump does not refer to.
tar -C "$data_dir" "${excludes[@]}" -cf "$partial/files.tar" . || [[ $? -eq 1 ]]
file_stats="$(tar -tvf "$partial/files.tar" | awk '/^-/ { n++; b += $3 } END { printf "%d %.0f", n, b }')"
read -r file_count file_bytes <<<"$file_stats"

artifacts=""
for artifact in database.dump files.tar; do
  sha256="$(sha256sum "$partial/$artifact" | cut -d' ' -f1)"
  artifacts+="$artifact"$'\t'"$sha256"$'\t'"$(stat -c %s "$partial/$artifact")"$'\n'
done
git_commit="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
git_dirty=false
[[ -z "$(git status --porcelain 2>/dev/null)" ]] || git_dirty=true

say "  manifest.json"
M_NAME="$name" M_CREATED="$(date -u -d "@$epoch" +%FT%TZ)" M_HOST="$(hostname)" \
  M_DURATION_MS="$(($(now_ms) - started))" M_GIT_COMMIT="$git_commit" M_GIT_DIRTY="$git_dirty" \
  M_DB="$db" M_SERVER_VERSION="$server_version" M_ENCODING="$encoding" M_COLLATE="$collate" \
  M_CTYPE="$ctype" M_ALEMBIC_HEAD="$alembic_head" M_TABLES="$tables" M_DATA_DIR="$data_dir" \
  M_FILE_COUNT="$file_count" M_FILE_BYTES="$file_bytes" M_ARTIFACTS="$artifacts" \
  python3 -I - "$partial/manifest.json" <<'PY'
import json
import os
import sys

env = os.environ


def rows(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.splitlines() if line]


manifest = {
    "format": 1,
    "name": env["M_NAME"],
    "created_at": env["M_CREATED"],
    "duration_seconds": round(int(env["M_DURATION_MS"]) / 1000, 1),
    "host": env["M_HOST"],
    "git_commit": env["M_GIT_COMMIT"],
    "git_dirty": env["M_GIT_DIRTY"] == "true",
    "database": {
        "name": env["M_DB"],
        "server_version": env["M_SERVER_VERSION"],
        "encoding": env["M_ENCODING"],
        "collate": env["M_COLLATE"],
        "ctype": env["M_CTYPE"],
        "alembic_head": env["M_ALEMBIC_HEAD"],
        "tables": {name: int(count) for name, count in rows(env["M_TABLES"])},
    },
    "files": {
        "source": env["M_DATA_DIR"],
        "count": int(env["M_FILE_COUNT"]),
        "bytes": int(env["M_FILE_BYTES"]),
    },
    "artifacts": [
        {"name": name, "sha256": sha256, "bytes": int(size)}
        for name, sha256, size in rows(env["M_ARTIFACTS"])
    ],
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2)
    handle.write("\n")
PY

sync -- "$partial"/* "$partial"
mv -T -- "$partial" "$final"
sync -- "$backup_root"

# Retention: the newest $keep backups stay. Only directories named like this script's count.
mapfile -t backups < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name 'arp-*' -printf '%f\n' |
  grep -E "$backup_name_re" | LC_ALL=C sort)
if ((${#backups[@]} > keep)); then
  for old in "${backups[@]:0:${#backups[@]}-keep}"; do
    say "  removing the old backup $old (ARP_BACKUP_KEEP=$keep)"
    rm -rf -- "${backup_root:?}/$old"
  done
fi

size="$(du -sb "$final" | cut -f1)"
say "Backup $name: $(human "$size") in $(secs "$(($(now_ms) - started))") (Alembic head" \
  "$alembic_head, $(awk -F'\t' '{ n += $2 } END { printf "%.0f", n }' <<<"$tables") rows," \
  "$file_count files of $(human "$file_bytes"))"

status=0
if [[ -n ${RESTIC_REPOSITORY:-} ]]; then
  # Credentials in a repository URL (rest:https://user:pass@host/) stay out of the output.
  repository="$(sed -E 's#(://)[^/@]*@#\1***@#' <<<"$RESTIC_REPOSITORY")"
  if ! command -v restic >/dev/null; then
    say "warning: restic is not installed, so this backup did not go off-box to $repository"
  elif [[ -z ${RESTIC_PASSWORD_FILE:-}${RESTIC_PASSWORD_COMMAND:-}${RESTIC_PASSWORD:-} ]]; then
    say "error: no restic password (set RESTIC_PASSWORD_FILE): $name did not go off-box"
    status=2
  else
    say "Sending $name to $repository"
    # Backup only, never forget/prune: the server's key can then be append-only (the runbook).
    if ! restic backup --tag arp "$final" </dev/null >&2; then
      say "error: restic failed; the local backup stays at $final"
      status=2
    fi
  fi
fi
printf '%s\n' "$final"
exit "$status"
