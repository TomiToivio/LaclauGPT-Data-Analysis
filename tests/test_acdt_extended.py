from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.analysis.acdt_affect import ValidatedLexiconAffectPlugin
from laclaugpt_data_analysis.analysis.acdt_multimodal import MultimodalRhetoricPerformativePlugin
from laclaugpt_data_analysis.analysis.acdt_networks import ActorInteractionNetworkPlugin
from laclaugpt_data_analysis.canonical import (
    CanonicalRecord,
    ContentSection,
    FrameReference,
    OcrObservation,
    SourceSection,
    Transcript,
)
from laclaugpt_data_analysis.plugin_pipeline import PluginContext


def test_actor_network_keeps_evidence_and_does_not_infer_ideology():
    record = CanonicalRecord(
        source_url="x:1",
        source=SourceSection(
            platform="twitter",
            author="alice",
            created_at=datetime(2021, 1, 1, tzinfo=UTC),
            raw_metadata={"mentions": ["bob"]},
        ),
        content=ContentSection(text="hello @bob"),
    )
    output = ActorInteractionNetworkPlugin().process_corpus([record], PluginContext(), {})
    assert output["edges"][0]["evidence_record_ids"] == ["x:1"]
    assert output["semantic_status"] == "interaction_network_not_discourse_coalition_or_ideology"


def test_affect_plugin_requires_declared_validated_language_lexicon():
    plugin = ValidatedLexiconAffectPlugin("emotion_intensity")
    record = CanonicalRecord(
        source_url="doc:1",
        source=SourceSection(language="en"),
        content=ContentSection(text="hope fear", language="en"),
    )
    with pytest.raises(ValueError):
        plugin.process(record, PluginContext(), {"lexicon": {"hope": 0.8}})

    output = plugin.process(
        record,
        PluginContext(),
        {
            "language": "en",
            "lexicon_id": "synthetic-v1",
            "lexicon_validation": "validated",
            "lexicon": {"hope": {"joy": 0.8}, "fear": {"fear": 0.9}},
        },
    )
    assert output["mean_intensity"] == {"fear": 0.9, "joy": 0.8}
    assert output["semantic_status"] == "auxiliary_measurement_not_affective_investment"


def test_multimodal_adapter_preserves_timecoded_evidence():
    record = CanonicalRecord(
        source_url="video:1",
        content=ContentSection(
            transcripts=[Transcript(id="t1", text="spoken", start_seconds=0, end_seconds=2)],
            ocr=[OcrObservation(id="o1", text="TEXT", frame_ref="f1", timestamp_seconds=1.5)],
            frames=[FrameReference(id="f1", timestamp_seconds=1.5, description="frame")],
        ),
    )
    output = MultimodalRhetoricPerformativePlugin().process(record, PluginContext(), {})
    assert output["timecodes_seconds"] == [1.5]
    assert output["evidence_record_ids"] == ["video:1"]
    assert "without_new_theoretical_inference" in output["semantic_status"]
