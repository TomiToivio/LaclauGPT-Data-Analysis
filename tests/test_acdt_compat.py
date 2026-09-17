from datetime import UTC, datetime

from laclaugpt_data_analysis.analysis.acdt_compat import (
    CloseReadingSamplerPlugin,
    HashtagCooccurrencePlugin,
    TemporalPeakPlugin,
    WordFrequencyPlugin,
)
from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, SourceSection
from laclaugpt_data_analysis.plugin_pipeline import AnalysisPipeline, PluginContext, PluginRegistry, PluginSelection


def _record(record_id: str, text: str, *, day: int, hashtags=(), author="a") -> CanonicalRecord:
    return CanonicalRecord(
        source_url=f"x:{record_id}",
        source=SourceSection(
            platform="twitter",
            author=author,
            created_at=datetime(2021, 1, day, 12, 0, tzinfo=UTC),
            raw_metadata={"hashtags": list(hashtags)},
        ),
        content=ContentSection(text=text, language="en"),
    )


def test_result_envelope_declares_stable_method_and_interpretation_mode():
    registry = PluginRegistry()
    registry.register(WordFrequencyPlugin())
    pipeline = AnalysisPipeline(registry, [PluginSelection("acdt_word_frequency")])
    result = pipeline.run_corpus(
        [_record("1", "AI progress AI", day=1)],
        PluginContext(project_id="ai26", run_id="run-1", metadata={"corpus_id": "sample"}),
    )
    envelope = result.sidecars["acdt_word_frequency"]
    assert envelope["schema_version"] == "acdt-result/1.0"
    assert envelope["method_id"] == "word_frequency"
    assert envelope["method_version"] == "1.0"
    assert envelope["interpretation_mode"] == "exploratory_instrumentalist"
    assert envelope["study_id"] == "ai26"
    assert envelope["input_record_ids"] == ["x:1"]


def test_hashtag_network_is_explicitly_not_laclaudian_articulation():
    plugin = HashtagCooccurrencePlugin()
    output = plugin.process_corpus(
        [
            _record("1", "one", day=1, hashtags=("AI", "progress")),
            _record("2", "two", day=1, hashtags=("AI", "progress")),
        ],
        PluginContext(),
        {},
    )
    assert output["edges"][0]["relation"] == "cooccurrence_candidate"
    assert output["semantic_status"] == "cooccurrence_is_not_laclaudian_articulation"
    serialized = repr(output).lower()
    assert "hegemony" not in serialized
    assert "ideological_formation" not in serialized


def test_legacy_absolute_peak_threshold_keeps_evidence_record_ids():
    plugin = TemporalPeakPlugin()
    records = [_record(str(i), "mask", day=2, hashtags=("mask",)) for i in range(3)]
    output = plugin.process_corpus(records, PluginContext(), {"threshold_count": 3, "hashtag": "mask"})
    assert output["threshold_rule"] == "absolute_count_gte"
    assert len(output["peaks"]) == 1
    assert output["peaks"][0]["record_ids"] == ["x:0", "x:1", "x:2"]


def test_close_reading_random_sample_is_reproducible():
    plugin = CloseReadingSamplerPlugin()
    records = [_record(str(i), f"text {i}", day=1) for i in range(10)]
    config = {"mode": "random", "n": 3, "seed": 42}
    first = plugin.process_corpus(records, PluginContext(), config)
    second = plugin.process_corpus(records, PluginContext(), config)
    assert first["record_ids"] == second["record_ids"]
