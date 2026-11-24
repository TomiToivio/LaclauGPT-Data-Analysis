"""SQLite-backed durable task result and failure history.

SQLite is the zero-infrastructure durable option: one file, no server, and the
same duplicate/fingerprint semantics as the Mongo store. The schema is created
and migrated in place on construction, so an existing local run directory keeps
working after an upgrade; the added columns are backwards compatible.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from .models import (
    TaskEnvelope,
    bounded_failure_diagnostics,
    result_matches_fingerprint,
    result_supersedes_fingerprint,
)


class SqliteTaskStore:
    """Durable local task result/failure history for direct and offline operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_results ("
                "idempotency_key TEXT PRIMARY KEY, source_url TEXT, result_json TEXT NOT NULL, "
                "provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            result_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_results)")
            }
            if "source_url" not in result_columns:
                connection.execute("ALTER TABLE task_results ADD COLUMN source_url TEXT")
            if "generation_fingerprint" not in result_columns:
                connection.execute(
                    "ALTER TABLE task_results ADD COLUMN generation_fingerprint TEXT"
                )

            connection.execute(
                "CREATE TABLE IF NOT EXISTS task_failures ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, "
                "idempotency_key TEXT NOT NULL, source_url TEXT, attempt INTEGER NOT NULL, "
                "error TEXT NOT NULL, provenance_json TEXT NOT NULL, response_raw TEXT, "
                "response_raw_chars INTEGER, response_raw_truncated INTEGER, finish_reason TEXT, "
                "diagnostic_only INTEGER, terminal INTEGER NOT NULL DEFAULT 0, "
                "terminal_reason TEXT, output_budget_tokens INTEGER, "
                "required_output_tokens_lower_bound INTEGER, generated_output_chars INTEGER, "
                "rearmed_at REAL, created_at REAL NOT NULL)"
            )
            failure_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(task_failures)")
            }
            if "source_url" not in failure_columns:
                connection.execute("ALTER TABLE task_failures ADD COLUMN source_url TEXT")
            for column, declaration in {
                "response_raw": "TEXT",
                "response_raw_chars": "INTEGER",
                "response_raw_truncated": "INTEGER",
                "finish_reason": "TEXT",
                "diagnostic_only": "INTEGER",
                "terminal": "INTEGER NOT NULL DEFAULT 0",
                "terminal_reason": "TEXT",
                "output_budget_tokens": "INTEGER",
                "required_output_tokens_lower_bound": "INTEGER",
                "generated_output_chars": "INTEGER",
                "rearmed_at": "REAL",
            }.items():
                if column not in failure_columns:
                    connection.execute(
                        f"ALTER TABLE task_failures ADD COLUMN {column} {declaration}"
                    )

    def has_result(self, idempotency_key: str, fingerprint: str = "") -> bool:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT generation_fingerprint FROM task_results WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return False
        return result_matches_fingerprint({"generation_fingerprint": row[0] or ""}, fingerprint)

    def has_terminal_failure(self, idempotency_key: str) -> bool:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT 1 FROM task_failures "
                "WHERE idempotency_key = ? AND terminal = 1 AND rearmed_at IS NULL LIMIT 1",
                (idempotency_key,),
            ).fetchone()
        return row is not None

    def has_recent_capacity_failure(
        self, idempotency_key: str, *, within_seconds: float
    ) -> bool:
        if within_seconds <= 0:
            return False
        cutoff = time.time() - within_seconds
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT 1 FROM task_failures WHERE idempotency_key = ? "
                "AND error LIKE '%no GPU capacity%' AND created_at >= ? LIMIT 1",
                (idempotency_key, cutoff),
            ).fetchone()
        return row is not None

    def rearm_terminal_failure(self, idempotency_key: str) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE task_failures SET rearmed_at = ? "
                "WHERE idempotency_key = ? AND terminal = 1 AND rearmed_at IS NULL",
                (time.time(), idempotency_key),
            )
            return int(cursor.rowcount)

    def rearm_terminal_failure_if_budget_increased(
        self, idempotency_key: str, current_ceiling: int
    ) -> int:
        if current_ceiling < 1:
            return 0
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE task_failures SET rearmed_at = ? "
                "WHERE idempotency_key = ? AND terminal = 1 AND rearmed_at IS NULL "
                "AND terminal_reason = ? AND output_budget_tokens IS NOT NULL "
                "AND output_budget_tokens < ?",
                (
                    time.time(),
                    idempotency_key,
                    "unanalysable_within_budget",
                    current_ceiling,
                ),
            )
            return int(cursor.rowcount)

    def failure_summary(self) -> dict[str, int]:
        with sqlite3.connect(self.path) as connection:
            events = int(connection.execute("SELECT COUNT(*) FROM task_failures").fetchone()[0])
            distinct = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT idempotency_key) FROM task_failures"
                ).fetchone()[0]
            )
            terminal = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT idempotency_key) FROM task_failures "
                    "WHERE terminal = 1 AND rearmed_at IS NULL"
                ).fetchone()[0]
            )
        return {"events": events, "distinct": distinct, "terminal": terminal}

    def write_result(
        self,
        task: TaskEnvelope,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        fingerprint: str = "",
    ) -> bool:
        payload = (
            task.record_ref,
            json.dumps(dict(result), ensure_ascii=False, default=str),
            json.dumps(dict(provenance), ensure_ascii=False, default=str),
            time.time(),
            fingerprint,
        )
        with sqlite3.connect(self.path) as connection:
            existing = connection.execute(
                "SELECT generation_fingerprint FROM task_results WHERE idempotency_key = ?",
                (task.idempotency_key,),
            ).fetchone()
            stored = None if existing is None else {"generation_fingerprint": existing[0] or ""}
            if not result_supersedes_fingerprint(stored, fingerprint):
                return False
            if stored is None:
                try:
                    connection.execute(
                        "INSERT INTO task_results (source_url, result_json, provenance_json, "
                        "created_at, generation_fingerprint, idempotency_key) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (*payload, task.idempotency_key),
                    )
                except sqlite3.IntegrityError:
                    # Another writer won the same source; that is a duplicate, not an error.
                    return False
            else:
                # Same source, provably different generation settings: the old answer is
                # replaced rather than kept next to an answer it does not describe.
                connection.execute(
                    "UPDATE task_results SET source_url = ?, result_json = ?, "
                    "provenance_json = ?, created_at = ?, generation_fingerprint = ? "
                    "WHERE idempotency_key = ?",
                    (*payload, task.idempotency_key),
                )
        return True

    def write_failure(
        self,
        task: TaskEnvelope,
        error: str,
        provenance: Mapping[str, Any],
        diagnostics: Mapping[str, Any] | None = None,
        *,
        terminal: bool = False,
    ) -> None:
        diagnostic = bounded_failure_diagnostics(diagnostics)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO task_failures "
                "(task_id, idempotency_key, source_url, attempt, error, provenance_json, "
                "response_raw, response_raw_chars, response_raw_truncated, finish_reason, "
                "diagnostic_only, terminal, terminal_reason, output_budget_tokens, "
                "required_output_tokens_lower_bound, generated_output_chars, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.task_id,
                    task.idempotency_key,
                    task.record_ref,
                    task.attempt,
                    error,
                    json.dumps(dict(provenance), ensure_ascii=False, default=str),
                    diagnostic.get("response_raw"),
                    diagnostic.get("response_raw_chars"),
                    int(bool(diagnostic.get("response_raw_truncated"))) if diagnostic else None,
                    diagnostic.get("finish_reason"),
                    int(bool(diagnostic.get("diagnostic_only"))) if diagnostic else None,
                    int(terminal),
                    diagnostic.get("terminal_reason"),
                    diagnostic.get("output_budget_tokens"),
                    diagnostic.get("required_output_tokens_lower_bound"),
                    diagnostic.get("generated_output_chars"),
                    time.time(),
                ),
            )
