import hashlib
import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.distributed_worker import (
    AI26_MODEL,
    FrozenRunManifest,
    WorkerBinding,
    collection_records_name,
    enforce_local_model,
)
from laclaugpt_data_analysis.task_queue import TaskEnvelope


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_binding(tmp_path: Path) -> WorkerBinding:
    private = tmp_path / "private"
    private.mkdir()
    config = private / "ai26.json"
    codebook = private / "codebook.json"
    config.write_text('{"arena":"elites"}', encoding="utf-8")
    codebook.write_text(
        '{"codebook_id":"ai26-test","version":"1","title":"Synthetic","entries":[]}',
        encoding="utf-8",
    )
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps(
            {
                "project_id": "ai26",
                "run_id": "run-001",
                "schema_version": SCHEMA_VERSION,
                "config_sha256": sha(config),
                "codebook_sha256": sha(codebook),
                "model": AI26_MODEL,
                "public_git_sha": "abc123",
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
    manifest = tmp_path / "run.json"
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="inside"):
        WorkerBinding.build(
            manifest_path=manifest,
            private_root=private,
            private_config=outside,
            codebook=codebook,
        )


def test_manifest_hashes_and_schema_are_frozen(tmp_path: Path) -> None:
    binding = make_binding(tmp_path)
    binding.private_config.write_text('{"arena":"changed"}', encoding="utf-8")

    with pytest.raises(ValueError, match="config hash"):
        binding.validate_files()


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
    assert "payload" not in task.to_fields()


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
