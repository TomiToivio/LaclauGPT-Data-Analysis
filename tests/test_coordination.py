from pathlib import Path

from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.coordination import (
    ConfigRevision,
    FileConfigStore,
    InMemoryMessageBus,
    MessageEnvelope,
    config_store_from_settings,
)
from laclaugpt_data_analysis.distributed import ProjectNamespace
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, TaskEnvelope


def test_redis_disabled_uses_durable_local_config_store(tmp_path: Path) -> None:
    settings = Settings(project_id="ai26", data_dir=tmp_path, redis_url=None)
    store = config_store_from_settings(settings)
    revision = ConfigRevision.build(
        project_id="ai26",
        module="analysis",
        payload={"plugins": ["laclau"], "model": "gemma4:12b"},
        publisher="test",
    )
    store.publish(revision)
    loaded = store.current("analysis")
    assert loaded is not None
    assert loaded.revision == revision.revision
    assert loaded.payload["model"] == "gemma4:12b"


def test_config_revision_is_content_addressed_and_immutable(tmp_path: Path) -> None:
    store = FileConfigStore(tmp_path, project_id="ai26")
    first = ConfigRevision.build(
        project_id="ai26", module="analysis", payload={"rag_top_k": 20}, publisher="ui"
    )
    second = ConfigRevision.build(
        project_id="ai26", module="analysis", payload={"rag_top_k": 30}, publisher="ui"
    )
    assert first.revision != second.revision
    store.publish(first)
    store.publish(second)
    assert store.current("analysis").revision == second.revision
    assert store.get("analysis", first.revision).payload == {"rag_top_k": 20}


def test_message_round_trip_preserves_correlation_and_config_revision() -> None:
    bus = InMemoryMessageBus()
    request = MessageEnvelope.build(
        project_id="ai26",
        run_id="run-1",
        sender="visualization",
        recipient="rag",
        message_type="rag.query",
        config_revision="cfg-123",
        source_record_id="record-7",
        payload_ref="mongodb://ai26/record-7",
        body={"question": "What articulations surround AI?"},
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
    first = queue.claim(block_ms=0)
    second = queue.claim(block_ms=0)
    assert first is not None
    assert second is None
    assert queue.reclaim(min_idle_ms=0) == first


def test_namespace_exposes_cross_module_settings_and_lock_keys() -> None:
    namespace = ProjectNamespace("ai26")
    assert namespace.settings_key("analysis", "abc") == "laclaugpt:ai26:settings:analysis:abc"
    assert namespace.settings_key("storage", "current") == "laclaugpt:ai26:settings:storage:current"
    assert namespace.worker_key("simulation", "worker-1") == "laclaugpt:ai26:worker:simulation:worker-1"
    assert namespace.lock_key("analysis:record-1") == "laclaugpt:ai26:lock:analysis:record-1"
