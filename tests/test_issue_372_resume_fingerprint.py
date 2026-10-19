"""Regression tests for resume bound to the effective generation settings (issue #372).

Upstream multimodal #287: the resume fingerprint covered prompt, model and generation
options, so changing an option could not silently reuse an answer produced under
different settings. AI26 keys durable identity on Collection's ``handoff_key``, which is
stable for an immutable source revision — necessary, and not sufficient. ``has_result``
returned True for any stored row, so a run with a different model, prompt version,
``num_ctx`` or ``num_predict`` reported every record as an already-completed duplicate and
never re-analysed it. The port binds the stored result to a fingerprint of the *effective*
settings.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from laclaugpt_data_analysis.distributed_worker import ai26_generation_fingerprint
from laclaugpt_data_analysis.llm.base import (
    DEFAULT_OPTIONS,
    effective_generation_settings,
    generation_fingerprint,
)
from laclaugpt_data_analysis.task_queue import (
    InMemoryTaskStore,
    SqliteTaskStore,
    TaskEnvelope,
    TaskWorker,
    result_matches_fingerprint,
    result_supersedes_fingerprint,
)


def _task(key: str = "handoff-1") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=f"analysis:{key}",
        idempotency_key=key,
        project_id="ai26",
        run_id="ai26-run",
        task_type="analyze-record",
        record_ref="https://example.invalid/issue-372/1",
        schema_version="1.0",
        config_revision="config-sha",
        codebook_revision="codebook-sha",
    )


# --------------------------------------------------------------------------------------
# The fingerprint itself
# --------------------------------------------------------------------------------------


def test_the_fingerprint_covers_the_effective_options_not_just_the_arguments() -> None:
    base = generation_fingerprint(model="gemma4:12b")
    assert base == generation_fingerprint(model="gemma4:12b", options={})
    assert base != generation_fingerprint(model="gemma4:12b", options={"temperature": 0.7})
    assert base != generation_fingerprint(model="gemma4:12b", mode="cloud")
    assert base != generation_fingerprint(model="gemma4:13b")
    assert base != generation_fingerprint(model="gemma4:12b", prompt_version="v2")


def test_defaults_are_part_of_the_fingerprint(monkeypatch) -> None:
    """A changed default changes every answer, so it must change the identity too."""
    before = generation_fingerprint(model="gemma4:12b")
    monkeypatch.setitem(DEFAULT_OPTIONS, "temperature", 0.1)
    assert generation_fingerprint(model="gemma4:12b") != before


def test_option_order_does_not_change_the_fingerprint() -> None:
    first = generation_fingerprint(model="m", options={"temperature": 0, "top_p": 0.9})
    second = generation_fingerprint(model="m", options={"top_p": 0.9, "temperature": 0})
    assert first == second


def test_the_recorded_settings_name_the_effective_values() -> None:
    settings = effective_generation_settings(model="m", options={"num_ctx": 4096})
    assert settings["model"] == "m"
    assert settings["options"]["num_ctx"] == "4096"
    assert settings["options"]["temperature"] == str(DEFAULT_OPTIONS["temperature"])


def test_the_ai26_fingerprint_follows_the_structured_budget_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "local")
    before = ai26_generation_fingerprint()
    assert before == ai26_generation_fingerprint()  # stable within one configuration
    monkeypatch.setenv("LACLAUGPT_STRUCTURED_NUM_PREDICT", "8192")
    assert ai26_generation_fingerprint() != before


# --------------------------------------------------------------------------------------
# Store semantics
# --------------------------------------------------------------------------------------


def test_a_legacy_row_without_a_fingerprint_still_matches() -> None:
    """Deploying the guard must not trigger a mass re-analysis of an existing corpus."""
    assert result_matches_fingerprint({}, "abc") is True
    assert result_supersedes_fingerprint({}, "abc") is False


def test_a_recorded_mismatch_is_a_cache_miss_and_supersedes() -> None:
    stored = {"generation_fingerprint": "old"}
    assert result_matches_fingerprint(stored, "new") is False
    assert result_supersedes_fingerprint(stored, "new") is True
    assert result_supersedes_fingerprint(stored, "old") is False
    assert result_matches_fingerprint(stored, "old") is True


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_a_changed_fingerprint_replaces_the_stored_result(tmp_path, store_kind: str) -> None:
    store = (
        InMemoryTaskStore()
        if store_kind == "memory"
        else SqliteTaskStore(tmp_path / "tasks.sqlite")
    )
    task = _task()

    assert store.write_result(task, {"v": 1}, {}, fingerprint="fp-old") is True
    assert store.has_result(task.idempotency_key, "fp-old") is True
    assert store.has_result(task.idempotency_key, "fp-new") is False
    assert store.has_result(task.idempotency_key) is True  # legacy call: presence only

    assert store.write_result(task, {"v": 2}, {}, fingerprint="fp-new") is True
    assert store.has_result(task.idempotency_key, "fp-new") is True
    assert store.has_result(task.idempotency_key, "fp-old") is False
    # Writing the same answer again is a duplicate, not a silent overwrite.
    assert store.write_result(task, {"v": 3}, {}, fingerprint="fp-new") is False


def test_sqlite_upgrades_an_existing_table_in_place(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE task_results (idempotency_key TEXT PRIMARY KEY, source_url TEXT, "
            "result_json TEXT NOT NULL, provenance_json TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO task_results VALUES (?, ?, ?, ?, ?)",
            ("handoff-1", "https://example.invalid/1", "{}", "{}", 0.0),
        )

    store = SqliteTaskStore(path)
    # The pre-existing row has no fingerprint and keeps resuming, which is the documented
    # compatibility rule rather than a silent loss of the guard for new rows.
    assert store.has_result("handoff-1", "fp-new") is True
    assert store.write_result(_task(), {"v": 1}, {}, fingerprint="fp-new") is False


# --------------------------------------------------------------------------------------
# Worker behaviour
# --------------------------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.calls = 0

    def handler(self, task: TaskEnvelope) -> dict:
        self.calls += 1
        return {"source_url": task.record_ref}


def _worker(store, handler, fingerprint: str) -> TaskWorker:
    return TaskWorker(
        queue=SimpleNamespace(),
        durable_store=store,
        handler=handler,
        worker_id="test-worker",
        provenance={},
        generation_fingerprint=fingerprint,
    )


def test_the_worker_reanalyses_when_the_settings_changed_and_says_so() -> None:
    store = InMemoryTaskStore()
    task = _task()
    store.write_result(task, {"v": "old"}, {}, fingerprint="fp-old")

    handler = _Clock()
    worker = _worker(store, handler.handler, "fp-new")

    assert worker.has_current_result(task) is False
    assert worker.last_resume_invalidated == 1
    assert handler.calls == 0


def test_the_worker_still_treats_a_matching_fingerprint_as_a_duplicate() -> None:
    store = InMemoryTaskStore()
    task = _task()
    store.write_result(task, {"v": "same"}, {}, fingerprint="fp-same")

    worker = _worker(store, _Clock().handler, "fp-same")

    assert worker.has_current_result(task) is True
    assert worker.last_resume_invalidated == 0


def test_without_a_fingerprint_the_historical_presence_check_is_unchanged() -> None:
    store = InMemoryTaskStore()
    task = _task()
    store.write_result(task, {"v": "any"}, {})

    worker = _worker(store, _Clock().handler, "")

    assert worker.has_current_result(task) is True
    assert worker.last_resume_invalidated == 0
