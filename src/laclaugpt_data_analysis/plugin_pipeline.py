"""Generic preprocess -> analysis plugins -> postprocess runtime.

The core deliberately knows nothing about Laclau, populism, framing, sentiment, or any
other substantive method. First-party and external methods implement the same versioned
plugin contract. Redis/distributed workers may wrap this runtime, but deployment remains
separate from the Collection and Visualization modules.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import entry_points
from typing import Any, Callable, Iterable, Literal, Mapping, Protocol, Sequence

from .canonical import CanonicalRecord

PluginScope = Literal["record", "corpus"]
InterpretationMode = Literal[
    "exploratory_instrumentalist",
    "measurement",
    "theoretical_interpretive",
]


def _stable_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """Versioned capability contract for one analytical method.

    ``name``/``version`` identify the software plugin. ``method_id`` and
    ``method_version`` identify the stable cross-repository research method. This
    distinction lets implementations evolve without silently changing the meaning of
    legacy AC/DT results.

    ``prompt_ids`` declares stable first-party/external prompt resources used by an
    LLM-assisted plugin. Prompt-free statistical/network plugins leave it empty.
    """

    name: str
    version: str
    scope: PluginScope = "record"
    requires: frozenset[str] = frozenset()
    produces: frozenset[str] = frozenset()
    dependencies: tuple[str, ...] = ()
    deterministic: bool = False
    model_dependencies: tuple[str, ...] = ()
    prompt_ids: tuple[str, ...] = ()
    config_schema_version: str = "1"
    method_id: str | None = None
    method_version: str | None = None
    interpretation_mode: InterpretationMode = "exploratory_instrumentalist"

    @property
    def stable_method_id(self) -> str:
        return self.method_id or self.name

    @property
    def stable_method_version(self) -> str:
        return self.method_version or self.version

    def validate(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("plugin name/version must not be empty")
        if self.scope not in {"record", "corpus"}:
            raise ValueError(f"unsupported plugin scope: {self.scope}")
        if self.name in self.dependencies:
            raise ValueError("plugin cannot depend on itself")
        if any(not prompt_id.strip() for prompt_id in self.prompt_ids):
            raise ValueError("plugin prompt IDs must not be empty")
        if self.interpretation_mode not in {
            "exploratory_instrumentalist",
            "measurement",
            "theoretical_interpretive",
        }:
            raise ValueError(f"unsupported interpretation mode: {self.interpretation_mode}")
        if not self.stable_method_id.strip() or not self.stable_method_version.strip():
            raise ValueError("stable method id/version must not be empty")


@dataclass(slots=True)
class PluginContext:
    project_id: str = "default"
    run_id: str = ""
    worker_id: str = ""
    config_revision: str = ""
    codebook_revision: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalysisPlugin(Protocol):
    spec: PluginSpec

    def process(
        self,
        record: CanonicalRecord,
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class CorpusAnalysisPlugin(Protocol):
    spec: PluginSpec

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class PluginSelection:
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class PipelineResult:
    records: list[CanonicalRecord]
    sidecars: dict[str, Any] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def flat_rows(self) -> list[dict[str, Any]]:
        """Stable, dataframe-friendly projection without flattening plugin internals."""
        rows: list[dict[str, Any]] = []
        for record in self.records:
            rows.append(
                {
                    "schema_version": record.schema_version,
                    "source_url": record.source_url,
                    "platform": record.source.platform,
                    "source_type": record.source.source_type,
                    "author": record.source.author,
                    "created_at": record.source.created_at,
                    "text": record.content.text,
                    "analysis_status": record.analysis.status,
                    "plugin_results": json.dumps(
                        record.analysis.plugin_results,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    "plugin_failures": json.dumps(
                        record.analysis.plugin_failures,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    "human_summary": record.human_readable.summary,
                }
            )
        return rows


class PluginRegistry:
    """First-party/external registry with optional Python entry-point discovery."""

    ENTRY_POINT_GROUP = "laclaugpt.analysis_plugins"

    def __init__(self) -> None:
        self._plugins: dict[str, AnalysisPlugin | CorpusAnalysisPlugin] = {}

    def register(self, plugin: AnalysisPlugin | CorpusAnalysisPlugin) -> None:
        plugin.spec.validate()
        if plugin.spec.name in self._plugins:
            raise ValueError(f"analysis plugin already registered: {plugin.spec.name}")
        self._plugins[plugin.spec.name] = plugin

    def get(self, name: str) -> AnalysisPlugin | CorpusAnalysisPlugin:
        try:
            return self._plugins[name]
        except KeyError as exc:
            raise KeyError(f"analysis plugin not registered: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._plugins))

    def discover(self) -> None:
        """Load external plugins using the standard ``laclaugpt.analysis_plugins`` group."""
        discovered = entry_points()
        selected = discovered.select(group=self.ENTRY_POINT_GROUP)
        for point in selected:
            plugin = point.load()
            if isinstance(plugin, type):
                plugin = plugin()
            self.register(plugin)


class Preprocessor:
    """Stable generic normalization layer; never performs substantive theory coding."""

    def process(self, record: CanonicalRecord) -> tuple[CanonicalRecord, set[str]]:
        enriched = record.model_copy(deep=True)
        capabilities = self.capabilities(enriched)

        if not enriched.content.text.strip():
            chunks = [item.text for item in enriched.content.transcripts if item.text.strip()]
            chunks.extend(item.text for item in enriched.content.ocr if item.text.strip())
            if chunks:
                enriched.content.text = "\n".join(chunks)
                enriched.intermediate.stage_outputs["preprocess_text_assembly"] = {
                    "sources": ["transcript", "ocr"],
                    "generated_at": datetime.now(UTC).isoformat(),
                }
                capabilities.add("text")

        enriched.intermediate.stage_outputs["analysis_capabilities"] = sorted(capabilities)
        return enriched, capabilities

    @staticmethod
    def capabilities(record: CanonicalRecord) -> set[str]:
        capabilities = {"canonical_record", "metadata", "provenance"}
        if record.raw_capture.preserved:
            capabilities.add("raw")
        if record.content.text.strip():
            capabilities.add("text")
        if record.content.transcripts:
            capabilities.update({"transcript", "textual_representation"})
        if record.content.ocr:
            capabilities.update({"ocr", "textual_representation"})
        if record.content.frames:
            capabilities.add("frames")
        if record.content.media_references:
            capabilities.add("media")
        if record.evidence:
            capabilities.add("evidence")
        return capabilities


class Postprocessor:
    """Stable output validation/projection independent of which plugins ran."""

    def process(self, records: Sequence[CanonicalRecord], *, sidecars: Mapping[str, Any]) -> PipelineResult:
        output: list[CanonicalRecord] = []
        for record in records:
            validated = CanonicalRecord.model_validate(record.model_dump(mode="python"))
            if validated.analysis.plugin_failures:
                validated.analysis.status = "analysis-partial"
            elif validated.analysis.plugin_results:
                validated.analysis.status = "analysis-complete"
            else:
                validated.analysis.status = "preprocessed"
            output.append(validated)
        return PipelineResult(records=output, sidecars=dict(sidecars))


class AnalysisPipeline:
    """Fixed preprocess/postprocess around an arbitrary configured plugin chain."""

    def __init__(
        self,
        registry: PluginRegistry,
        selections: Iterable[PluginSelection] = (),
        *,
        preprocessor: Preprocessor | None = None,
        postprocessor: Postprocessor | None = None,
        fail_fast: bool = False,
    ) -> None:
        self.registry = registry
        self.selections = [selection for selection in selections if selection.enabled]
        self.preprocessor = preprocessor or Preprocessor()
        self.postprocessor = postprocessor or Postprocessor()
        self.fail_fast = fail_fast
        self._validate_order()

    def _validate_order(self) -> None:
        seen: set[str] = set()
        for selection in self.selections:
            plugin = self.registry.get(selection.name)
            missing = [name for name in plugin.spec.dependencies if name not in seen]
            if missing:
                raise ValueError(
                    f"plugin {plugin.spec.name} depends on earlier plugin(s): {', '.join(missing)}"
                )
            seen.add(plugin.spec.name)

    def _result_envelope(
        self,
        plugin: AnalysisPlugin | CorpusAnalysisPlugin,
        config: Mapping[str, Any],
        result: Mapping[str, Any],
        context: PluginContext,
        *,
        input_record_ids: Sequence[str],
    ) -> dict[str, Any]:
        method_id = plugin.spec.stable_method_id
        method_version = plugin.spec.stable_method_version
        validation_status = (
            "not_validated" if plugin.spec.interpretation_mode == "measurement" else "not_applicable"
        )
        return {
            # Shared AC/DT result contract.
            "schema_version": "acdt-result/1.0",
            "method_id": method_id,
            "method_version": method_version,
            "interpretation_mode": plugin.spec.interpretation_mode,
            "study_id": context.project_id or None,
            "corpus_id": context.metadata.get("corpus_id"),
            "input_record_ids": list(input_record_ids),
            "parameters": dict(config),
            "provenance": {
                "producer": "laclaugpt-data-analysis",
                "producer_version": plugin.spec.version,
                "git_commit": context.metadata.get("git_commit"),
                "run_id": context.run_id or None,
                "worker_id": context.worker_id or None,
                "created_at": datetime.now(UTC).isoformat(),
            },
            "validation": {
                "status": validation_status,
                "human_review_status": "provisional",
                "method": None,
                "notes": None,
            },
            # Backwards-compatible plugin metadata retained for existing consumers.
            "plugin": plugin.spec.name,
            "plugin_version": plugin.spec.version,
            "scope": plugin.spec.scope,
            "deterministic": plugin.spec.deterministic,
            "model_dependencies": list(plugin.spec.model_dependencies),
            "prompt_ids": list(plugin.spec.prompt_ids),
            "config_schema_version": plugin.spec.config_schema_version,
            "config_hash": _stable_hash(config),
            "config_revision": context.config_revision,
            "codebook_revision": context.codebook_revision,
            "run_id": context.run_id,
            "worker_id": context.worker_id,
            "created_at": datetime.now(UTC).isoformat(),
            "review_status": "PROVISIONAL",
            "output": dict(result),
        }

    @staticmethod
    def _missing_capabilities(plugin: AnalysisPlugin | CorpusAnalysisPlugin, available: set[str]) -> set[str]:
        return set(plugin.spec.requires) - available

    def run_record(self, record: CanonicalRecord, context: PluginContext | None = None) -> PipelineResult:
        context = context or PluginContext()
        current, capabilities = self.preprocessor.process(record)
        original_identity = current.source_url
        failures: list[dict[str, Any]] = []

        for selection in self.selections:
            plugin = self.registry.get(selection.name)
            if plugin.spec.scope != "record":
                continue
            missing = self._missing_capabilities(plugin, capabilities)
            if missing:
                failure = {
                    "plugin": plugin.spec.name,
                    "status": "missing-capability",
                    "missing": sorted(missing),
                }
                current.analysis.plugin_failures[plugin.spec.name] = failure
                failures.append(failure)
                if self.fail_fast:
                    raise ValueError(
                        f"plugin {plugin.spec.name} missing capabilities: {', '.join(sorted(missing))}"
                    )
                continue
            try:
                result = plugin.process(current.model_copy(deep=True), context, selection.config)
                current.analysis.plugin_results[plugin.spec.name] = self._result_envelope(
                    plugin,
                    selection.config,
                    result,
                    context,
                    input_record_ids=[current.source_url],
                )
                capabilities.update(plugin.spec.produces)
                current.append_analysis_provenance(
                    method=f"plugin:{plugin.spec.name}",
                    model_version=plugin.spec.version,
                    metadata={
                        "plugin": plugin.spec.name,
                        "plugin_version": plugin.spec.version,
                        "method_id": plugin.spec.stable_method_id,
                        "method_version": plugin.spec.stable_method_version,
                        "interpretation_mode": plugin.spec.interpretation_mode,
                        "prompt_ids": list(plugin.spec.prompt_ids),
                        "config_hash": _stable_hash(selection.config),
                        "config_revision": context.config_revision,
                        "codebook_revision": context.codebook_revision,
                        "run_id": context.run_id,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - plugin failures are isolated by design
                failure = {
                    "plugin": plugin.spec.name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                current.analysis.plugin_failures[plugin.spec.name] = failure
                failures.append(failure)
                if self.fail_fast:
                    raise

            if current.source_url != original_identity:
                raise ValueError(f"plugin {plugin.spec.name} attempted to replace canonical source identity")

        result = self.postprocessor.process([current], sidecars={})
        result.failures.extend(failures)
        return result

    def run_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext | None = None,
    ) -> PipelineResult:
        context = context or PluginContext()
        processed: list[CanonicalRecord] = []
        failures: list[dict[str, Any]] = []

        record_selections = [
            item for item in self.selections if self.registry.get(item.name).spec.scope == "record"
        ]
        record_pipeline = AnalysisPipeline(
            self.registry,
            record_selections,
            preprocessor=self.preprocessor,
            postprocessor=self.postprocessor,
            fail_fast=self.fail_fast,
        )
        for record in records:
            item = record_pipeline.run_record(record, context)
            processed.extend(item.records)
            failures.extend(item.failures)

        sidecars: dict[str, Any] = {}
        available = {"canonical_record", "corpus"}
        for record in processed:
            available.update(self.preprocessor.capabilities(record))
            available.update(record.analysis.plugin_results.keys())

        for selection in self.selections:
            plugin = self.registry.get(selection.name)
            if plugin.spec.scope != "corpus":
                continue
            missing = self._missing_capabilities(plugin, available)
            if missing:
                failure = {
                    "plugin": plugin.spec.name,
                    "status": "missing-capability",
                    "missing": sorted(missing),
                }
                failures.append(failure)
                if self.fail_fast:
                    raise ValueError(
                        f"plugin {plugin.spec.name} missing capabilities: {', '.join(sorted(missing))}"
                    )
                continue
            try:
                output = plugin.process_corpus(
                    [record.model_copy(deep=True) for record in processed],
                    context,
                    selection.config,
                )
                sidecars[plugin.spec.name] = self._result_envelope(
                    plugin,
                    selection.config,
                    output,
                    context,
                    input_record_ids=[record.source_url for record in processed],
                )
                available.update(plugin.spec.produces)
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "plugin": plugin.spec.name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                failures.append(failure)
                if self.fail_fast:
                    raise

        final = self.postprocessor.process(processed, sidecars=sidecars)
        final.failures.extend(failures)
        return final


class LegacyLaclauPlugin:
    """Adapter making the existing canonical Laclau workflow a normal plugin.

    ``executor`` is intentionally injected so the core remains model/provider agnostic.
    Existing callers can wrap ``run_canonical_pipeline`` with their provider/context and
    return a CanonicalRecord; this adapter namespaces that analysis as plugin output.
    """

    spec = PluginSpec(
        name="laclau",
        version="1.0",
        method_id="laclau_discourse_analysis",
        method_version="1.0",
        interpretation_mode="theoretical_interpretive",
        scope="record",
        requires=frozenset({"text"}),
        produces=frozenset({"laclau"}),
        deterministic=False,
        prompt_ids=(
            "laclau.system:v1",
            "laclau.frame_analysis:v1",
            "laclau.summary_analysis:v1",
            "laclau.discourse_analysis:v1",
        ),
    )

    def __init__(self, executor: Callable[[CanonicalRecord, Mapping[str, Any]], CanonicalRecord]):
        self.executor = executor

    def process(
        self,
        record: CanonicalRecord,
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        analyzed = self.executor(record.model_copy(deep=True), config)
        return analyzed.analysis.model_dump(mode="json", exclude={"plugin_results", "plugin_failures"})
