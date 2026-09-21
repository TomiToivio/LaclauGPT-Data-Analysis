import hashlib
import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.distributed_worker import (
    AI26_MODEL,
    AI26TaskWorker,
    FrozenRunManifest,
    WorkerBinding,
    collection_records_name,
    enforce_local_model,
    seed_ready_tasks,
)
from laclaugpt_data_analysis.task_queue import InMemoryTaskQueue, InMemoryTaskStore, TaskEnvelope


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_binding(tmp_path: Path, *, public_git_sha: str = "abc123") -> WorkerBinding:
    private = tmp_path / "private"
    private.mkdir()
    config = private / "ai26.json"
    codebook = private / "codebook.json"
    config.write_text('{"arena":"elites"}', encoding="utf-8")
    codebook.write_text(
        '{"codebook_id":"ai26-test","version":"1","title":"Synthetic","entries":[]}',
        encoding="utf-8",
    )
    manifest = private / "run.json"
    manifest.write_text(
        json.dumps(
            {
                "project_id": "ai26",
                "run_id": "run-001",
                "schema_version": SCHEMA_VERSION,
                "config_sha256": sha(config),
                "codebook_sha256": sha(codebook),
                "model": AI26_MODEL,
                "public_git_sha": public_git_sha,
            }
        ),
        encoding="utf-8",
    )
    return WorkerBinding.build(
        manifest_path=manifest,
        private_root=private,
        private_config=config,
        codebook=codebook,
        worker_id="worker-1",
    )


def test_private_runtime_files_must_be_inside_private_root(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    codebook = private / "codebook.json"
    codebook.write_text("{}", encoding="utf-8")
    manifest = private / "run.json"
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="inside"):
        WorkerBinding.build(
            manifest_path=manifest,
            private_root=private,
            private_config=outside,
            codebook=codebook,
        )


def test_run_manifest_must_also_be_inside_private_root(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    config = private / "ai26.json"
    codebook = private / "codebook.json"
    outside_manifest = tmp_path / "run.json"
    config.write_text("{}", encoding="utf-8")
    codebook.write_text("{}", encoding="utf-8")
    outside_manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="inside"):
        WorkerBinding.build(
            manifest_path=outside_manifest,
            private_root=private,
            private_config=config,
            codebook=codebook,
        )


def test_manifest_hashes_and_schema_are_frozen(tmp_path: Path) -> None:
    binding = make_binding(tmp_path)
    binding.private_config.write_text('{"arena":"changed"}', encoding="utf-8")

    with pytest.raises(ValueError, match="config hash"):
        binding.validate_files()


def test_runtime_git_sha_must_match_frozen_manifest(tmp_path: Path, monkeypatch) -> None:
    binding = make_binding(tmp_path, public_git_sha="frozen-sha")
    monkeypatch.setenv("LACLAUGPT_PUBLIC_GIT_SHA", "different-sha")

    with pytest.raises(ValueError, match="public Git SHA"):
        binding.validate_runtime_code()


def test_runtime_git_sha_accepts_explicit_matching_revision(tmp_path: Path, monkeypatch) -> None:
    binding = make_binding(tmp_path, public_git_sha="frozen-sha")
    monkeypatch.setenv("LACLAUGPT_PUBLIC_GIT_SHA", "frozen-sha")
    binding.validate_runtime_code()


def test_task_revisions_must_match_frozen_manifest(tmp_path: Path) -> None:
    binding = make_binding(tmp_path)
    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="id-1",
        project_id="ai26",
        run_id="wrong-run",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/1",
        schema_version=SCHEMA_VERSION,
        config_revision=binding.manifest.config_sha256,
        codebook_revision=binding.manifest.codebook_sha256,
    )

    with pytest.raises(ValueError, match="run_id"):
        binding.validate_task(task)


def test_collection_ready_handoff_becomes_reference_only_analysis_task(tmp_path: Path) -> None:
    binding = make_binding(tmp_path)
    task = binding.task_from_handoff(
        {
            "status": "ready",
            "handoff_key": "handoff-123",
            "run_id": "run-001",
            "source_url": "https://example.invalid/source/1",
        }
    )
    assert task.idempotency_key == "handoff-123"
    assert task.record_ref == "https://example.invalid/source/1"
    assert task.config_revision == binding.manifest.config_sha256
    assert task.codebook_revision == binding.manifest.codebook_sha256
    assert "payload" not in task.to_dict()


def test_collection_mongo_contract_uses_records_collection() -> None:
    settings = Settings(project_id="ai26")
    assert collection_records_name(settings) == "ai26__records"


def test_wrong_collection_handoff_run_is_rejected(tmp_path: Path) -> None:
    binding = make_binding(tmp_path)
    with pytest.raises(ValueError, match="handoff run"):
        binding.task_from_handoff(
            {
                "status": "ready",
                "handoff_key": "handoff-123",
                "run_id": "other-run",
                "source_url": "https://example.invalid/source/1",
            }
        )


def test_provenance_contains_worker_run_model_and_hashes(tmp_path: Path) -> None:
    provenance = make_binding(tmp_path).provenance()
    assert provenance["run_id"] == "run-001"
    assert provenance["worker_id"] == "worker-1"
    assert provenance["model"] == AI26_MODEL
    assert provenance["schema_version"] == SCHEMA_VERSION
    assert provenance["config_sha256"]
    assert provenance["codebook_sha256"]


def test_ai26_worker_forces_local_model_and_no_cloud(monkeypatch) -> None:
    manifest = FrozenRunManifest(
        project_id="ai26",
        run_id="run-001",
        schema_version=SCHEMA_VERSION,
        config_sha256="a",
        codebook_sha256="b",
        model=AI26_MODEL,
        public_git_sha="abc",
    )
    monkeypatch.delenv("LLM_MODE", raising=False)
    monkeypatch.delenv("LLM_ALLOW_CLOUD_FALLBACK", raising=False)
    monkeypatch.delenv("LACLAUGPT_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    enforce_local_model(manifest)

    assert __import__("os").environ["LLM_MODE"] == "local"
    assert __import__("os").environ["LLM_ALLOW_CLOUD_FALLBACK"] == "0"
    assert __import__("os").environ["LACLAUGPT_OLLAMA_MODEL"] == AI26_MODEL


def test_cloud_mode_is_rejected(monkeypatch) -> None:
    manifest = FrozenRunManifest(
        project_id="ai26",
        run_id="run-001",
        schema_version=SCHEMA_VERSION,
        config_sha256="a",
        codebook_sha256="b",
        model=AI26_MODEL,
        public_git_sha="abc",
    )
    monkeypatch.setenv("LLM_MODE", "cloud")

    with pytest.raises(ValueError, match="forbids cloud"):
        enforce_local_model(manifest)


def test_ai26_retry_requeues_with_incremented_attempt() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    calls = 0

    def flaky(task: TaskEnvelope):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return {"task_id": task.task_id, "attempt": task.attempt}

    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="id-1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/1",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
    )
    queue.publish(task)
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=flaky,
        worker_id="worker-1",
        provenance={},
        max_attempts=3,
    )

    assert worker.run_once() == "retry"
    assert len(queue.pending) == 1
    assert queue.pending[0].task.attempt == 2
    assert worker.run_once() == "completed"
    assert store.has_result("id-1")


def test_ai26_retry_reaches_dead_letter_instead_of_looping_forever() -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="id-1",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/1",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="cb",
    )
    queue.publish(task)
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(RuntimeError("still broken")),
        worker_id="worker-1",
        provenance={},
        max_attempts=3,
    )

    assert worker.run_once() == "retry"
    assert store.failures[-1]["task"]["attempt"] == 1
    assert worker.run_once() == "retry"
    assert store.failures[-1]["task"]["attempt"] == 2
    assert worker.run_once() == "dead-letter"
    assert store.failures[-1]["task"]["attempt"] == 3
    assert store.failures[-1]["terminal"] is True
    assert store.has_terminal_failure("id-1")
    assert store.failure_summary() == {"events": 3, "distinct": 1, "terminal": 1}
    assert len(queue.dead_letters) == 1
    assert queue.dead_letters[0]["task"]["attempt"] == 3
    assert not queue.pending


@pytest.mark.parametrize("reclaimed", [False, True], ids=["claim", "reclaim"])
def test_manifest_validation_failure_is_quarantined_without_blocking_queue(reclaimed: bool) -> None:
    queue = InMemoryTaskQueue()
    store = InMemoryTaskStore()
    handled: list[str] = []

    stale = TaskEnvelope(
        task_id="stale-task",
        idempotency_key="stale-id",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/stale",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="stale-codebook",
    )
    current = TaskEnvelope(
        task_id="current-task",
        idempotency_key="current-id",
        project_id="ai26",
        run_id="run-001",
        task_type="analyze-record",
        record_ref="https://example.invalid/source/current",
        schema_version=SCHEMA_VERSION,
        config_revision="cfg",
        codebook_revision="current-codebook",
    )
    queue.publish(stale)
    queue.publish(current)

    if reclaimed:
        claimed = queue.claim()
        assert claimed is not None
        assert claimed.task.task_id == "stale-task"

    def validate(task: TaskEnvelope) -> None:
        if task.codebook_revision != "current-codebook":
            raise ValueError("task/run manifest mismatch: codebook_revision")

    def handle(task: TaskEnvelope) -> dict[str, str]:
        handled.append(task.task_id)
        return {"task_id": task.task_id}

    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=handle,
        worker_id="worker-1",
        provenance={"run_id": "run-001"},
        validator=validate,
        max_attempts=3,
    )
    reclaim_idle_ms = 0 if reclaimed else None

    assert worker.run_once(reclaim_idle_ms=reclaim_idle_ms) == "dead-letter"
    assert handled == []
    assert worker.last_failure_class == "ValueError"
    assert len(store.failures) == 1
    assert store.failures[0]["task"]["attempt"] == 1
    assert store.failures[0]["provenance"]["run_id"] == "run-001"
    assert "codebook_revision" in store.failures[0]["error"]
    assert len(queue.dead_letters) == 1
    assert queue.dead_letters[0]["task"]["attempt"] == 1

    assert worker.run_once(reclaim_idle_ms=reclaim_idle_ms) == "completed"
    assert handled == ["current-task"]
    assert store.has_result("current-id")
    assert not queue.pending
    assert not queue.claimed



def test_permanent_failure_is_not_reseeded_across_cycles_until_rearmed() -> None:
    class Binding:
        manifest = type("Manifest", (), {"run_id": "run-001"})()

        @staticmethod
        def task_from_handoff(handoff):
            return TaskEnvelope(
                task_id=f"analysis:{handoff['handoff_key']}",
                idempotency_key=handoff["handoff_key"],
                project_id="ai26",
                run_id="run-001",
                task_type="analyze-record",
                record_ref=handoff["source_url"],
                schema_version=SCHEMA_VERSION,
                config_revision="cfg",
                codebook_revision="cb",
            )

    class Handoff:
        row = {
            "status": "ready",
            "run_id": "run-001",
            "handoff_key": "handoff-permanent",
            "source_url": "https://example.invalid/permanent",
        }

        def ready_handoffs(self, run_id: str, *, limit: int, offset: int = 0):
            assert run_id == "run-001"
            return [self.row][offset : offset + limit]

    binding = Binding()
    handoff = Handoff()
    store = InMemoryTaskStore()
    queue = InMemoryTaskQueue()
    worker = AI26TaskWorker(
        queue=queue,
        durable_store=store,
        handler=lambda _: (_ for _ in ()).throw(RuntimeError("permanent")),
        worker_id="worker-284",
        provenance={},
        max_attempts=3,
    )

    assert seed_ready_tasks(binding, handoff, queue, store, limit=1) == 1
    assert worker.run_once() == "retry"
    assert worker.run_once() == "retry"
    assert worker.run_once() == "dead-letter"
    assert [row["task"]["attempt"] for row in store.failures] == [1, 2, 3]
    assert store.has_terminal_failure("handoff-permanent")

    second_cycle_queue = InMemoryTaskQueue()
    assert seed_ready_tasks(binding, handoff, second_cycle_queue, store, limit=1) == 0
    assert second_cycle_queue.pending == []

    assert store.rearm_terminal_failure("handoff-permanent") == 1
    assert not store.has_terminal_failure("handoff-permanent")
    third_cycle_queue = InMemoryTaskQueue()
    assert seed_ready_tasks(binding, handoff, third_cycle_queue, store, limit=1) == 1
    assert third_cycle_queue.pending[0].task.attempt == 1
