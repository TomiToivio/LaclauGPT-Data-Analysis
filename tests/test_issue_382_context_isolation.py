"""Regression for EP24 #301-class cross-record context mutation (AI26 #382)."""

from types import SimpleNamespace

from laclaugpt_data_analysis import distributed_worker
from laclaugpt_data_analysis.pipeline_context import PipelineContext


def test_handler_isolates_mutable_context_between_records(monkeypatch):
    shared = PipelineContext(
        project_context="AI26",
        project_config={"nested": {"sample": "original"}},
        provenance={"source": ["original"]},
    )
    contexts = []

    def analyze(record, *, context, **kwargs):
        contexts.append(context)
        context.provenance["source"].append(record.source_url)
        # A simulated stage mutating nested project configuration should not
        # taint the next source, even if the previous stage succeeds.
        context.project_config["nested"]["sample"] = record.source_url
        return SimpleNamespace(model_dump=lambda **_: {"source_url": record.source_url})

    monkeypatch.setattr(distributed_worker, "run_canonical_pipeline", analyze)
    handler = object.__new__(distributed_worker.AI26Handler)
    handler.context = shared
    handler.handoff = SimpleNamespace(
        resolve=lambda ref: SimpleNamespace(source_url=ref)
    )
    handler.stager = None
    handler.provider = object()
    handler.codebook = SimpleNamespace(entries=[])

    for source in ("https://example.org/1", "https://example.org/2"):
        assert handler(SimpleNamespace(record_ref=source)) == {"source_url": source}

    assert contexts[0] is not contexts[1]
    assert contexts[0].provenance["source"] == ["original", "https://example.org/1"]
    assert contexts[1].provenance["source"] == ["original", "https://example.org/2"]
    assert contexts[1].project_config["nested"]["sample"] == "https://example.org/2"
    assert shared.provenance == {"source": ["original"]}
    assert shared.project_config == {"nested": {"sample": "original"}}
