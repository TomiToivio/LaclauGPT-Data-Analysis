from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord, ContentSection, RawCaptureSection
from laclaugpt_data_analysis.plugin_pipeline import (
    AnalysisPipeline,
    LegacyLaclauPlugin,
    PluginContext,
    PluginRegistry,
    PluginSelection,
    PluginSpec,
)


def record(text: str = "Hello social data science") -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.test/1",
        raw_capture=RawCaptureSection(payload={"original": True}),
        content=ContentSection(text=text),
    )


@dataclass
class UppercasePlugin:
    spec = PluginSpec(
        name="uppercase",
        version="1.0",
        requires=frozenset({"text"}),
        produces=frozenset({"uppercase_text"}),
        deterministic=True,
    )

    def process(self, item, context, config):
        del context, config
        return {"text": item.content.text.upper()}


@dataclass
class WordCountPlugin:
    spec = PluginSpec(
        name="word_count",
        version="1.0",
        requires=frozenset({"text"}),
        produces=frozenset({"word_count"}),
        dependencies=("uppercase",),
        deterministic=True,
    )

    def process(self, item, context, config):
        del context, config
        return {"count": len(item.content.text.split())}


@dataclass
class BrokenPlugin:
    spec = PluginSpec(name="broken", version="1.0", requires=frozenset({"text"}))

    def process(self, item, context, config):
        del item, context, config
        raise RuntimeError("synthetic failure")


@dataclass
class NeedsFramesPlugin:
    spec = PluginSpec(name="needs_frames", version="1.0", requires=frozenset({"frames"}))

    def process(self, item, context, config):
        del item, context, config
        return {"ok": True}


@dataclass
class CorpusCountPlugin:
    spec = PluginSpec(
        name="corpus_count",
        version="1.0",
        scope="corpus",
        requires=frozenset({"corpus"}),
        produces=frozenset({"corpus_metrics"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context, config
        return {"records": len(records), "urls": [item.source_url for item in records]}


def registry(*plugins):
    result = PluginRegistry()
    for plugin in plugins:
        result.register(plugin)
    return result


def test_preprocess_only_preserves_raw_and_has_stable_postprocess():
    source = record()
    output = AnalysisPipeline(PluginRegistry()).run_record(source)
    item = output.records[0]
    assert item.raw_capture.payload == {"original": True}
    assert item.analysis.status == "preprocessed"
    assert item.analysis.plugin_results == {}
    assert output.flat_rows()[0]["source_url"] == source.source_url


def test_one_and_multiple_plugins_are_namespaced_with_provenance():
    pipe = AnalysisPipeline(
        registry(UppercasePlugin(), WordCountPlugin()),
        [PluginSelection("uppercase"), PluginSelection("word_count")],
    )
    item = pipe.run_record(record(), PluginContext(project_id="ai26", run_id="run-1")).records[0]
    assert item.analysis.plugin_results["uppercase"]["output"]["text"] == "HELLO SOCIAL DATA SCIENCE"
    assert item.analysis.plugin_results["word_count"]["output"]["count"] == 4
    assert item.analysis.plugin_results["uppercase"]["run_id"] == "run-1"
    assert item.raw_capture.payload == {"original": True}
    assert [event.method for event in item.provenance][-2:] == [
        "plugin:uppercase",
        "plugin:word_count",
    ]


def test_disabled_plugin_is_absent():
    pipe = AnalysisPipeline(
        registry(UppercasePlugin()),
        [PluginSelection("uppercase", enabled=False)],
    )
    item = pipe.run_record(record()).records[0]
    assert "uppercase" not in item.analysis.plugin_results


def test_dependency_order_is_validated():
    with pytest.raises(ValueError, match="depends on earlier"):
        AnalysisPipeline(
            registry(UppercasePlugin(), WordCountPlugin()),
            [PluginSelection("word_count"), PluginSelection("uppercase")],
        )


def test_missing_capability_and_plugin_failure_are_isolated():
    pipe = AnalysisPipeline(
        registry(NeedsFramesPlugin(), BrokenPlugin(), UppercasePlugin()),
        [
            PluginSelection("needs_frames"),
            PluginSelection("broken"),
            PluginSelection("uppercase"),
        ],
    )
    result = pipe.run_record(record())
    item = result.records[0]
    assert item.analysis.plugin_failures["needs_frames"]["status"] == "missing-capability"
    assert item.analysis.plugin_failures["broken"]["status"] == "failed"
    assert "uppercase" in item.analysis.plugin_results
    assert item.analysis.status == "analysis-partial"


def test_record_and_corpus_plugins_share_one_contract():
    pipe = AnalysisPipeline(
        registry(UppercasePlugin(), CorpusCountPlugin()),
        [PluginSelection("uppercase"), PluginSelection("corpus_count")],
    )
    result = pipe.run_corpus([record("one"), record("two words")])
    assert len(result.records) == 2
    assert result.sidecars["corpus_count"]["output"]["records"] == 2
    assert all("uppercase" in item.analysis.plugin_results for item in result.records)


def test_legacy_laclau_adapter_makes_existing_workflow_a_plugin():
    def executor(item: CanonicalRecord, config: Mapping[str, Any]) -> CanonicalRecord:
        assert config["codebook"] == "test"
        item.analysis.summary = "legacy Laclau result"
        item.analysis.formula_of_populism = {"us": ["workers"], "frontier": "platform power"}
        return item

    laclau = LegacyLaclauPlugin(executor)
    pipe = AnalysisPipeline(
        registry(laclau),
        [PluginSelection("laclau", {"codebook": "test"})],
    )
    item = pipe.run_record(record()).records[0]
    result = item.analysis.plugin_results["laclau"]["output"]
    assert result["summary"] == "legacy Laclau result"
    assert result["formula_of_populism"]["frontier"] == "platform power"
    assert item.source_url == "https://example.test/1"
