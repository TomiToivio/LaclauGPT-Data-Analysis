from __future__ import annotations

import sqlite3

from laclaugpt_data_analysis.task_queue import SqliteTaskStore, TaskEnvelope


def _task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="analysis:demo",
        idempotency_key="demo",
        project_id="ai26",
        run_id="run-1",
        task_type="analyze-record",
        record_ref="https://example.org/source/1",
        schema_version="1.0",
        config_revision="cfg",
        codebook_revision="cb",
    )


def test_sqlite_result_persists_source_url(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(path)
    task = _task()

    assert store.write_result(task, {"source_url": task.record_ref}, {"worker": "test"})

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT source_url, result_json FROM task_results WHERE idempotency_key = ?",
            (task.idempotency_key,),
        ).fetchone()

    assert row is not None
    assert row[0] == task.record_ref
    assert task.record_ref in row[1]


def test_sqlite_failure_persists_source_url(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = SqliteTaskStore(path)
    task = _task()

    store.write_failure(task, "boom", {"worker": "test"})

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT source_url, error FROM task_failures WHERE idempotency_key = ?",
            (task.idempotency_key,),
        ).fetchone()

    assert row == (task.record_ref, "boom")


def test_sqlite_migrates_existing_tables_without_source_url(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE task_results ("
            "idempotency_key TEXT PRIMARY KEY, result_json TEXT NOT NULL, "
            "provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE task_failures ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, "
            "idempotency_key TEXT NOT NULL, attempt INTEGER NOT NULL, "
            "error TEXT NOT NULL, provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
        )

    SqliteTaskStore(path)

    with sqlite3.connect(path) as connection:
        result_columns = {row[1] for row in connection.execute("PRAGMA table_info(task_results)")}
        failure_columns = {row[1] for row in connection.execute("PRAGMA table_info(task_failures)")}

    assert "source_url" in result_columns
    assert "source_url" in failure_columns
