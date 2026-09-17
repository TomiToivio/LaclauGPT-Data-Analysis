from pathlib import Path

from laclaugpt_data_analysis.coordination import (
    ConfigRevision,
    FileConfigStore,
    InMemoryMessageBus,
    MessageEnvelope,
)
from laclaugpt_data_analysis.distributed import ProjectNamespace
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, TaskEnvelope


def test_file_config_store_preserves_immutable_history(tmp_path: Path) -> None:
    store = FileConfigStore(tmp_path, project_id="ai26")
    revision = ConfigRevision.build(
        project_id="ai26",
        module="analysis",
        payload={"model": "gemma4:12b", "temperature": 0},
        publisher="test",
    )

    assert store.publish(revision) == revision.revision
    assert store.current("analysis") == revision
    assert store.get("analysis", revision.revision) == revision


def test_config_revision_rejects_tampered_payload() -> None:
    revision = ConfigRevision.build(
        project_id="ai26",
        module="analysis",
        payload={"model": "gemma4:12b"},
        publisher="test",
    )
    tampered = ConfigRevision(
        project_id=revision.project_id,
        module=revision.module,
        revision=revision.revision,
        payload={"model": "different"},
        created_at=revision.created_at,
        publisher=revision.publisher,
    )

    try:
        tampered.validate()
    except ValueError as exc:
        assert "hash" in str(exc)
    else:
        raise AssertionError("tampered config revision should fail validation")


def test_in_memory_message_bus_requires_reference_for_research_payloads() -> None:
    bus = InMemoryMessageBus()
    request = MessageEnvelope(
        message_id="request-1",
        project_id="ai26",
        sender="analysis",
        recipient="visualization",
        kind="refresh",
        correlation_id="corr-1",
        config_revision="cfg-123",
        body={"record_ref": "record-1"},
    )
    message_id = bus.publish(request)
    received_id, received = bus.receive()
    assert received_id == message_id
    assert received.correlation_id == request.correlation_id
    assert received.config_revision == "cfg-123"
    bus.ack(received_id)
    assert bus.pending == {}


def test_in_memory_queue_prevents_simultaneous_double_claim() -> None:
    queue = InMemoryTaskQueue()
    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="ai26:record-1:stage-1:v1",
        project_id="ai26",
        run_id="run-1",
        task_type="analyze-record",
        record_ref="record-1",
        schema_version="1.0",
        config_revision="cfg",
        codebook_revision="codebook",
    )
    queue.publish(task)
    first = queue.claim()
    second = queue.claim()
    assert first is not None
    assert second is None
    assert queue.reclaim(min_idle_ms=0) == first


def test_namespace_exposes_cross_module_settings_and_lock_keys() -> None:
    namespace = ProjectNamespace("ai26")
    assert namespace.settings_key("analysis", "abc") == "laclaugpt:ai26:settings:analysis:abc"
    assert namespace.settings_key("storage", "current") == "laclaugpt:ai26:settings:storage:current"
    assert namespace.worker_key("simulation", "worker-1") == "laclaugpt:ai26:worker:simulation:worker-1"
    assert namespace.lock_key("analysis:record-1") == "laclaugpt:ai26:lock:analysis:record-1"
