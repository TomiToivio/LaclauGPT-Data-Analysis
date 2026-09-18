"""AC/DT compatibility plugins.

These methods preserve the older exploratory workflow without promoting computational
signals to Laclaudian theoretical findings. Every plugin declares a stable method ID and
an interpretation mode that is emitted by :mod:`plugin_pipeline`.
"""
from __future__ import annotations

import random
import re
from collections import Counter
from datetime import datetime
from itertools import combinations
from typing import Any, Callable, Mapping, Sequence

from ..canonical import CanonicalRecord
from ..plugin_pipeline import PluginContext, PluginSpec

_TOKEN = re.compile(r"\b[^\W\d_][\w'’-]*\b", re.UNICODE)


def _record_id(record: CanonicalRecord) -> str:
    return record.source_url


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = value.strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _hashtags(record: CanonicalRecord) -> list[str]:
    values = record.source.raw_metadata.get("hashtags", [])
    if isinstance(values, str):
        values = [values]
    return sorted({str(value).strip().lstrip("#") for value in values or [] if str(value).strip()})


class WordFrequencyPlugin:
    spec = PluginSpec(
        name="acdt_word_frequency",
        phase=2, default_enabled=False, experimental=True,
        version="1.0",
        method_id="word_frequency",
        method_version="1.0",
        interpretation_mode="exploratory_instrumentalist",
        scope="corpus",
        requires=frozenset({"corpus", "text"}),
        produces=frozenset({"word_frequency"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        lowercase = bool(config.get("lowercase", True))
        min_count = int(config.get("min_count", 1))
        stopwords = {str(item).casefold() for item in config.get("stopwords", [])}
        counts: Counter[str] = Counter()
        evidence: dict[str, list[str]] = {}
        for record in records:
            seen: set[str] = set()
            for match in _TOKEN.finditer(record.content.text or ""):
                token = match.group(0)
                key = token.casefold() if lowercase else token
                if key.casefold() in stopwords:
                    continue
                counts[key] += 1
                seen.add(key)
            for token in seen:
                evidence.setdefault(token, []).append(_record_id(record))
        rows = [
            {"term": term, "count": count, "evidence_record_ids": evidence.get(term, [])}
            for term, count in counts.most_common()
            if count >= min_count
        ]
        return {"rows": rows, "semantic_status": "descriptive_pattern_only"}


class HashtagCooccurrencePlugin:
    spec = PluginSpec(
        name="acdt_hashtag_cooccurrence",
        phase=2, default_enabled=False, experimental=True,
        version="1.0",
        method_id="hashtag_cooccurrence",
        method_version="1.0",
        interpretation_mode="exploratory_instrumentalist",
        scope="corpus",
        requires=frozenset({"corpus", "metadata"}),
        produces=frozenset({"hashtag_network"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        min_edge_count = int(config.get("min_edge_count", 1))
        node_counts: Counter[str] = Counter()
        edge_counts: Counter[tuple[str, str]] = Counter()
        edge_evidence: dict[tuple[str, str], list[str]] = {}
        for record in records:
            tags = _hashtags(record)
            node_counts.update(tags)
            for a, b in combinations(tags, 2):
                edge = (a, b)
                edge_counts[edge] += 1
                edge_evidence.setdefault(edge, []).append(_record_id(record))
        return {
            "nodes": [{"id": tag, "count": count} for tag, count in node_counts.most_common()],
            "edges": [
                {
                    "source": a,
                    "target": b,
                    "count": count,
                    "evidence_record_ids": edge_evidence[(a, b)],
                    "relation": "cooccurrence_candidate",
                }
                for (a, b), count in edge_counts.most_common()
                if count >= min_edge_count
            ],
            "semantic_status": "cooccurrence_is_not_laclaudian_articulation",
        }


class TemporalPeakPlugin:
    """Daily count peaks with explicit legacy absolute-threshold compatibility."""

    spec = PluginSpec(
        name="acdt_peak_analysis",
        phase=2, default_enabled=False, experimental=True,
        version="1.0",
        method_id="peak_analysis",
        method_version="1.0",
        interpretation_mode="exploratory_instrumentalist",
        scope="corpus",
        requires=frozenset({"corpus", "metadata"}),
        produces=frozenset({"temporal_peaks"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        threshold = int(config.get("threshold_count", 40))
        group_hashtag = str(config.get("hashtag", "")).strip().lstrip("#")
        bins: dict[str, list[str]] = {}
        skipped: list[str] = []
        for record in records:
            if group_hashtag and group_hashtag not in _hashtags(record):
                continue
            parsed = _parse_datetime(record.source.created_at)
            if parsed is None:
                skipped.append(_record_id(record))
                continue
            day = parsed.date().isoformat()
            bins.setdefault(day, []).append(_record_id(record))
        series = [
            {"date": day, "count": len(record_ids), "record_ids": record_ids}
            for day, record_ids in sorted(bins.items())
        ]
        peaks = [item for item in series if item["count"] >= threshold]
        return {
            "bin": "day",
            "timezone_policy": "source_timestamp_offset",
            "threshold_rule": "absolute_count_gte",
            "threshold_count": threshold,
            "hashtag_filter": group_hashtag or None,
            "series": series,
            "peaks": peaks,
            "skipped_record_ids_without_parseable_time": skipped,
            "semantic_status": "peak_selects_material_for_interpretation",
        }


class CloseReadingSamplerPlugin:
    spec = PluginSpec(
        name="acdt_close_reading_sampler",
        phase=2, default_enabled=False, experimental=True,
        version="1.0",
        method_id="close_reading_sampler",
        method_version="1.0",
        interpretation_mode="exploratory_instrumentalist",
        scope="corpus",
        requires=frozenset({"corpus"}),
        produces=frozenset({"close_reading_sample"}),
        deterministic=True,
    )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        mode = str(config.get("mode", "random"))
        n = max(0, int(config.get("n", 20)))
        seed = int(config.get("seed", 0))
        selected: list[CanonicalRecord]
        if mode == "random":
            rng = random.Random(seed)
            selected = rng.sample(list(records), min(n, len(records)))
        elif mode == "actor":
            actor = str(config.get("actor", ""))
            selected = [record for record in records if record.source.author == actor][:n]
        elif mode in {"peak", "event", "topic", "outlier", "validation"}:
            wanted = {str(value) for value in config.get("record_ids", [])}
            selected = [record for record in records if _record_id(record) in wanted][:n or None]
        else:
            raise ValueError(f"unsupported close-reading sampling mode: {mode}")
        return {
            "mode": mode,
            "n_requested": n,
            "seed": seed if mode == "random" else None,
            "selection_criteria": dict(config),
            "record_ids": [_record_id(record) for record in selected],
            "samples": [
                {
                    "record_id": _record_id(record),
                    "author": record.source.author,
                    "created_at": record.source.created_at,
                    "text": record.content.text,
                }
                for record in selected
            ],
        }


class TopicModelAdapterPlugin:
    """Wrap an existing topic-model backend under the shared AC/DT result contract.

    The injected executor receives canonical records and plugin config. Topic outputs are
    explicitly exploratory by default and therefore cannot become frame/discourse/ideology
    codes merely by passing through this adapter.
    """

    def __init__(
        self,
        executor: Callable[[Sequence[CanonicalRecord], Mapping[str, Any]], Mapping[str, Any]],
        *,
        lda: bool = False,
        version: str = "1.0",
    ) -> None:
        self.executor = executor
        self.spec = PluginSpec(
            name="acdt_topic_model_lda" if lda else "acdt_topic_model_generic",
            phase=2, default_enabled=False, experimental=True,
            version=version,
            method_id="topic_model_lda" if lda else "topic_model_generic",
            method_version="1.0",
            interpretation_mode="exploratory_instrumentalist",
            scope="corpus",
            requires=frozenset({"corpus", "text"}),
            produces=frozenset({"topics"}),
            deterministic=False,
        )

    def process_corpus(
        self,
        records: Sequence[CanonicalRecord],
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context
        output = dict(self.executor(records, config))
        output.setdefault("semantic_status", "topic_is_not_frame_discourse_or_ideology")
        return output


class LegacyMeasurementPassThroughPlugin:
    """Expose imported legacy measurements without recomputing or reinterpreting them."""

    def __init__(self, *, method_id: str, field_names: Sequence[str], name: str | None = None) -> None:
        if method_id not in {"wordscores", "wordfish", "sentiment_analysis", "emotion_analysis", "emotion_intensity"}:
            raise ValueError(f"unsupported legacy measurement method: {method_id}")
        self.field_names = tuple(field_names)
        self.spec = PluginSpec(
            name=name or f"acdt_legacy_{method_id}",
            phase=2, default_enabled=False, experimental=True,
            version="1.0",
            method_id=method_id,
            method_version="legacy-import/1.0",
            interpretation_mode="measurement",
            scope="record",
            requires=frozenset({"canonical_record"}),
            produces=frozenset({method_id}),
            deterministic=True,
        )

    def process(
        self,
        record: CanonicalRecord,
        context: PluginContext,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del context, config
        original = record.legacy.get("original") if isinstance(record.legacy, dict) else None
        source = original if isinstance(original, dict) else {}
        values = {field: source.get(field) for field in self.field_names if field in source}
        return {
            "values": values,
            "recomputed": False,
            "validation_status": "imported_legacy_unknown_unless_separately_documented",
            "semantic_status": "measurement_not_theoretical_code",
        }


def first_party_acdt_plugins() -> tuple[object, ...]:
    """Deterministic first-party methods that require no optional NLP dependencies."""
    return (
        WordFrequencyPlugin(),
        HashtagCooccurrencePlugin(),
        TemporalPeakPlugin(),
        CloseReadingSamplerPlugin(),
    )
