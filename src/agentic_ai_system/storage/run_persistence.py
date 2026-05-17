from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class RunPersistence:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path.cwd() / "outputs" / "flow_runs.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    current_year TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def start_run(self, run_id: str, topic: str, current_year: str) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, topic, current_year, status, started_at, updated_at)
                VALUES (?, ?, ?, 'running', ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  topic = excluded.topic,
                  current_year = excluded.current_year,
                  status = 'running',
                  updated_at = excluded.updated_at
                """,
                (run_id, topic, current_year, now, now),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now, run_id),
            )

    def stage_event(self, run_id: str, stage: str, status: str, message: Optional[str] = None) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stage_events (run_id, stage, status, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, stage, status, message, now),
            )

    def log_approval(self, run_id: str, stage: str, approved: bool) -> None:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (run_id, stage, approved, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, stage, 1 if approved else 0, now),
            )
