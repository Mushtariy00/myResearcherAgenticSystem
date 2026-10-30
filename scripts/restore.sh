#!/usr/bin/env bash
# Restores a backup made by scripts/backup.sh (docs/runbooks/backup-restore.md):
#   1. checks every artifact against the manifest's sha256 before touching anything;
#   2. restores the dump into a NEW database (default arp_restore_<UTC time>);
#   3. extracts the files into a NEW or empty directory (default ARP_BACKUP_DIR/scratch/<database>).
# The live database and ARP_DATA_DIR are written only with --into <live database>
# --yes-replace-live, with the services stopped. The dump is then restored beside the live
# database, the files are extracted over ARP_DATA_DIR, and the live database is renamed to
# <name>_replaced_<UTC time> (kept until someone drops it) as the restored one takes its name.
# Usage: scripts/restore.sh <backup dir> [--into <database>] [--files-into <dir>] [--yes-replace-live]
#        (make restore backup=<dir> [into=<database>] [files=<dir>])
set -euo pipefail
caller_pwd="$PWD"
cd "$(dirname "$0")/.."
# shellcheck source=scripts/backup-common.sh
. scripts/backup-common.sh

usage="usage: scripts/restore.sh <backup dir> [--into <database>] [--files-into <dir>] [--yes-replace-live]"
absolute() {  # paths on the command line are relative to where the script was started
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    "~" | "~/"*) expand_home "$1" ;;
    *) printf '%s\n' "$caller_pwd/$1" ;;
  esac
}
backup="" into="" files_into="" replace_live=0
while (($#)); do
  case "$1" in
    --into) into="${2:?$usage}" && shift 2 ;;
    --files-into) files_into="$(absolute "${2:?$usage}")" && shift 2 ;;
    --yes-replace-live) replace_live=1 && shift ;;
    -h | --help) say "$usage" && exit 0 ;;
    -*) die "unknown option $1 ($usage)" ;;
    *) [[ -z $backup ]] || die "$usage"; backup="$(absolute "$1")" && shift ;;
  esac
done
if [[ -z $backup ]]; then
  say "$usage"
  say "Backups in $backup_root:"
  find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name 'arp-*' 2>/dev/null | LC_ALL=C sort | tail -n 5 >&2
  exit 1
fi
backup="$(realpath -m -- "$backup")"
[[ -f $backup/manifest.json ]] || die "$backup has no manifest.json: not a backup from scripts/backup.sh"
require_tools tar sha256sum flock

umask 077
mkdir -p "$backup_root"
exec 9>"$backup_root/.lock"  # keeps a backup (and its retention) from running meanwhile
flock -n 9 || die "a backup or restore is using $backup_root"
started="$(now_ms)"
ts="$(date -u +%Y%m%d_%H%M%S)"

# The database: a new one, unless the live one is replaced on purpose.
into="${into:-arp_restore_$ts}"
[[ $into =~ $database_name_re ]] ||
  die "--into takes up to 38 lowercase letters, digits and underscores (got '$into')"
is_live=0
for live in "$(postgres_env POSTGRES_DB)" "${ARP_BACKUP_DATABASE:-}"; do
  if [[ $into == "$live" ]]; then is_live=1; fi
done
if ((is_live && !replace_live)); then
  die "$into is the live database. To replace it, stop the services and run" \
    "scripts/restore.sh $backup --into $into --yes-replace-live"
fi
((!replace_live || is_live)) || die "--yes-replace-live only goes with --into <the live database>"
exists="$(sql postgres "SELECT count(*) FROM pg_database WHERE datname = '$into'")"
((is_live || exists == 0)) || die "database $into already exists: restores only create new databases"

# The files: a new or empty directory, or ARP_DATA_DIR itself when replacing the live system.
inside() { [[ $1 == "$2" || $1 == "$2"/* ]]; }  # inside <path> <dir>
if [[ -z $files_into ]]; then
  if ((replace_live)); then files_into="$data_dir"; else files_into="$backup_root/scratch/$into"; fi
fi
target="$(realpath -m -- "$files_into")"
live_files="$(realpath -m -- "$data_dir")"
files_live=0
if inside "$target" "$live_files" && ! inside "$target" "$(realpath -m -- "$backup_root")"; then
  files_live=1
fi
if ((files_live)); then
  ((replace_live)) || die "$target is the live ARP_DATA_DIR or inside it (only with --yes-replace-live)"
  [[ $target == "$live_files" ]] || die "extract into ARP_DATA_DIR itself ($live_files), not below it"
elif [[ -e $target && -n "$(ls -A -- "$target")" ]]; then
  die "$target is not empty: restores only extract into new or empty directories"
fi

sessions_on() { sql postgres "SELECT count(*) FROM pg_stat_activity WHERE datname = '$1'"; }
if ((is_live)); then
  sessions="$(sessions_on "$into")"
  ((sessions == 0)) || die "$sessions sessions are connected to $into: stop the api, worker," \
    "gateway and web first (docs/runbooks/backup-restore.md)"
fi

# Nothing is restored from a damaged or altered backup.
say "Checking $backup against its manifest"
artifacts="$(manifest "$backup" artifacts)"
for required in database.dump files.tar; do
  [[ $'\n'$artifacts == *$'\n'"$required"$'\t'* ]] || die "the manifest lists no $required"
done
while IFS=$'\t' read -r name sha256 bytes; do
  [[ $name =~ ^[a-z0-9][a-z0-9._-]*$ ]] || die "the manifest names an odd artifact: $name"
  [[ -f $backup/$name ]] || die "$name is missing: refusing to restore"
  actual="$(stat -c %s "$backup/$name")"
  [[ $actual == "$bytes" ]] || die "$name is $actual bytes, the manifest says $bytes: refusing to restore"
  actual="$(sha256sum "$backup/$name" | cut -d' ' -f1)"
  [[ $actual == "$sha256" ]] ||
    die "$name has sha256 $actual, the manifest says $sha256: refusing to restore"
  say "  $name: sha256 matches"
done <<<"$artifacts"

# What this run created is removed again if it fails half-way; nothing else is ever dropped.
created_db="" created_dir=""
undo() {
  if [[ -n $created_db ]]; then
    say "Dropping the unfinished database $created_db"
    sql postgres "DROP DATABASE IF EXISTS \"$created_db\" WITH (FORCE)" || true
  fi
  if [[ -n $created_dir ]]; then rm -rf -- "$created_dir"; fi
}
trap undo EXIT

staging="$into"
((!is_live)) || staging="${into}_incoming_$ts"
encoding="$(manifest "$backup" database.encoding)"
collate="$(manifest "$backup" database.collate)"
ctype="$(manifest "$backup" database.ctype)"
for value in "$encoding" "$collate" "$ctype"; do
  [[ $value =~ ^[A-Za-z0-9_.@-]+$ ]] || die "the manifest has an odd encoding or locale: $value"
done
say "Restoring the database into $staging"
# template0 with the source's encoding and locale: an empty database that sorts text as before.
sql postgres "CREATE DATABASE \"$staging\" TEMPLATE template0 ENCODING '$encoding'
              LC_COLLATE '$collate' LC_CTYPE '$ctype'"
created_db="$staging"
# One transaction: the database ends up with the whole dump or with nothing.
pg pg_restore --single-transaction -d "$staging" <"$backup/database.dump"

say "Extracting the files into $target"
if ((!files_live)) && [[ ! -e $target ]]; then created_dir="$target"; fi
mkdir -p -- "$target"
# Modes as archived (the API reads the PDFs). The owner is whoever runs this, which should be
# the services' user. Over ARP_DATA_DIR, files newer than the backup stay: no restored row
# refers to them.
tar -C "$target" --no-same-owner --preserve-permissions -xf "$backup/files.tar"

replaced=""
if ((is_live)); then
  sessions="$(sessions_on "$into")"
  ((sessions == 0)) || die "$sessions sessions connected to $into during the restore: stop the" \
    "services and run this again"
  if ((exists)); then
    # One transaction: the swap happens completely or not at all. The old database is kept.
    replaced="${into}_replaced_$ts"
    sql postgres "BEGIN; ALTER DATABASE \"$into\" RENAME TO \"$replaced\";
                  ALTER DATABASE \"$staging\" RENAME TO \"$into\"; COMMIT;"
  else
    sql postgres "ALTER DATABASE \"$staging\" RENAME TO \"$into\""
  fi
  created_db=""
  # Fresh planner statistics before the services come back; the restore is done either way.
  sql "$into" "ANALYZE" || say "warning: ANALYZE failed; run it on $into once the services are up"
fi
created_db="" created_dir=""

say "Restored $(basename "$backup") in $(secs "$(($(now_ms) - started))")"
say "  database  $into (Alembic head $(manifest "$backup" database.alembic_head))"
if [[ -n $replaced ]]; then say "  previous  $replaced (kept: drop it once the restore is confirmed)"; fi
say "  files     $target ($(manifest "$backup" files.count) files in the backup)"
if ((is_live)); then
  say "Next: uv run alembic -c packages/db/alembic.ini current (it should say (head)), then" \
    "start the services."
else
  say "When done: ${compose[*]} exec postgres dropdb -U $(postgres_env POSTGRES_USER) $into" \
    "&& rm -rf $target"
fi
