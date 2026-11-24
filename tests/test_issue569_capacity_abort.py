"""Issue #569: a model-capacity outage must stop the cycle, not eat the ceiling."""
from __future__ import annotations

from pathlib import Path

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.distributed_worker import (
    CAPACITY_FAILURE_ABORT_AFTER,
    PROVIDER_UNAVAILABLE_EXIT_CODE,
    SEED_PROVIDER_DEFERRED,
    AI26TaskWorker,
    _cycle_exit_code,
    _run_bounded_cycle,
    capacity_cooldown_seconds,
    is_capacity_unavailable,
    seed_disposition,
)
from laclaugpt_data_analysis.llm.base import TransientProviderError
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


def _task(name: str = "capacity-1", attempt: int = 1) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=name,
        idempotency_key=name,
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref=f"https://example.invalid/{name}",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
        attempt=attempt,
    )


def test_only_the_ollama_capacity_response_is_a_capacity_outage():
    assert is_capacity_unavailable(
        TransientProviderError(
            "Ollama call failed: scheduler: no GPU capacity for gemma4:12b within 900s "
            "(status code: 503)"
        )
    )
    assert not is_capacity_unavailable(TransientProviderError("Ollama call failed: HTTP 503"))
    assert not is_capacity_unavailable(RuntimeError("no GPU capacity"))


def test_two_capacity_failures_stop_the_cycle_without_spending_attempts():
    queue, store = InMemoryTaskQueue(), InMemoryTaskStore()
    for index in range(3):
        queue.publish(_task(f"capacity-{index}"))

    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(
            TransientProviderError(
                "Ollama call failed: scheduler: no GPU capacity for gemma4:12b within 900s "
                "(status code: 503)"
            )
        ),
        worker_id="test",
        provenance={},
        max_attempts=3,
    )

    counts, failure_classes = _run_bounded_cycle(
        worker, max_tasks=5, reclaim_idle_ms=None, seeded=1
    )

    assert CAPACITY_FAILURE_ABORT_AFTER == 2
    assert counts["claims"] == 2, "the cycle must stop after the configured capacity failures"
    assert counts["provider_unavailable"] == 1
    assert counts["retry"] == 2
    assert counts["completed"] == 0
    assert counts["dead-letter"] == 0
    assert failure_classes == {"TransientProviderError": 2}
    assert _cycle_exit_code(counts) == PROVIDER_UNAVAILABLE_EXIT_CODE == 5
    assert queue.dead_letters == []
    assert [item.task.idempotency_key for item in queue.pending] == ["capacity-2"], (
        "the cycle must stop before the third task; the untouched task waits for the next cycle"
    )
    assert all(item.task.attempt == 1 for item in queue.pending)
    assert store.failures[-1]["provider_condition"] == "no_gpu_capacity"
    assert store.failures[-1]["infrastructure"] is True


def test_recent_capacity_failure_is_deferred_by_the_seed_cooldown(monkeypatch):
    store = InMemoryTaskStore()
    task = _task("deferred-1")
    store.write_failure(
        task,
        "TransientProviderError: scheduler: no GPU capacity",
        {},
        diagnostics={"provider_condition": "no_gpu_capacity", "infrastructure": True},
    )
    assert store.has_recent_capacity_failure("deferred-1", within_seconds=60) is True
    assert store.has_recent_capacity_failure("deferred-1", within_seconds=0) is False
    assert store.has_recent_capacity_failure("other", within_seconds=60) is False
    assert seed_disposition({"limit": 3, "examined": 1, "provider_deferred": 1}) == SEED_PROVIDER_DEFERRED
    monkeypatch.setenv("LACLAUGPT_AI26_CAPACITY_COOLDOWN_SECONDS", "not-a-number")
    assert capacity_cooldown_seconds() == 1800.0


def test_the_wrapper_names_the_capacity_outage_and_documents_exit_five():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    docs = (root / "docs" / "AI26_LASKIN_ANALYSIS.md").read_text(encoding="utf-8")
    assert "PROVIDER CAPACITY UNAVAILABLE" in script
    assert '"$WORKER_STATUS" -eq 5' in script
    assert "\n5   provider capacity unavailable" in docs
    assert "#569" in script
