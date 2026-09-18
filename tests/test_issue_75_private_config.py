# ruff: noqa: I001
import hashlib
import json
from pathlib import Path

import pytest

import laclaugpt_data_analysis.task_queue as task_queue
from laclaugpt_data_analysis.canonical import CanonicalRecord, SCHEMA_VERSION
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.critical_ai import critical_ai_enabled
from laclaugpt_data_analysis.distributed_worker import AI26Handler, AI26_MODEL, WorkerBinding
from laclaugpt_data_analysis.dna_statement_coding import dna_statement_coding_enabled


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(tmp_path: Path, config_text: str) -> WorkerBinding:
    private = tmp_path / "private"
    private.mkdir()
    config = private / "analysis.json"
    codebook = private / "codebook.json"
    manifest = private / "run.json"
    config.write_text(config_text, encoding="utf-8")
    codebook.write_text(
        '{"codebook_id":"ai26-test","version":"1","title":"Synthetic","entries":[]}',
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "project_id": "ai26",
                "run_id": "run-075",
                "schema_version": SCHEMA_VERSION,
                "config_sha256": _sha(config),
                "codebook_sha256": _sha(codebook),
                "model": AI26_MODEL,
                "public_git_sha": "test-sha",
            }
        ),
        encoding="utf-8",
    )
    return WorkerBinding.build(
        manifest_path=manifest,
        private_root=private,
        private_config=config,
        codebook=codebook,
        worker_id="worker-75",
    )


def _task(binding: WorkerBinding) -> task_queue.TaskEnvelope:
    manifest = binding.manifest
    return task_queue.TaskEnvelope(
        task_id="analysis:test-75",
        idempotency_key="test-75",
        project_id=manifest.project_id,
        run_id=manifest.run_id,
        task_type="analyze-record",
        record_ref="https://example.invalid/75",
        schema_version=manifest.schema_version,
        config_revision=manifest.config_sha256,
        codebook_revision=manifest.codebook_sha256,
    )


class _Handoff:
    def resolve(self, source_url: str) -> CanonicalRecord:
        return CanonicalRecord(source_url=source_url)


@pytest.mark.parametrize("enabled", [False, True])
def test_worker_publishes_frozen_private_config_to_pipeline_context(
    tmp_path: Path, monkeypatch, enabled: bool
) -> None:
    config = {
        "analysis": {
            "dna_statement_coding": {"enabled": enabled},
            "critical_ai": {"enabled": enabled},
        }
    }
    binding = _binding(tmp_path, json.dumps(config))
    captured = {}

    class _Provider:
        def __init__(self, host=None, min_vram_gb=None):
            captured["provider_args"] = {"host": host, "min_vram_gb": min_vram_gb}

    def fake_pipeline(
        record,
        *,
        provider,
        context=None,
        codebook_entries=None,
        model="auto",
        project_profile="generic",
        allow_cloud_fallback=None,
        **kwargs,
    ):
        captured["provider"] = provider
        captured["context"] = context
        captured["codebook_entries"] = codebook_entries
        captured["model"] = model
        captured["project_profile"] = project_profile
        captured["allow_cloud_fallback"] = allow_cloud_fallback
        return record

    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.OllamaProvider", _Provider)
    monkeypatch.setattr(
        "laclaugpt_data_analysis.distributed_worker.run_canonical_pipeline",
        fake_pipeline,
    )

    handler = AI26Handler(binding, Settings(project_id="ai26"), _Handoff())
    handler(_task(binding))

    context = captured["context"]
    assert context.project_config == config
    # Manifest revisions are carried in declared provenance fields. PipelineContext
    # does not declare config_revision/project_config_revision/codebook_revision.
    assert context.provenance["private_config_sha256"] == [binding.manifest.config_sha256]
    assert context.provenance["codebook_sha256"] == [binding.manifest.codebook_sha256]
    assert captured["provider_args"] == {
        "host": __import__("laclaugpt_data_analysis.distributed_worker", fromlist=["resolve_llm_host"]).resolve_llm_host() or None,
        "min_vram_gb": None,
    }
    assert captured["provider"] is handler.provider
    assert captured["codebook_entries"] == handler.codebook.entries
    assert captured["model"] == AI26_MODEL
    assert captured["project_profile"] == "ai26"
    assert captured["allow_cloud_fallback"] is False
    assert critical_ai_enabled(context.project_config) is enabled
    assert dna_statement_coding_enabled(context.project_config) is enabled


def test_worker_fails_closed_on_malformed_private_config(tmp_path: Path, monkeypatch) -> None:
    binding = _binding(tmp_path, "{not-json")

    class _Provider:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.OllamaProvider", _Provider)

    with pytest.raises(ValueError, match="unreadable or malformed"):
        AI26Handler(binding, Settings(project_id="ai26"), _Handoff())


def test_worker_fails_closed_on_non_object_private_config(tmp_path: Path, monkeypatch) -> None:
    binding = _binding(tmp_path, "[]")

    class _Provider:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.OllamaProvider", _Provider)

    with pytest.raises(ValueError, match="must be a JSON object"):
        AI26Handler(binding, Settings(project_id="ai26"), _Handoff())


def test_ai26_handler_uses_real_runtime_signatures(tmp_path: Path, monkeypatch) -> None:
    binding = _binding(tmp_path, "{}")
    monkeypatch.delenv("LACLAUGPT_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    handler = AI26Handler(binding, Settings(project_id="ai26"), _Handoff())

    assert handler.provider.__class__.__name__ == "OllamaProvider"
    assert handler.context.project_config == {}
    assert handler.context.provenance["private_config_sha256"] == [
        binding.manifest.config_sha256
    ]
    assert handler.context.provenance["codebook_sha256"] == [
        binding.manifest.codebook_sha256
    ]
    assert handler.stager is None
