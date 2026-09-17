from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.canonical_pipeline import PipelineContext
from laclaugpt_data_analysis import contextual_entrypoints


def test_contextual_entrypoint_preserves_optional_stage_project_config(monkeypatch) -> None:
    record = CanonicalRecord(source_url="https://example.invalid/issue-75")
    context = PipelineContext(
        project_config={
            "analysis": {
                "dna_statement_coding": {"enabled": True},
                "critical_ai": {"enabled": True},
            }
        },
        project_config_revision="frozen-config-sha",
        provenance={"private_config_sha256": ["frozen-config-sha"]},
    )
    seen = {}

    monkeypatch.setattr(contextual_entrypoints, "load_settings", lambda: type("S", (), {"project_id": "ai26"})())
    monkeypatch.setattr(contextual_entrypoints, "production_context_policy", lambda *a, **k: object())
    monkeypatch.setattr(contextual_entrypoints, "production_summary_repository", lambda *a, **k: None)
    monkeypatch.setattr(contextual_entrypoints, "production_retrieval_backend", lambda *a, **k: None)
    monkeypatch.setattr(
        contextual_entrypoints,
        "run_contextual_canonical_pipeline",
        lambda input_record, **kwargs: input_record,
    )

    def fake_optional(input_record, *, context, **kwargs):
        seen["context"] = context
        return None

    monkeypatch.setattr(contextual_entrypoints, "run_optional_critical_ai", fake_optional)

    result = contextual_entrypoints._contextual_run(
        record,
        provider=object(),
        context=context,
        codebook_entries=[],
        project_profile="ai26",
        allow_cloud_fallback=False,
    )

    assert result is record
    assert seen["context"].project_config["analysis"]["critical_ai"]["enabled"] is True
    assert seen["context"].project_config_revision == "frozen-config-sha"
