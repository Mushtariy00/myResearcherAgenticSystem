#!/usr/bin/env bash
# The restore drill (monthly; docs/runbooks/backup-restore.md). Takes a fresh backup with
# scripts/backup.sh, restores it with scripts/restore.sh into a scratch database
# (arp_drill_<UTC time>) and a scratch directory, and checks that
#   - the Alembic head is the live one, and `alembic current` reads it as the code's head;
#   - every table has the manifest's row count;
#   - the foreign keys hold;
#   - sampled PDFs hash to their papers.pdf_sha256;
#   - the auth schema has the live users.
# The scratch database and directory are dropped at the end (kept with --keep). Prints a
# PASS/FAIL summary with timings and exits non-zero on any failure. The backup itself is kept,
# like any other.
# Usage: scripts/restore-drill.sh [--keep]   (make restore-drill [keep=1])
set -euo pipefail
shopt -s inherit_errexit
cd "$(dirname "$0")/.."
# shellcheck source=scripts/backup-common.sh
. scripts/backup-common.sh

keep=0
case "${1:-}" in
  "") ;;
  --keep) keep=1 ;;
  *) die "usage: scripts/restore-drill.sh [--keep]" ;;
esac
require_tools sha256sum flock
live_db="$(live_database)"
pdf_sample=50  # enough to catch a broken archive or a wrong path without hashing a whole library
drill_started="$(now_ms)"

# The clean-up drops the scratch database by name, so the name must be this drill's alone: one
# drill at a time, and a name that is not taken yet.
mkdir -p "$backup_root"
exec 8>"$backup_root/.drill.lock"
flock -n 8 || die "another restore drill is running"
while :; do
  drill_db="arp_drill_$(date -u +%Y%m%d_%H%M%S)"
  drill_files="$backup_root/scratch/$drill_db"
  taken="$(sql postgres "SELECT count(*) FROM pg_database WHERE datname = '$drill_db'")"
  [[ -e $drill_files || $taken != 0 ]] || break
  sleep 1
done
work="$(mktemp -d)"
results=()  # status<TAB>label<TAB>milliseconds<TAB>detail
backup_dir="" restore_ok=0 cleaned=0

on_exit() {  # an interrupted drill still removes its scratch copies
  rm -rf -- "$work"
  if ((!keep && !cleaned)); then
    sql postgres "DROP DATABASE IF EXISTS \"$drill_db\" WITH (FORCE)" >/dev/null 2>&1 ||
      say "warning: could not drop the scratch database $drill_db"
    rm -rf -- "$drill_files"
  fi
}
trap on_exit EXIT

record() { results+=("$1"$'\t'"$2"$'\t'"$3"$'\t'"$4"); }  # record <status> <label> <ms> <detail>

# A check runs in its own subshell, where set -e stops it at the first failing command, and ends
# with pass, fail or skip. Anything else (a query error, say) counts as a failure.
pass() { printf 'PASS\t%s\n' "$*" && exit 0; }
fail() { printf 'FAIL\t%s\n' "$*" && exit 0; }
skip() { printf 'SKIP\t%s\n' "$*" && exit 0; }
run_check() {  # run_check <label> <function>
  local start rc=0 last
  start="$(now_ms)"
  "$2" >"$work/check" 2>&1 &
  wait "$!" || rc=$?
  last="$(tail -n 1 "$work/check")"
  if ((rc == 0)) && [[ $last =~ ^(PASS|FAIL|SKIP)$'\t' ]]; then
    record "${last%%$'\t'*}" "$1" "$(($(now_ms) - start))" "${last#*$'\t'}"
  else
    # The error itself (psql ends its message with a caret line under the query).
    last="$(grep -m 1 -iE 'error' "$work/check" || tail -n 1 "$work/check")"
    record FAIL "$1" "$(($(now_ms) - start))" "stopped (exit $rc): ${last:-no output}"
  fi
}

check_alembic_head() {
  local restored live expected
  restored="$(sql "$drill_db" "$alembic_head_sql")"
  live="$(sql "$live_db" "$alembic_head_sql")"
  expected="$(manifest "$backup_dir" database.alembic_head)"
  [[ -n $restored ]] || fail "the restored alembic_version is empty"
  [[ $restored == "$expected" ]] || fail "restored $restored, the manifest says $expected"
  [[ $restored == "$live" ]] || fail "restored $restored, live is $live"
  pass "$restored = live = manifest"
}

check_alembic_current() {  # the app's own migration tool, through the app's database URL
  local url output
  command -v uv >/dev/null && [[ -n ${ARP_DATABASE_URL:-} ]] || skip "needs uv and ARP_DATABASE_URL"
  # ARP_DATABASE_URL pointed at the scratch database; the URL holds a password, so it only ever
  # travels in the environment.
  url="$(DRILL_DB="$drill_db" python3 -I -c 'import os, urllib.parse as u
p = u.urlsplit(os.environ["ARP_DATABASE_URL"])
print(u.urlunsplit(p._replace(path="/" + os.environ["DRILL_DB"])))')"
  output="$(ARP_DATABASE_URL="$url" uv run --no-sync alembic -c packages/db/alembic.ini current 2>&1)" ||
    fail "alembic current failed: ${output##*$'\n'}"
  output="${output##*$'\n'}"
  [[ $output == "$(manifest "$backup_dir" database.alembic_head) (head)" ]] || fail "alembic current: $output"
  pass "$output"
}

check_row_counts() {
  local expected restored differences
  expected="$(manifest "$backup_dir" tables)"
  restored="$(sql "$drill_db" "$count_rows_sql")"
  if [[ $restored != "$expected" ]]; then
    differences="$(diff <(printf '%s\n' "$expected") <(printf '%s\n' "$restored") | grep -E '^[<>]' |
      head -n 6 | tr '\t\n' '= ' || true)"
    fail "differs from the manifest (< manifest, > restored): $differences"
  fi
  pass "$(grep -c . <<<"$restored") tables, $(awk -F'\t' '{ n += $2 } END { printf "%.0f", n }' \
    <<<"$restored") rows = manifest"
}

# Orphans along the relations the app leans on. pg_restore re-creates and validates every
# constraint, so these check the data, not just the catalog.
orphans_sql="
SELECT 'run_papers->papers', count(*) FROM run_papers x LEFT JOIN papers y ON y.id = x.paper_id WHERE y.id IS NULL
UNION ALL
SELECT 'run_papers->stage_runs', count(*) FROM run_papers x LEFT JOIN stage_runs y ON y.id = x.stage_run_id WHERE y.id IS NULL
UNION ALL
SELECT 'stage_runs->runs', count(*) FROM stage_runs x LEFT JOIN runs y ON y.id = x.run_id WHERE y.id IS NULL
UNION ALL
SELECT 'stage_outputs->stage_runs', count(*) FROM stage_outputs x LEFT JOIN stage_runs y ON y.id = x.stage_run_id WHERE y.id IS NULL
UNION ALL
SELECT 'approvals->stage_outputs', count(*) FROM approvals x LEFT JOIN stage_outputs y ON y.id = x.stage_output_id WHERE y.id IS NULL
UNION ALL
SELECT 'run_events->runs', count(*) FROM run_events x LEFT JOIN runs y ON y.id = x.run_id WHERE y.id IS NULL
UNION ALL
SELECT 'runs->projects', count(*) FROM runs x LEFT JOIN projects y ON y.id = x.project_id WHERE y.id IS NULL
UNION ALL
SELECT 'auth.session->auth.user', count(*) FROM auth.session x LEFT JOIN auth.\"user\" y ON y.id = x.\"userId\" WHERE y.id IS NULL
UNION ALL
SELECT 'auth.account->auth.user', count(*) FROM auth.account x LEFT JOIN auth.\"user\" y ON y.id = x.\"userId\" WHERE y.id IS NULL;"

check_foreign_keys() {
  local constraints_sql live restored differing total unvalidated spots bad
  constraints_sql="SELECT conrelid::regclass::text, conname, convalidated FROM pg_constraint
                    WHERE contype = 'f' ORDER BY conrelid::regclass::text COLLATE \"C\", conname;"
  live="$(sql "$live_db" "$constraints_sql")"
  restored="$(sql "$drill_db" "$constraints_sql")"
  if [[ $restored != "$live" ]]; then
    differing="$(diff <(printf '%s\n' "$live") <(printf '%s\n' "$restored") | grep -E '^[<>]' |
      head -n 4 | tr '\t\n' '  ' || true)"
    fail "the constraints differ from live (< live, > restored): $differing"
  fi
  total="$(grep -c . <<<"$restored" || true)"
  unvalidated="$(grep -c $'\tf$' <<<"$restored" || true)"
  spots="$(sql "$drill_db" "$orphans_sql")"
  bad="$(awk -F'\t' '$2 != 0 { printf "%s has %s orphans; ", $1, $2 }' <<<"$spots")"
  [[ -z $bad ]] || fail "$bad"
  pass "$total as live ($unvalidated not validated), no orphans in $(grep -c . <<<"$spots") spot checks"
}

check_files() {
  local count bytes stats restored_count restored_bytes
  count="$(manifest "$backup_dir" files.count)"
  bytes="$(manifest "$backup_dir" files.bytes)"
  stats="$(find "$drill_files" -type f -printf '%s\n' | awk '{ n++; b += $1 } END { printf "%d %.0f", n, b }')"
  read -r restored_count restored_bytes <<<"$stats"
  [[ $restored_count == "$count" && $restored_bytes == "$bytes" ]] ||
    fail "restored $restored_count files of $restored_bytes bytes, the manifest says $count of $bytes"
  pass "$count files, $(human "$bytes") = manifest"
}

check_pdf_sample() {
  local counts papers with_pdf shas sha file checked=0
  counts="$(sql "$drill_db" "SELECT count(*), count(pdf_sha256) FROM papers")"
  read -r papers with_pdf <<<"$counts"
  ((with_pdf > 0)) || skip "no paper has a stored PDF (0 of $papers papers)"
  shas="$(sql "$drill_db" "SELECT sha FROM (SELECT DISTINCT pdf_sha256 AS sha FROM papers
                                             WHERE pdf_sha256 IS NOT NULL) s
                            ORDER BY random() LIMIT $pdf_sample")"
  while read -r sha; do
    [[ $sha =~ ^[0-9a-f]{64}$ ]] || fail "papers.pdf_sha256 is not a SHA-256: '$sha'"
    file="$drill_files/papers/${sha:0:2}/$sha.pdf"  # agentic_scholarly.storage.pdf_path
    [[ -f $file ]] || fail "no file papers/${sha:0:2}/$sha.pdf for a paper that has one"
    [[ "$(sha256sum "$file" | cut -d' ' -f1)" == "$sha" ]] ||
      fail "papers/${sha:0:2}/$sha.pdf does not hash to its pdf_sha256"
    checked=$((checked + 1))
  done <<<"$shas"
  pass "$checked sampled PDFs hash to their papers.pdf_sha256 ($with_pdf of $papers papers have one)"
}

check_users() {
  local users_sql live restored count differing
  users_sql="SELECT id, coalesce(email, ''), coalesce(role, '') FROM auth.\"user\" ORDER BY id COLLATE \"C\";"
  live="$(sql "$live_db" "$users_sql")"
  restored="$(sql "$drill_db" "$users_sql")"
  count="$(grep -c . <<<"$restored" || true)"
  if [[ $restored != "$live" ]]; then
    # Only ids go into the log, not emails.
    differing="$(diff <(cut -f1 <<<"$live") <(cut -f1 <<<"$restored") | grep -E '^[<>]' | head -n 5 |
      tr '\n' ' ' || true)"
    [[ -n $differing ]] || differing="the same ids with other emails or roles"
    fail "restored $count users, live has $(grep -c . <<<"$live" || true): $differing" \
      "(a user changed since the backup shows up here too)"
  fi
  pass "$count users, the same ids, emails and roles as live"
}

clean_up() {
  if ((keep)); then
    skip "kept $drill_db and $drill_files; drop them with: ${compose[*]} exec postgres dropdb" \
      "-U $(postgres_env POSTGRES_USER) $drill_db && rm -rf $drill_files"
  fi
  sql postgres "DROP DATABASE IF EXISTS \"$drill_db\" WITH (FORCE)"
  rm -rf -- "$drill_files"
  pass "dropped $drill_db and removed its files"
}

say "Restore drill $drill_db: database $live_db, files $data_dir"
start="$(now_ms)"
rc=0
backup_dir="$(bash scripts/backup.sh)" || rc=$?
ms="$(($(now_ms) - start))"
case $rc in
  0) record PASS backup "$ms" "$(basename "$backup_dir"), $(human "$(du -sb "$backup_dir" | cut -f1)")" ;;
  2) record FAIL backup "$ms" "$(basename "$backup_dir") made, but its restic copy failed" ;;
  *) record FAIL backup "$ms" "scripts/backup.sh failed (exit $rc, see above)" && backup_dir="" ;;
esac

if [[ -n $backup_dir ]]; then
  start="$(now_ms)"
  if bash scripts/restore.sh "$backup_dir" --into "$drill_db" --files-into "$drill_files"; then
    record PASS restore "$(($(now_ms) - start))" "into $drill_db and scratch/$drill_db"
    restore_ok=1
  else
    record FAIL restore "$(($(now_ms) - start))" "scripts/restore.sh failed (see above)"
  fi
fi

if ((restore_ok)); then
  run_check "alembic head" check_alembic_head
  run_check "alembic current" check_alembic_current
  run_check "row counts" check_row_counts
  run_check "foreign keys" check_foreign_keys
  run_check "files" check_files
  run_check "pdf sample" check_pdf_sample
  run_check "auth users" check_users
fi
run_check "clean up" clean_up
cleaned=1

paint() {  # colours only on a terminal, so logs and cron mail stay plain
  local colour
  case "$1" in PASS) colour=32 ;; FAIL) colour=31 ;; *) colour=33 ;; esac
  if [[ -t 1 ]]; then printf '\033[%sm%s\033[0m' "$colour" "$1"; else printf '%s' "$1"; fi
}
failed=0 passed=0 skipped=0
printf '\nRestore drill %s (backup %s)\n' "$drill_db" "$(basename "${backup_dir:-none}")"
for entry in "${results[@]}"; do
  IFS=$'\t' read -r status label ms detail <<<"$entry"
  case "$status" in PASS) passed=$((passed + 1)) ;; FAIL) failed=$((failed + 1)) ;; *) skipped=$((skipped + 1)) ;; esac
  printf '  %s  %-15s %7s  %s\n' "$(paint "$status")" "$label" "$(secs "$ms")" "$detail"
done
overall=PASS
((failed == 0)) || overall=FAIL
printf '%s  %d passed, %d failed, %d skipped in %s\n' "$(paint "$overall")" "$passed" "$failed" \
  "$skipped" "$(secs "$(($(now_ms) - drill_started))")"
((failed == 0))
