# Runbook: backups and restores

Phase 2's exit criteria (docs/PLAN.md) include off-box backups and a restore drill. This runbook
says what is backed up, how to restore after a disaster, how the monthly drill works, and what
the production server adds. The storage decisions are in
[ADR 0005](../adr/0005-storage-postgres-filesystem.md).

## Commands

| Command | What it does |
|---|---|
| `make backup` | Backs up now and prints the backup's directory. Exit 0: done. 1: no backup. 2: local backup made, restic copy failed. |
| `make restore backup=<dir> [into=<db>] [files=<dir>]` | Checks every sha256, then restores into a **new** database (default `arp_restore_<UTC time>`) and a new directory (default `ARP_BACKUP_DIR/scratch/<db>`). Prints how to drop them. |
| `bash scripts/restore.sh <dir> --into arp --yes-replace-live` | Replaces the live database and files (services stopped). There is no `make` shortcut for this on purpose. |
| `make restore-drill [keep=1]` | The drill: a fresh backup, a scratch restore, the checks, the clean-up. `keep=1` keeps the scratch copies. |
| `restic snapshots --tag arp` | Lists the off-box backups. |
| `restic restore <snapshot> --target <dir>` | Fetches one. The backup is then at `<dir>/<its original path>/arp-<UTC time>`. |

Settings come from the environment first, then from the repo's `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `ARP_DATA_DIR` | `~/.local/share/arp` | The files to back up (the services' setting). |
| `ARP_BACKUP_DIR` | `~/.local/share/arp/backups` | Where backups and scratch restores go. Left out of the files backup. |
| `ARP_BACKUP_KEEP` | `7` | Local backups kept; older ones are deleted after each backup. |
| `ARP_BACKUP_DATABASE` | the container's `POSTGRES_DB` (`arp`) | The database backed up, protected from restores, and compared in the drill. |
| `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE` | unset | The off-box copy (restic's own variables). Backend credentials such as `AWS_*` come from the environment only. |
| `COMPOSE_FILE`, `COMPOSE_ENV_FILES` | the dev compose files | The server's compose files. |

## What is backed up

`make backup` (`scripts/backup.sh`) writes `ARP_BACKUP_DIR/arp-<UTC time>/`:

| File | Contents |
|---|---|
| `database.dump` | `pg_dump -Fc` of the whole `arp` database: our tables in `public` (with `alembic_version`) and Better Auth's `auth` schema (users, password hashes, sessions). It runs inside the postgres container, so its version always matches the server. |
| `files.tar` | `ARP_DATA_DIR`: the PDFs under `papers/<sha256[:2]>/<sha256>.pdf`, without the backups directory or unfinished writes (`.*.tmp`). Uncompressed: PDFs barely compress, and restic deduplicates an uncompressed tar from one day to the next. |
| `manifest.json` | The time, git commit, Postgres version and locale, the Alembic head, every table's exact row count, the files' count and bytes, and each file's size and sha256. |

- **One moment.** The dump and the manifest's numbers come from one snapshot: a REPEATABLE READ
  transaction stays open while `pg_dump --snapshot` reuses it. The files are archived after the
  dump. The worker writes a PDF before the row that names it, so every file the dump refers to is
  in the archive.
- **Complete or absent.** A backup is written under a hidden `.arp-<time>.partial` name and
  renamed when it is whole. A lock keeps two backups (or a backup and a restore) apart.
- **Private.** Backups are owner-only (0700/0600) because they hold password hashes and session
  tokens. Don't copy them anywhere unencrypted. restic and pgBackRest encrypt their copies.
- **Off-box.** With `RESTIC_REPOSITORY` set, each backup also goes to restic. If restic is not
  installed, the script says so and the local backup still succeeds. If restic fails, the exit
  code is 2 and the local backup is kept. The script only adds snapshots, so the server's
  credentials can be append-only (see the production plan).

**Not backed up:**
- **Temporal's state.** The dev server keeps it in SQLite under `.data/temporal`, which is not
  backed up. A restore brings back Postgres and the files only. Runs that were active at backup
  time may no longer match Temporal's history, so check them after a restore (step 7 below). In
  production Temporal runs on its own Postgres, which needs its own pgBackRest stanza.
- **Valkey:** rate-limit buckets and SSE wake-ups, never the source of truth (ADR 0005). It comes
  back empty.
- **Secrets:** `.env`, `infra/compose/.env`, the SOPS age key and the backup passwords stay out of
  backups on purpose. See "Encryption keys".
- **Things that can be rebuilt:** images (GHCR), datasets (a read-only copy of NYU2), GROBID,
  Mailpit, Caddy's certificates (issued again on start).

## Restore after a disaster

1. **Stop the services, but not Postgres.** In dev, stop `make api`, `make worker`,
   `make gateway` and `make web`. On the server, stop the app containers. The live restore
   refuses to run while anything is connected to `arp`.
   - **On a new box:** install as in the README, put back `.env` and `infra/compose/.env` (from
     the password manager or SOPS), and run `make up`. Don't migrate: the empty `arp` database is
     replaced anyway.
2. **Pick the backup.**
   - Local backups: `ls ~/.local/share/arp/backups`.
   - Off-box, when the box is gone: run `restic snapshots --tag arp`, then
     `restic restore <snapshot> --target /var/tmp/arp-restore`.
3. **Rehearse (recommended).** `make restore backup=<dir>` restores into a scratch database.
   Look at it, then drop it with the command it prints.
4. **Restore.** Run `bash scripts/restore.sh <dir> --into arp --yes-replace-live` as the user
   that runs the services, so the files get the right owner. The script:
   - checks every artifact's sha256 and stops on any mismatch;
   - restores into `arp_incoming_<time>` in a single transaction;
   - extracts the files over `ARP_DATA_DIR`;
   - in one transaction, renames `arp` to `arp_replaced_<time>` and the restored database to
     `arp`.

   Files written after the backup stay in place, and no restored row refers to them. If anything
   fails before the rename, the incoming database is dropped and `arp` is untouched. Files
   extracted by then are the backup's own copies, under the same names.
5. **Check the schema.** `uv run alembic -c packages/db/alembic.ini current` must print the head
   followed by `(head)`. If the code has newer migrations than the backup, run `make migrate`.
6. **Start the services.** Sign in, open a recent run, and open one of its papers' PDFs.
7. **Check runs in flight.** Runs shown as running or awaiting approval may have lost their
   Temporal workflow. Cancel or retry them.
8. **After a few days**, drop the old database:
   `docker compose -f infra/compose/compose.yaml --env-file infra/compose/.env exec postgres dropdb -U arp arp_replaced_<time>`.

## The monthly drill

Run `make restore-drill` once a month, and after any change to the schema, these scripts or the
storage layout. It takes a fresh backup and restores it into `arp_drill_<UTC time>` and
`ARP_BACKUP_DIR/scratch/arp_drill_<UTC time>`. It then runs these checks:

| Check | Passes when |
|---|---|
| alembic head | The restored `alembic_version` equals the manifest's and the live database's. |
| alembic current | Alembic, through the app's `ARP_DATABASE_URL`, reads the restored database as the code's head. Skipped without `uv` or that URL. |
| row counts | Every table has exactly the manifest's row count. |
| foreign keys | The constraints match live and are validated, and spot checks find no orphans (papers of `run_papers`, stage runs, outputs, approvals, run events, projects, and Better Auth sessions and accounts). |
| files | The restored files' count and bytes equal the manifest's. |
| pdf sample | Up to 50 PDFs hash to their `papers.pdf_sha256`. Skipped when no paper has a file. |
| auth users | The restored users have the same ids, emails and roles as live. |
| clean up | The scratch database and directory are gone (skipped with `keep=1`). |

The drill prints a summary with timings and exits 1 on any failure. The backup it took is kept like
any other. Keep the summary with the date; Phase 2's exit check needs one.
- **On a failure:** don't trust that backup until the cause is fixed. The failing check names
  the problem, and `make restore-drill keep=1` keeps the copies for a look. Until then, the last
  good backup is the one before.
- **False alarms:** "auth users" compares with live a few seconds after the backup. A user
  invited in between shows up as a difference, so run the drill again.
- **Off-box, once a quarter:** restore from restic alone. On another machine with Docker, run
  `make up`, `restic restore`, then `make restore backup=<dir>`. The sha256 check proves the
  off-box copy is whole and restorable. A drill mode that fetches from restic is a follow-up for
  when restic is installed somewhere it can be tested.

## The production plan (the server)

- **Postgres: pgBackRest** (WAL-G as fallback) with continuous WAL archiving to an off-box
  repository (an S3-compatible bucket or SFTP to another host). It can restore to any point in
  time, not only the last nightly dump.
  - Two stanzas, `arp` (the app's cluster) and `temporal` (Temporal's own Postgres), backed up and
    drilled together.
  - A full backup weekly and a differential daily. `repo1-retention-full=4` gives about a month
    of point-in-time recovery.
  - `repo1-cipher-type=aes-256-cbc`: the repository is encrypted before it leaves the server.
  - Drilled monthly by restoring into a scratch Postgres container, alongside `make restore-drill`.
- **Logical dumps stay.** `make backup` runs nightly: its dumps restore on any Postgres major
  version without pgBackRest, and the drill checks them.
- **Files: restic**, nightly through `make backup` with `RESTIC_REPOSITORY` set. The repository is
  append-only for the server (for example `rest-server --append-only`): the server can add
  snapshots but not delete them, so an intruder on the server cannot wipe the off-box copies.
  Retention runs weekly from the backup host, not the server:
  `restic forget --tag arp --group-by host,tags --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune`.
  It groups by tag because every backup is a new path. Run `restic check --read-data-subset=5%`
  weekly too.
- **Schedule:** systemd timers, each alerting on a non-zero exit. The backup runs nightly at
  02:30, and the drill on the first Monday of the month at 04:00.

| Copy | Where | Kept |
|---|---|---|
| Dump + files tar | Server disk, `ARP_BACKUP_DIR` | The newest 7 (`ARP_BACKUP_KEEP`) |
| restic snapshots | Off-box | 7 daily, 5 weekly, 12 monthly |
| pgBackRest `arp` and `temporal` | Off-box | 4 full backups and their WAL (about 4 weeks of point-in-time recovery) |

### Encryption keys

- **On the server:**
  - the restic repository password, in `/etc/arp/backup/restic-password` (mode 0400, owned by
    the user that runs the backups), named by `RESTIC_PASSWORD_FILE`;
  - the off-box storage credentials, in a root-only environment file that the systemd unit
    loads;
  - the pgBackRest cipher pass, in `/etc/pgbackrest/pgbackrest.conf` (mode 0640, `postgres`);
  - the SOPS age key, which decrypts the deployment's secrets.
- **Off the server:** all of these also live in the lab's password manager (two admins have
  access) and on a printed copy sealed with the lab head. A backup whose key died with the server
  cannot be restored.
- **When an admin leaves,** rotate the restic password (`restic key add`, then `restic key remove`)
  and the storage credentials.
