"""Issue #140: Phase 1 default pipeline, phase gating and prompt-profile separation.

These tests encode the acceptance criteria of issue #140:

* the default pipeline runs the legacy five-stage conceptual order
  (preprocessing -> conditional frame analysis -> summary -> Laclaudian
  discourse analysis -> postprocessing);
* DNA and SNA / Phase 2 methods are not invoked by default;
* frame analysis is skipped cleanly for text-only records;
* postprocessing runs after discourse analysis and produces validated output;
* AI26 and EP24 have separate, explicitly named prompt profiles and neither
  leaks the other's project assumptions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from laclaugpt_data_analysis.canonical import CanonicalRecord  # noqa: E402
from laclaugpt_data_analysis.canonical_pipeline import (  # noqa: E402
    prompt_ids_for_stage,
    run_canonical_pipeline,
)
from laclaugpt_data_analysis.llm.base import (  # noqa: E402
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
)
from laclaugpt_data_analysis.phases import (  # noqa: E402
    CONDITIONAL_STAGES,
    PHASE1_STAGE_ORDER,
    PHASE2_CAPABILITIES,
    default_stage_order,
    is_phase2_capability,
    phase_manifest,
    stage_phase,
)
from laclaugpt_data_analysis.prompt_library import load_prompt  # noqa: E402


class RecordingProvider:
    """Fake provider that returns empty JSON objects and records every request."""

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content="{}",
            provenance=LLMCallProvenance(
                requested_mode="local",
                requested_model="fake-model",
                resolved_model="fake-model",
                actual_mode="local",
                actual_model="fake-model",
                endpoint="fake",
            ),
        )


def text_only_record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/ai26/text/1",
        content={"text": "AI will determine the future of work and democracy."},
    )


def multimodal_record() -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/ai26/video/1",
        content={
            "text": "A speaker discusses an AI system while a chart is shown.",
            "frames": [
                {"id": "frame-001", "timestamp_seconds": 12.5, "description": "Synthetic keyframe"}
            ],
        },
    )


# ---------------------------------------------------------------------------
# Phase registry contract
# ---------------------------------------------------------------------------

def test_phase1_default_order_matches_legacy_pipeline() -> None:
    assert tuple(default_stage_order()) == (
        "preprocess",
        "frame",
        "summary",
        "discourse",
        "postprocess",
    )
    assert PHASE1_STAGE_ORDER == (
        "preprocess",
        "frame",
        "summary",
        "discourse",
        "postprocess",
    )


def test_frame_stage_is_conditional_and_others_are_not() -> None:
    assert CONDITIONAL_STAGES == frozenset({"frame"})
    assert stage_phase("frame").conditional is True
    for name in ("preprocess", "summary", "discourse", "postprocess"):
        assert stage_phase(name).conditional is False, name


def test_phase1_stages_are_declared_default_enabled() -> None:
    for name in PHASE1_STAGE_ORDER:
        meta = stage_phase(name)
        assert meta.phase == 1, name
        assert meta.default_enabled is True, name
        assert meta.runs_by_default is True, name


def test_phase1_stages_record_their_legacy_origin() -> None:
    """Each stage must remain recognisably descended from its puhti_* ancestor."""
    expected = {
        "preprocess": "puhti_preprocess.py",
        "frame": "puhti_frame.py",
        "summary": "puhti_summary.py",
        "discourse": "puhti_populism.py",
        "postprocess": "puhti_postprocess.py",
    }
    for stage, legacy in expected.items():
        assert stage_phase(stage).legacy_origin == legacy


def test_phase2_capabilities_are_declared_not_default() -> None:
    for capability in ("dna_statement_coding", "critical_ai", "sna", "ant", "valueflows"):
        assert is_phase2_capability(capability), capability
        meta = stage_phase(capability)
        assert meta.phase == 2
        assert meta.default_enabled is False
        assert meta.experimental is True
        assert meta.optional is True
        assert meta.runs_by_default is False


def test_phase2_manifest_lists_capabilities() -> None:
    manifest = phase_manifest()
    assert manifest["phase1_order"] == list(PHASE1_STAGE_ORDER)
    assert manifest["conditional"] == ["frame"]
    assert set(manifest["phase2_capabilities"]) == set(PHASE2_CAPABILITIES)


# ---------------------------------------------------------------------------
# Default execution order and gating
# ---------------------------------------------------------------------------

def test_default_run_executes_phase1_stages_in_order() -> None:
    record = text_only_record()
    run_canonical_pipeline(record, provider=RecordingProvider(), model="fake-model")

    outputs = record.intermediate.stage_outputs
    assert "preprocess_contract" in outputs
    assert "summary_preanalysis" in outputs
    assert "discourse_analysis" in outputs
    assert "phase_manifest" in outputs

    # Postprocessing runs after discourse analysis: analysis is populated from
    # the discourse proposal, which only exists once that stage has run.
    assert record.analysis.status == "analyzed"
    assert record.analysis.completed_at is not None

    assert outputs["phase_manifest"][-1]["phase1_order"] == list(PHASE1_STAGE_ORDER)


def test_phase2_methods_are_not_invoked_by_default() -> None:
    record = text_only_record()
    run_canonical_pipeline(record, provider=RecordingProvider(), model="fake-model")

    outputs = record.intermediate.stage_outputs
    assert "dna_statement_coding" not in outputs
    assert "critical_ai_analysis" not in outputs


def test_phase2_methods_are_not_invoked_for_ai26_default_config() -> None:
    """The shipped AI26 project config must not enable Phase 2 by default."""
    import yaml

    config = yaml.safe_load(
        (REPO / "config" / "projects" / "ai26.yaml").read_text(encoding="utf-8")
    )
    analysis = config["analysis"]
    assert analysis["dna_statement_coding"]["enabled"] is False
    assert analysis["critical_ai"]["enabled"] is False
    assert analysis["sna"] is False
    assert analysis["ant"] is False
    assert analysis["valueflows"] is False


def test_text_only_record_skips_frame_analysis() -> None:
    record = text_only_record()
    assert record.content.frames == []
    run_canonical_pipeline(record, provider=RecordingProvider(), model="fake-model")
    assert record.intermediate.frame_analysis == []


def test_multimodal_record_runs_frame_analysis() -> None:
    record = multimodal_record()
    provider = RecordingProvider()
    run_canonical_pipeline(record, provider=provider, model="fake-model", project_profile="ai26")
    analysed = [entry for entry in record.intermediate.frame_analysis if "analysis" in entry]
    assert len(analysed) == 1
    assert analysed[0]["frame_id"] == "frame-001"


def test_postprocess_produces_validated_structured_output() -> None:
    record = text_only_record()
    run_canonical_pipeline(record, provider=RecordingProvider(), model="fake-model")
    assert isinstance(record.analysis.formula_of_populism, dict)
    assert isinstance(record.analysis.uncertainty, list)
    assert isinstance(record.analysis.abstentions, list)
    assert record.intermediate.stage_outputs["phase_manifest"][-1]["stages"]


# ---------------------------------------------------------------------------
# Prompt-profile separation (#140)
# ---------------------------------------------------------------------------

def test_ai26_and_ep24_use_distinct_prompt_profiles() -> None:
    for stage in ("frame", "summary", "discourse"):
        ai26 = prompt_ids_for_stage("ai26", stage)
        ep24 = prompt_ids_for_stage("ep24", stage)
        assert ai26[0].startswith("ai26."), stage
        assert ai26[1].startswith("ai26."), stage
        assert not ep24[0].startswith("ai26."), stage
        assert not ep24[1].startswith("ai26."), stage
        assert ai26 != ep24, stage


def test_ai26_prompt_resources_all_resolve() -> None:
    for prompt_id in (
        "ai26.system",
        "ai26.frame_analysis",
        "ai26.summary_analysis",
        "ai26.discourse_analysis",
        "ai26.postprocess",
    ):
        resource = load_prompt(prompt_id, version="v1")
        assert resource.text.strip()
        assert len(resource.sha256) == 64


def test_ai26_prompts_contain_no_ep24_election_assumptions() -> None:
    """AI26 prompts must not carry over EP24's election-specific framing."""
    forbidden = (
        "european parliament",
        "ep2024",
        "2024 european",
        "election campaign",
    )
    for prompt_id in (
        "ai26.system",
        "ai26.frame_analysis",
        "ai26.summary_analysis",
        "ai26.discourse_analysis",
        "ai26.postprocess",
    ):
        text = load_prompt(prompt_id, version="v1").text.lower()
        for phrase in forbidden:
            assert phrase not in text, f"{prompt_id} leaks EP24 assumption: {phrase!r}"


def test_ep24_prompt_profile_retains_election_context() -> None:
    """EP24 keeps its election-specific research context where appropriate."""
    text = (
        load_prompt("ep24.laclau_analysis", version="v2").text
        + load_prompt("ep24.frame_analysis", version="v2").text
    ).lower()
    assert "ep24" in text


def test_ai26_prompts_state_evidence_and_abstention_rules() -> None:
    discourse = load_prompt("ai26.discourse_analysis", version="v1").text.lower()
    for rule in ("evidence", "abstention", "final discourse analysis"):
        assert rule in discourse, rule
    assert "candidate" in discourse


def test_ai26_prompts_cover_all_phase1_llm_stages() -> None:
    for stage in ("frame", "summary", "discourse", "postprocess"):
        system_id, task_id = prompt_ids_for_stage("ai26", stage)
        assert system_id == "ai26.system"
        assert load_prompt(task_id, version="v1").text.strip()


# ---------------------------------------------------------------------------
# Plugin phase metadata (#140)
# ---------------------------------------------------------------------------

def test_plugin_spec_phase_defaults_are_phase1() -> None:
    from laclaugpt_data_analysis.plugin_pipeline import PluginSpec

    spec = PluginSpec(name="demo", version="1.0")
    assert spec.phase == 1
    assert spec.runs_by_default is True
    spec.validate()


def test_phase2_plugin_cannot_be_default_enabled() -> None:
    from laclaugpt_data_analysis.plugin_pipeline import PluginSpec

    spec = PluginSpec(name="sna_like", version="1.0", phase=2, default_enabled=True)
    with pytest.raises(ValueError, match="phase 2 plugins must not be enabled by default"):
        spec.validate()


def test_network_and_acdt_plugins_are_declared_phase2() -> None:
    from laclaugpt_data_analysis.analysis.acdt_compat import (
        CloseReadingSamplerPlugin,
        HashtagCooccurrencePlugin,
        TemporalPeakPlugin,
        WordFrequencyPlugin,
    )
    from laclaugpt_data_analysis.analysis.acdt_networks import ActorInteractionNetworkPlugin

    for plugin in (
        WordFrequencyPlugin(),
        HashtagCooccurrencePlugin(),
        TemporalPeakPlugin(),
        CloseReadingSamplerPlugin(),
        ActorInteractionNetworkPlugin(),
    ):
        spec = plugin.spec
        assert spec.phase == 2, spec.name
        assert spec.default_enabled is False, spec.name
        assert spec.experimental is True, spec.name
        spec.validate()
