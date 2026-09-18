# ruff: noqa: I001
"""Issue #159: AI26Handler must construct collaborators with real signatures.

The scheduled AI26 run died in worker construction:

    TypeError: OllamaProvider.__init__() got an unexpected keyword argument 'model'

`AI26Handler` passed five kwargs to `PipelineContext`, only one of which is a declared
field, and handed `model=` to an `OllamaProvider` that does not accept it. Even after the
`TypeError` is fixed, the four undeclared kwargs are **silently discarded**, because
`PipelineContext` inherits plain `BaseModel` (no ``extra="forbid"``) — so the run would
proceed without the configured model, codebook or media stager while looking healthy.

Existing coverage in `test_issue_75_private_config.py` stubs both collaborators with
``*args, **kwargs`` shims, so the real signatures were never exercised. These tests use
the **real** objects and ``inspect.signature``, which is what lets them catch this class
of defect.
"""
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION
from laclaugpt_data_analysis.canonical_pipeline import (
    PipelineContext,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.config import Settings
from laclaugpt_data_analysis.distributed_worker import AI26Handler, AI26_MODEL, WorkerBinding
from laclaugpt_data_analysis.llm.ollama import OllamaProvider


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(tmp_path: Path, config_text: str = '{"analysis": {}}') -> WorkerBinding:
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
                "run_id": "run-159",
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
        worker_id="worker-159",
    )


class _Handoff:
    """Not exercised: these tests only cover handler construction."""

    def resolve(self, source_url: str):  # pragma: no cover
        raise AssertionError("resolve() must not be called during construction")


def _settings() -> Settings:
    return Settings(project_id="ai26", data_backend="csv", cache_backend="none")


# --------------------------------------------------------------------------
# Ground truth: the real signatures the handler must respect
# --------------------------------------------------------------------------

def test_ollama_provider_does_not_accept_model() -> None:
    params = set(inspect.signature(OllamaProvider.__init__).parameters) - {"self"}
    assert "model" not in params, (
        "OllamaProvider takes no `model`; the model is per-request. "
        f"signature params: {sorted(params)}"
    )


def test_run_canonical_pipeline_requires_provider_keyword() -> None:
    """The handler must call it with ``provider=``; the parameter is keyword-only."""
    sig = inspect.signature(run_canonical_pipeline)
    assert sig.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["provider"].default is inspect.Parameter.empty


def test_pipeline_context_silently_drops_unknown_kwargs() -> None:
    """Documents WHY the guard below is needed — this is the dangerous behaviour."""
    ctx = PipelineContext(project_id="ai26", codebook="SENTINEL", llm="SENTINEL")
    assert not hasattr(ctx, "project_id")
    assert not hasattr(ctx, "codebook")
    assert not hasattr(ctx, "llm")


# --------------------------------------------------------------------------
# The regression: construction against the real constructors
# --------------------------------------------------------------------------

def test_handler_construction_does_not_raise(tmp_path, monkeypatch) -> None:
    """The direct guard for issue #159.

    Before the fix this raised
    ``TypeError: OllamaProvider.__init__() got an unexpected keyword argument 'model'``.
    """
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    binding = _binding(tmp_path)
    try:
        AI26Handler(binding, _settings(), _Handoff())
    except TypeError as exc:  # pragma: no cover - only on regression
        pytest.fail(f"AI26Handler construction raised TypeError: {exc}")


def test_handler_exposes_a_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    handler = AI26Handler(_binding(tmp_path), _settings(), _Handoff())
    assert hasattr(handler, "provider"), "run_canonical_pipeline requires a provider"


def test_context_uses_only_declared_fields(tmp_path, monkeypatch) -> None:
    """No undeclared kwarg may be silently dropped on the way in."""
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    handler = AI26Handler(_binding(tmp_path), _settings(), _Handoff())
    declared = set(PipelineContext.model_fields)
    dumped = set(handler.context.model_dump())
    assert dumped <= declared, f"unexpected context fields: {dumped - declared}"


def test_context_carries_manifest_revisions(tmp_path, monkeypatch) -> None:
    """Config/codebook hashes must reach the context, not be dropped."""
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    binding = _binding(tmp_path)
    handler = AI26Handler(binding, _settings(), _Handoff())
    joined = json.dumps(handler.context.provenance)
    assert binding.manifest.config_sha256 in joined
    assert binding.manifest.codebook_sha256 in joined


def test_malformed_private_config_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    binding = _binding(tmp_path, "{not-json")
    with pytest.raises(ValueError, match="unreadable or malformed"):
        AI26Handler(binding, _settings(), _Handoff())


def test_non_object_private_config_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("laclaugpt_data_analysis.distributed_worker.resolve_llm_host", lambda: None)
    binding = _binding(tmp_path, "[]")
    with pytest.raises(ValueError, match="must be a JSON object"):
        AI26Handler(binding, _settings(), _Handoff())
