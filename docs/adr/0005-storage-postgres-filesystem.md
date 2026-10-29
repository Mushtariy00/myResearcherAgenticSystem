# ADR 0005 — PostgreSQL 18 + Valkey + a filesystem volume (S3 later)

- Status: accepted (2026-10-30)

## Context
The legacy system kept results as JSON files and run logs in SQLite. The deck asks for tables
for users, projects, runs, papers, stage outputs and approvals, plus search across runs. The dev
box has 7.7 GiB of RAM.

## Decision
- **PostgreSQL 18** is the system of record, accessed through SQLAlchemy 2.1 async with Alembic
  migrations from Phase 1. Paper search uses Postgres full-text search (`tsvector`); pgvector
  semantic search is deferred to Phase 5.
- **`run_events`** carry a per-run sequence number assigned in the same transaction as the state
  change. They are the source of truth for SSE replay. The audit log is a separate table.
- **Valkey 9** (BSD) holds rate-limit token buckets and pub/sub wake-ups for SSE. It is never the
  source of truth.
- **Files** (PDFs, parsed text, generated code, checkpoints, logs) live on a filesystem volume
  behind a small storage interface. An S3-compatible backend (SeaweedFS or cloud S3) can replace
  it later without code changes. Files are streamed through the API with `nosniff` and
  `attachment` headers.

## Consequences
- One host means a filesystem volume is enough. Backups use pgBackRest (with WAL-G as fallback)
  for Postgres and restic for files, off-box, with monthly restore drills.

## Alternatives considered
- **MinIO**: the community edition is archived (2026).
- **SeaweedFS from day one**: not needed until there is more than one host.
- **Postgres LISTEN/NOTIFY as the event log**: it doesn't persist and its payloads are small.
  It is fine only as a wake-up signal.
