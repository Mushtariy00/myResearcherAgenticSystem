# Shared by scripts/backup.sh, restore.sh and restore-drill.sh (docs/runbooks/backup-restore.md).
# Sourced from the repo root by scripts that run with `set -euo pipefail`.

# Settings come from the environment first, then from the repo's .env (the file `make` reads), so
# a script started by cron finds the same ARP_DATA_DIR as the services.
if [[ -f .env ]]; then
  while IFS='=' read -r key value; do
    [[ $key =~ ^(ARP|RESTIC)_[A-Z0-9_]+$ && -z ${!key+set} ]] || continue
    if [[ $value =~ ^\"(.*)\"$ || $value =~ ^\'(.*)\'$ ]]; then value="${BASH_REMATCH[1]}"; fi
    export "$key=$value"
  done <.env
fi

expand_home() {  # a leading ~ is the home directory, as Path.expanduser reads it in the services
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s\n' "$HOME/${1#"~/"}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}
# Empty means the default, as in agentic_api.settings.
data_dir="$(expand_home "${ARP_DATA_DIR:-$HOME/.local/share/arp}")"
backup_root="$(expand_home "${ARP_BACKUP_DIR:-$HOME/.local/share/arp/backups}")"

# The dev stack by default; on the server, COMPOSE_FILE (and COMPOSE_ENV_FILES) name its files.
if [[ -n ${COMPOSE_FILE:-} ]]; then
  compose=(docker compose)
else
  compose=(docker compose -f infra/compose/compose.yaml --env-file infra/compose/.env)
fi

# Directories backup.sh makes, and the databases restore.sh may create: short enough that a live
# restore's "<name>_replaced_<time>" still fits in Postgres's 63 characters.
backup_name_re='^arp-[0-9]{8}T[0-9]{6}Z$'
database_name_re='^[a-z_][a-z0-9_]{0,37}$'

say() { printf '%s\n' "$*" >&2; }
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}
now_ms() {  # from /proc/uptime, which never steps: WSL2 and NTP do move the wall clock mid-run
  local uptime
  read -r uptime _ </proc/uptime
  printf '%s\n' "$((10#${uptime/./} * 10))"
}
secs() { printf '%d.%d s' "$(($1 / 1000))" "$(($1 % 1000 / 100))"; }
human() { numfmt --to=iec-i --suffix=B "$1"; }

# pg <program> [args...]: a Postgres client inside the postgres container, as its superuser over
# the local socket. The client always matches the server's version, and no password is involved.
pg() {
  # shellcheck disable=SC2016  # $POSTGRES_USER is the container's, expanded there
  "${compose[@]}" exec -T postgres sh -c 'exec "$0" -U "$POSTGRES_USER" "$@"' "$@"
}

# sql <database> <query>: the result rows, tab-separated, without headers.
sql() {
  pg psql -X -q -A -t -F $'\t' -v ON_ERROR_STOP=1 -d "$1" -c "$2" </dev/null
}

postgres_env() {  # postgres_env <name>: a variable of the postgres container (POSTGRES_DB, ...)
  "${compose[@]}" exec -T postgres printenv "$1" </dev/null
}

# The database the services use: POSTGRES_DB, unless ARP_BACKUP_DATABASE names another.
live_database() {
  if [[ -n ${ARP_BACKUP_DATABASE:-} ]]; then
    printf '%s\n' "$ARP_BACKUP_DATABASE"
  else
    postgres_env POSTGRES_DB
  fi
}

require_tools() {  # require_tools [tool...]: docker and python3 always, and Postgres up
  local tool
  for tool in docker python3 "$@"; do
    command -v "$tool" >/dev/null || die "$tool is not installed"
  done
  sql postgres "SELECT 1" >/dev/null || die "cannot reach the compose stack's Postgres (make up?)"
}

# Exact row counts of every table as "schema.table<TAB>rows", in byte order, which is how Python
# and `LC_ALL=C sort` order them too.
count_rows_sql="SELECT n.nspname || '.' || c.relname,
       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I',
                                                    n.nspname, c.relname), false, true, '')))[1]::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind IN ('r', 'p') AND n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg\\_%'
 ORDER BY (n.nspname || '.' || c.relname) COLLATE \"C\";"

alembic_head_sql="SELECT string_agg(version_num, ',' ORDER BY version_num) FROM public.alembic_version;"

# manifest <backup dir> <field>: a value of its manifest.json by dotted path (files.count), or
# one tab-separated row per entry for "artifacts" (name, sha256, bytes) and "tables" (name, rows).
manifest() {
  python3 -I - "$1/manifest.json" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
field = sys.argv[2]
if field == "artifacts":
    for artifact in manifest["artifacts"]:
        print(artifact["name"], artifact["sha256"], artifact["bytes"], sep="\t")
elif field == "tables":
    for name, rows in sorted(manifest["database"]["tables"].items()):
        print(name, rows, sep="\t")
else:
    value = manifest
    for key in field.split("."):
        value = value[key]
    print(value)
PY
}
