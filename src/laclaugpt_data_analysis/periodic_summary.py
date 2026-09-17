"""Production-ready periodic discourse summaries over canonical analysis records.

Deterministic aggregation is authoritative. Optional LLM synthesis only turns
already-computed aggregates into researcher-facing prose. Previous summaries are
historical context, never source evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord
from .context_runtime import ContextItem
from .llm.structured_output import chat_structured
from .prompt_library import load_prompt, prompt_provenance
from .storage import RecordStore

SUMMARY_SCHEMA_VERSION = "periodic-summary-v2"
DEFAULT_INTERVAL = timedelta(hours=24)
REPORT_GENERATOR_VERSION = "2"


class SummaryScope(BaseModel):
    dimension: str = "overall"
    value: str = "all"

    @property
    def key(self) -> str:
        return "overall" if self.dimension == "overall" else f"{self.dimension}={self.value}"

    @classmethod
    def parse(cls, value: str | None) -> "SummaryScope":
        if not value or value.casefold() == "overall":
            return cls()
        if "=" not in value:
            raise ValueError("scope must be 'overall' or DIMENSION=VALUE")
        dimension, selected = value.split("=", 1)
        if not dimension.strip() or not selected.strip():
            raise ValueError("scope must include both dimension and value")
        return cls(dimension=dimension.strip(), value=selected.strip())


class PeriodicSummaryLimits(BaseModel):
    max_evidence_refs_per_metric: int = Field(default=50, ge=1, le=10_000)
    max_labels_per_family: int = Field(default=100, ge=1, le=100_000)
    max_relations: int = Field(default=250, ge=1, le=100_000)
    max_context_chars: int = Field(default=12_000, ge=500, le=100_000)
    max_narrative_chars: int = Field(default=20_000, ge=500, le=200_000)
    history_depth: int = Field(default=7, ge=1, le=30)
    minimum_prominence_count: int = Field(default=1, ge=1)
    minimum_prominence_document_frequency: int = Field(default=1, ge=1)


class TrendMetric(BaseModel):
    label: str
    count: int = 0
    document_frequency: int = 0
    normalized_frequency: float = 0.0
    delta: int | None = None
    distinct_authors: int = 0
    source_distribution: dict[str, int] = Field(default_factory=dict)
    formation_distribution: dict[str, int] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationMetric(BaseModel):
    relation_type: str
    source: str
    target: str
    count: int = 0
    delta: int | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class CoverageStatistics(BaseModel):
    record_count: int = 0
    records_considered: int = 0
    missing_timestamp: int = 0
    distinct_authors: int = 0
    source_distribution: dict[str, int] = Field(default_factory=dict)
    language_distribution: dict[str, int] = Field(default_factory=dict)
    failed_or_incomplete: int = 0


class PeriodicSummaryStatistics(BaseModel):
    coverage: CoverageStatistics = Field(default_factory=CoverageStatistics)
    signifiers: list[TrendMetric] = Field(default_factory=list)
    formations: list[TrendMetric] = Field(default_factory=list)
    us: list[TrendMetric] = Field(default_factory=list)
    them: list[TrendMetric] = Field(default_factory=list)
    frontiers: list[TrendMetric] = Field(default_factory=list)
    affects: list[TrendMetric] = Field(default_factory=list)
    topics: list[TrendMetric] = Field(default_factory=list)
    themes: list[TrendMetric] = Field(default_factory=list)
    relations: list[RelationMetric] = Field(default_factory=list)
    graph_degree: dict[str, int] = Field(default_factory=dict)
    graph_degree_delta: dict[str, int] = Field(default_factory=dict)
    change_categories: dict[str, list[str]] = Field(default_factory=dict)


class PeriodicDiscourseSummary(BaseModel):
    id: str
    schema_version: str = SUMMARY_SCHEMA_VERSION
    project_id: str
    scope: SummaryScope = Field(default_factory=SummaryScope)
    window_start: datetime
    window_end: datetime
    interval_seconds: int = 86_400
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_data_cutoff: datetime | None = None
    previous_summary_ids: list[str] = Field(default_factory=list)
    statistics: PeriodicSummaryStatistics = Field(default_factory=PeriodicSummaryStatistics)
    narrative: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude={"generated_at"})
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def context_payload(self, *, max_items: int = 10) -> dict[str, Any]:
        stats = self.statistics

        def top(items: list[TrendMetric]) -> list[dict[str, Any]]:
            return [
                {"label": item.label, "count": item.count, "df": item.document_frequency, "delta": item.delta}
                for item in items[:max_items]
            ]

        relation_changes = [
            {"type": item.relation_type, "source": item.source, "target": item.target, "delta": item.delta}
            for item in stats.relations
            if item.delta
        ][:max_items]
        return {
            "label": "historical situational context; not current-source evidence",
            "report_id": self.id,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "scope": self.scope.key,
            "top_signifiers": top(stats.signifiers),
            "top_formations": top(stats.formations),
            "top_frontiers": top(stats.frontiers),
            "top_topics": top(stats.topics),
            "major_changes": stats.change_categories,
            "relation_changes": relation_changes,
            "coverage": stats.coverage.model_dump(mode="json"),
            "narrative_excerpt": self.narrative[:2500],
        }

    def context_text(self, *, max_chars: int = 12_000) -> str:
        header = "HISTORICAL SUMMARY CONTEXT - NOT CURRENT-SOURCE EVIDENCE\n"
        payload = json.dumps(
            self.context_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (header + payload)[:max_chars]


class NarrativeProposal(BaseModel):
    markdown: str


class PeriodicSummaryRepository:
    """Persist summary payloads through the existing RecordStore abstraction."""

    def __init__(self, store: RecordStore):
        self.store = store

    @staticmethod
    def _encode(summary: PeriodicDiscourseSummary) -> dict[str, Any]:
        return {
            "id": summary.id,
            "project_id": summary.project_id,
            "scope_key": summary.scope.key,
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
            "payload_json": summary.model_dump_json(),
        }

    @staticmethod
    def _decode(row: dict[str, Any]) -> PeriodicDiscourseSummary | None:
        payload = row.get("payload_json")
        if not payload:
            return None
        try:
            return PeriodicDiscourseSummary.model_validate_json(str(payload))
        except Exception:
            return None

    def read(self) -> list[PeriodicDiscourseSummary]:
        return [item for row in self.store.read() if (item := self._decode(row)) is not None]

    def save(self, summary: PeriodicDiscourseSummary) -> None:
        existing = {item.id: item for item in self.read()}
        existing[summary.id] = summary
        self.store.write(self._encode(item) for item in existing.values())

    def latest(
        self,
        project_id: str,
        scope: SummaryScope | None = None,
        *,
        before: datetime | None = None,
    ) -> PeriodicDiscourseSummary | None:
        wanted = (scope or SummaryScope()).key
        candidates = [
            item
            for item in self.read()
            if item.project_id == project_id
            and item.scope.key == wanted
            and (before is None or item.window_end <= before)
        ]
        return max(candidates, key=lambda item: item.window_end, default=None)

    def history(
        self,
        project_id: str,
        scope: SummaryScope | None = None,
        *,
        before: datetime | None = None,
        limit: int = 7,
    ) -> list[PeriodicDiscourseSummary]:
        wanted = (scope or SummaryScope()).key
        items = [
            item
            for item in self.read()
            if item.project_id == project_id
            and item.scope.key == wanted
            and (before is None or item.window_end <= before)
        ]
        items.sort(key=lambda item: item.window_end, reverse=True)
        return items[: max(0, limit)]


def _ensure_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def record_timestamp(record: CanonicalRecord) -> datetime | None:
    value = record.source.created_at or record.source.collected_at
    return _ensure_aware(value) if value is not None else None


def floor_window(value: datetime, interval: timedelta = DEFAULT_INTERVAL) -> tuple[datetime, datetime]:
    value = _ensure_aware(value)
    seconds = int(interval.total_seconds())
    if seconds <= 0:
        raise ValueError("interval must be positive")
    epoch = int(value.timestamp())
    start_epoch = epoch - (epoch % seconds)
    start = datetime.fromtimestamp(start_epoch, tz=UTC)
    return start, start + interval


def latest_completed_window(
    now: datetime | None = None,
    interval: timedelta = DEFAULT_INTERVAL,
) -> tuple[datetime, datetime]:
    current_start, _ = floor_window(now or datetime.now(UTC), interval)
    return current_start - interval, current_start


def corpus_windows(
    records: Iterable[CanonicalRecord],
    interval: timedelta = DEFAULT_INTERVAL,
) -> list[tuple[datetime, datetime]]:
    timestamps = sorted(ts for record in records if (ts := record_timestamp(record)) is not None)
    if not timestamps:
        return []
    start, _ = floor_window(timestamps[0], interval)
    _, last_end = floor_window(timestamps[-1], interval)
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < last_end:
        windows.append((cursor, cursor + interval))
        cursor += interval
    return windows


def _labels(record: CanonicalRecord, field: str) -> list[Any]:
    return list(getattr(record.analysis, field, []) or [])


def _topic_items(record: CanonicalRecord) -> list[Any]:
    return list(getattr(record.analysis, "topics", []) or [])


def _item_label(item: Any) -> str:
    return str(getattr(item, "canonical_label", None) or getattr(item, "label", None) or "").strip()


def _topic_labels(record: CanonicalRecord) -> set[str]:
    return {label.casefold() for item in _topic_items(record) if (label := _item_label(item))}


def _metadata_value(record: CanonicalRecord, key: str) -> str:
    raw = record.source.raw_metadata
    mapping = {
        "source": record.source.platform,
        "platform": record.source.platform,
        "author": record.source.author or record.source.author_fullname,
        "actor": record.source.author or record.source.author_fullname,
        "arena": str(raw.get("arena") or ""),
        "language": record.content.language or record.source.language,
        "country": record.source.country,
        "region": str(raw.get("region") or ""),
        "document_type": record.source.source_type,
        "source_type": record.source.source_type,
    }
    return str(mapping.get(key, raw.get(key, "")) or "")


def record_matches_scope(record: CanonicalRecord, scope: SummaryScope) -> bool:
    if scope.dimension == "overall":
        return True
    wanted = scope.value.casefold()
    if scope.dimension == "signifier":
        return wanted in {_item_label(item).casefold() for item in _labels(record, "signifiers")}
    if scope.dimension == "formation":
        return wanted in {_item_label(item).casefold() for item in _labels(record, "formations")}
    if scope.dimension in {"topic", "theme"}:
        labels = _topic_labels(record) | {
            _item_label(item).casefold() for item in _labels(record, "themes")
        }
        return wanted in labels
    return wanted == _metadata_value(record, scope.dimension).casefold()


def _statistics_field(record_field: str) -> str:
    return "frontiers" if record_field == "frontier" else record_field


def _previous_counts(
    previous: PeriodicDiscourseSummary | None,
    record_field: str,
) -> dict[str, int]:
    if previous is None:
        return {}
    values = getattr(previous.statistics, _statistics_field(record_field), [])
    return {item.label: item.count for item in values}


def _previous_relation_counts(
    previous: PeriodicDiscourseSummary | None,
) -> dict[tuple[str, str, str], int]:
    if previous is None:
        return {}
    return {
        (item.relation_type, item.source, item.target): item.count
        for item in previous.statistics.relations
    }


def _bounded_append(
    mapping: dict[Any, list[str]],
    key: Any,
    values: Iterable[str],
    limit: int,
) -> None:
    bucket = mapping[key]
    if len(bucket) >= limit:
        return
    seen = set(bucket)
    for value in values:
        if len(bucket) >= limit:
            break
        if value and value not in seen:
            bucket.append(value)
            seen.add(value)


def _aggregate_records(
    records: Sequence[CanonicalRecord],
    previous: PeriodicDiscourseSummary | None,
    limits: PeriodicSummaryLimits,
) -> PeriodicSummaryStatistics:
    family_fields = {
        "signifiers": "signifiers",
        "formations": "formations",
        "us": "us",
        "them": "them",
        "frontiers": "frontier",
        "affects": "affects",
        "themes": "themes",
    }
    counts = {family: Counter() for family in family_fields}
    dfs = {family: Counter() for family in family_fields}
    authors = {family: defaultdict(set) for family in family_fields}
    sources = {family: defaultdict(Counter) for family in family_fields}
    formation_dist = {family: defaultdict(Counter) for family in family_fields}
    evidence = {family: defaultdict(list) for family in family_fields}
    role_meta = {family: defaultdict(set) for family in family_fields}
    topic_counts: Counter[str] = Counter()
    topic_df: Counter[str] = Counter()
    topic_evidence: dict[str, list[str]] = defaultdict(list)
    relation_counts: Counter[tuple[str, str, str]] = Counter()
    relation_evidence: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    degree: Counter[str] = Counter()
    source_distribution: Counter[str] = Counter()
    language_distribution: Counter[str] = Counter()
    all_authors: set[str] = set()
    failed = 0

    for record in records:
        source = record.source.platform or "unknown"
        language = record.content.language or record.source.language or "unknown"
        author = record.source.author or record.source.author_fullname
        source_distribution[source] += 1
        language_distribution[language] += 1
        if author:
            all_authors.add(author)
        if record.analysis.status != "analyzed":
            failed += 1
        record_formations = {
            _item_label(item)
            for item in _labels(record, "formations")
            if _item_label(item)
        }

        for family, field in family_fields.items():
            seen_labels: set[str] = set()
            for item in _labels(record, field):
                label = _item_label(item)
                if not label:
                    continue
                counts[family][label] += 1
                seen_labels.add(label)
                if author:
                    authors[family][label].add(author)
                sources[family][label][source] += 1
                for formation in record_formations:
                    formation_dist[family][label][formation] += 1
                refs = list(getattr(item, "evidence_ids", []) or []) or [record.source_url]
                _bounded_append(
                    evidence[family],
                    label,
                    refs,
                    limits.max_evidence_refs_per_metric,
                )
                if getattr(item, "kind", None):
                    role_meta[family][label].add(str(item.kind))
            for label in seen_labels:
                dfs[family][label] += 1

        seen_topics: set[str] = set()
        for item in _topic_items(record):
            label = _item_label(item)
            if not label:
                continue
            topic_counts[label] += 1
            seen_topics.add(label)
            _bounded_append(
                topic_evidence,
                label,
                [record.source_url],
                limits.max_evidence_refs_per_metric,
            )
        for label in seen_topics:
            topic_df[label] += 1

        for relation in record.analysis.relations:
            key = (relation.relation_type, relation.source_ref, relation.target_ref)
            relation_counts[key] += 1
            _bounded_append(
                relation_evidence,
                key,
                relation.evidence_ids or [record.source_url],
                limits.max_evidence_refs_per_metric,
            )
            degree[relation.source_ref] += 1
            degree[relation.target_ref] += 1

    total = max(1, len(records))
    stats = PeriodicSummaryStatistics(
        coverage=CoverageStatistics(
            record_count=len(records),
            distinct_authors=len(all_authors),
            source_distribution=dict(source_distribution),
            language_distribution=dict(language_distribution),
            failed_or_incomplete=failed,
        )
    )

    for family, field in family_fields.items():
        old = _previous_counts(previous, field)
        metrics: list[TrendMetric] = []
        for label, count in counts[family].most_common(limits.max_labels_per_family):
            metrics.append(
                TrendMetric(
                    label=label,
                    count=count,
                    document_frequency=dfs[family][label],
                    normalized_frequency=dfs[family][label] / total,
                    delta=count - old.get(label, 0) if previous is not None else None,
                    distinct_authors=len(authors[family][label]),
                    source_distribution=dict(sources[family][label]),
                    formation_distribution=dict(formation_dist[family][label]),
                    evidence_refs=evidence[family][label],
                    metadata={"candidate_roles": sorted(role_meta[family][label])},
                )
            )
        if previous is not None:
            present = counts[family]
            for label, old_count in old.items():
                if label not in present and len(metrics) < limits.max_labels_per_family:
                    metrics.append(TrendMetric(label=label, delta=-old_count))
        setattr(stats, family, metrics)

    old_topics = {item.label: item.count for item in (previous.statistics.topics if previous else [])}
    stats.topics = [
        TrendMetric(
            label=label,
            count=count,
            document_frequency=topic_df[label],
            normalized_frequency=topic_df[label] / total,
            delta=count - old_topics.get(label, 0) if previous else None,
            evidence_refs=topic_evidence[label],
        )
        for label, count in topic_counts.most_common(limits.max_labels_per_family)
    ]
    if previous:
        for label, old_count in old_topics.items():
            if label not in topic_counts and len(stats.topics) < limits.max_labels_per_family:
                stats.topics.append(TrendMetric(label=label, delta=-old_count))

    old_rel = _previous_relation_counts(previous)
    stats.relations = [
        RelationMetric(
            relation_type=key[0],
            source=key[1],
            target=key[2],
            count=count,
            delta=count - old_rel.get(key, 0) if previous else None,
            evidence_refs=relation_evidence[key],
        )
        for key, count in relation_counts.most_common(limits.max_relations)
    ]
    if previous:
        present = relation_counts
        for key, old_count in old_rel.items():
            if key not in present and len(stats.relations) < limits.max_relations:
                stats.relations.append(
                    RelationMetric(
                        relation_type=key[0],
                        source=key[1],
                        target=key[2],
                        delta=-old_count,
                    )
                )

    old_degree = previous.statistics.graph_degree if previous else {}
    stats.graph_degree = dict(degree)
    stats.graph_degree_delta = {
        node: value - old_degree.get(node, 0)
        for node, value in degree.items()
        if value - old_degree.get(node, 0)
    }
    if previous:
        for node, value in old_degree.items():
            if node not in degree and value:
                stats.graph_degree_delta[node] = -value
    stats.change_categories = _changes(stats)
    return stats


def _changes(statistics: PeriodicSummaryStatistics) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for family in (
        "signifiers",
        "formations",
        "us",
        "them",
        "frontiers",
        "affects",
        "topics",
        "themes",
    ):
        for item in getattr(statistics, family):
            if item.delta is None:
                continue
            if item.count == 0 and item.delta < 0:
                result["disappearing"].append(f"{family}:{item.label}")
            elif item.delta > 0 and item.count == item.delta:
                result["new"].append(f"{family}:{item.label}")
            elif item.delta > 0:
                result["increasing"].append(f"{family}:{item.label}")
            elif item.delta < 0:
                result["decreasing"].append(f"{family}:{item.label}")
            else:
                result["stable"].append(f"{family}:{item.label}")
    if any(item.delta for item in statistics.frontiers):
        result["frontier_shift"].append("frontier composition changed")
    return dict(result)


def _summary_id(
    project_id: str,
    scope: SummaryScope,
    start: datetime,
    end: datetime,
) -> str:
    payload = json.dumps(
        {
            "project": project_id,
            "scope": scope.key,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        sort_keys=True,
    )
    return "periodic:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _format_metric(items: list[TrendMetric], limit: int = 12) -> str:
    if not items:
        return "- (none supported in this window)"
    lines = []
    for item in items[:limit]:
        delta = "" if item.delta is None else f", delta {item.delta:+d}"
        lines.append(
            f"- **{item.label}**: {item.document_frequency} documents "
            f"({item.normalized_frequency:.1%}{delta})"
        )
    return "\n".join(lines)


def render_markdown(summary: PeriodicDiscourseSummary) -> str:
    stats = summary.statistics
    changed = []
    for category in ("new", "increasing", "decreasing", "disappearing", "frontier_shift"):
        values = stats.change_categories.get(category, [])
        if values:
            changed.append(f"- **{category}**: {', '.join(values[:10])}")
    relations = [
        f"- {item.relation_type}: **{item.source} -> {item.target}** "
        f"(n={item.count}{', delta ' + format(item.delta, '+d') if item.delta is not None else ''})"
        for item in stats.relations[:15]
    ] or ["- (none represented in canonical relation data)"]
    lines = [
        f"# Discourse and ideology summary - {summary.project_id} - {summary.window_start.date().isoformat()}",
        "",
        "## Executive summary",
        *(changed or ["- No comparison signal is available or the measured aggregates are stable."]),
        "",
        "## Emerging and declining signifiers",
        _format_metric(stats.signifiers),
        "",
        "## Formations",
        _format_metric(stats.formations),
        "",
        "## Topics / themes",
        _format_metric(stats.topics),
        _format_metric(stats.themes),
        "",
        "## Collective identities and political frontiers",
        "### Us",
        _format_metric(stats.us, 8),
        "### Them",
        _format_metric(stats.them, 8),
        "### Frontiers",
        _format_metric(stats.frontiers, 8),
        "",
        "## Affects",
        _format_metric(stats.affects, 8),
        "",
        "## Relations / articulations",
        *relations,
        "",
        "## Coverage",
        f"- Records: {stats.coverage.record_count}",
        f"- Failed/incomplete: {stats.coverage.failed_or_incomplete}",
        f"- Distinct authors: {stats.coverage.distinct_authors}",
        f"- Sources/platforms: {json.dumps(stats.coverage.source_distribution, ensure_ascii=False, sort_keys=True)}",
        f"- Languages: {json.dumps(stats.coverage.language_distribution, ensure_ascii=False, sort_keys=True)}",
        "",
        "## Comparison and safeguards",
        *(changed or ["- No compatible previous summary was supplied."]),
        "- Previous summaries are context only, not evidence for this period.",
        "- Frequency is not hegemony; co-occurrence is not articulation; community structure is not ideological formation.",
        "- Negative sentiment is not an antagonistic frontier; sentiment/emotion is not affective investment; topic is not discourse/frame/ideology by default.",
        "",
        "## Provenance",
        f"- Window: {summary.window_start.isoformat()} to {summary.window_end.isoformat()}",
        f"- Scope: {summary.scope.key}",
        f"- Previous summaries: {', '.join(summary.previous_summary_ids) or '(none)'}",
    ]
    return "\n".join(lines)


def build_periodic_summary(
    records: Iterable[CanonicalRecord],
    *,
    project_id: str,
    window_start: datetime,
    window_end: datetime,
    scope: SummaryScope | None = None,
    previous: PeriodicDiscourseSummary | None = None,
    history: Sequence[PeriodicDiscourseSummary] = (),
    revisions: dict[str, Any] | None = None,
    limits: PeriodicSummaryLimits | None = None,
) -> PeriodicDiscourseSummary:
    scope = scope or SummaryScope()
    limits = limits or PeriodicSummaryLimits()
    start, end = _ensure_aware(window_start), _ensure_aware(window_end)
    if end <= start:
        raise ValueError("window_end must be after window_start")
    considered = 0
    missing_timestamp = 0
    selected: list[CanonicalRecord] = []
    for record in records:
        considered += 1
        timestamp = record_timestamp(record)
        if timestamp is None:
            missing_timestamp += 1
            continue
        if start <= timestamp < end and record_matches_scope(record, scope):
            selected.append(record)
    statistics = _aggregate_records(selected, previous, limits)
    statistics.coverage.records_considered = considered
    statistics.coverage.missing_timestamp = missing_timestamp
    cutoff = max((record_timestamp(record) for record in selected), default=None)
    previous_ids: list[str] = []
    prior_items = ([previous] if previous else []) + list(history)
    for item in prior_items:
        if item and item.scope.key == scope.key and item.id not in previous_ids:
            previous_ids.append(item.id)
    previous_ids = previous_ids[: limits.history_depth]
    revision_payload = dict(revisions or {})
    generated_at = datetime.now(UTC)
    summary = PeriodicDiscourseSummary(
        id=_summary_id(project_id, scope, start, end),
        project_id=project_id,
        scope=scope,
        window_start=start,
        window_end=end,
        interval_seconds=int((end - start).total_seconds()),
        source_data_cutoff=cutoff,
        previous_summary_ids=previous_ids,
        statistics=statistics,
        evidence_refs=sorted({record.source_url for record in selected})[
            : limits.max_evidence_refs_per_metric * 10
        ],
        generated_at=generated_at,
        provenance={
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "report_generator_version": REPORT_GENERATOR_VERSION,
            "project": project_id,
            "scope": scope.key,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "source_data_cutoff": cutoff.isoformat() if cutoff else None,
            "records_considered": considered,
            "records_selected": len(selected),
            "previous_summary_ids": previous_ids,
            "revisions": revision_payload,
            "configuration_revision": revision_payload.get("configuration_revision")
            or revision_payload.get("config_revision"),
            "codebook_revision": revision_payload.get("codebook_revision"),
            "generated_at": generated_at.isoformat(),
            "limits": limits.model_dump(mode="json"),
            "previous_summary_context_only": bool(previous_ids),
        },
    )
    summary.narrative = render_markdown(summary)[: limits.max_narrative_chars]
    return summary


def grouped_summaries(
    records: Iterable[CanonicalRecord],
    *,
    project_id: str,
    window_start: datetime,
    window_end: datetime,
    group_by: Sequence[str] = (),
    previous: dict[str, PeriodicDiscourseSummary] | None = None,
    revisions: dict[str, Any] | None = None,
    limits: PeriodicSummaryLimits | None = None,
) -> list[PeriodicDiscourseSummary]:
    values = list(records)
    scopes = [SummaryScope()]
    for dimension in group_by:
        discovered: set[str] = set()
        for record in values:
            if dimension == "signifier":
                discovered.update(
                    _item_label(item)
                    for item in record.analysis.signifiers
                    if _item_label(item)
                )
            elif dimension == "formation":
                discovered.update(
                    _item_label(item)
                    for item in record.analysis.formations
                    if _item_label(item)
                )
            elif dimension in {"topic", "theme"}:
                discovered.update(
                    _item_label(item) for item in _topic_items(record) if _item_label(item)
                )
                discovered.update(
                    _item_label(item) for item in record.analysis.themes if _item_label(item)
                )
            else:
                value = _metadata_value(record, dimension)
                if value:
                    discovered.add(value)
        scopes.extend(
            SummaryScope(dimension=dimension, value=value) for value in sorted(discovered)
        )
    previous = previous or {}
    return [
        build_periodic_summary(
            values,
            project_id=project_id,
            window_start=window_start,
            window_end=window_end,
            scope=scope,
            previous=previous.get(scope.key),
            revisions=revisions,
            limits=limits,
        )
        for scope in scopes
    ]


def summary_context_item(
    summary: PeriodicDiscourseSummary,
    *,
    max_chars: int = 12_000,
) -> ContextItem:
    return ContextItem(
        kind="historical_summary_context",
        text=summary.context_text(max_chars=max_chars),
        source=summary.id,
        record_id=summary.id,
        trust="context_not_evidence",
        metadata={
            "sha256": summary.sha256,
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
            "scope": summary.scope.key,
        },
    )


def inject_summary_context(
    context: Any,
    summary: PeriodicDiscourseSummary,
    *,
    max_chars: int = 12_000,
) -> Any:
    provenance = {key: list(values) for key, values in getattr(context, "provenance", {}).items()}
    provenance.setdefault("periodic_summary_id", []).append(summary.id)
    provenance.setdefault("periodic_summary_sha256", []).append(summary.sha256)
    return context.model_copy(
        update={
            "situational_context": summary.context_text(max_chars=max_chars),
            "provenance": provenance,
        }
    )


def synthesize_narrative(
    summary: PeriodicDiscourseSummary,
    *,
    provider: Any,
    model: str,
    project_context: str = "",
    history: Sequence[PeriodicDiscourseSummary] = (),
    allow_cloud_fallback: bool | None = None,
    max_chars: int = 20_000,
) -> PeriodicDiscourseSummary:
    system_resource = load_prompt("laclau.system", version="v1")
    task_resource = load_prompt("periodic_summary.narrative", version="v1")
    rendered = task_resource.render(
        project_context=project_context or "(none supplied)",
        current_aggregates=json.dumps(
            summary.statistics.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ),
        previous_context=json.dumps(
            [
                {
                    "id": item.id,
                    "window_start": item.window_start.isoformat(),
                    "window_end": item.window_end.isoformat(),
                    "scope": item.scope.key,
                    "statistics": item.statistics.model_dump(mode="json"),
                }
                for item in history
            ],
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    proposal, response = chat_structured(
        provider,
        NarrativeProposal,
        model=model,
        system_prompt=system_resource.text,
        user_prompt=rendered.text,
        allow_cloud_fallback=allow_cloud_fallback,
    )
    prompt_meta = prompt_provenance(system_resource, task_resource, rendered=rendered)
    copy = summary.model_copy(deep=True)
    copy.narrative = (proposal.markdown.strip() or summary.narrative)[:max_chars]
    copy.provenance = {
        **copy.provenance,
        "narrative_model": response.provenance.to_dict(),
        **prompt_meta,
        "history_context_ids": [item.id for item in history],
    }
    return copy


def _load_jsonl(path: Path) -> list[CanonicalRecord]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(CanonicalRecord.model_validate_json(line))
    return records


def _load_summaries(path: Path) -> list[PeriodicDiscourseSummary]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                items.append(PeriodicDiscourseSummary.model_validate_json(line))
    return items


def _write_jsonl(path: Path, summaries: Sequence[PeriodicDiscourseSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {item.id: item for item in _load_summaries(path)}
    by_id.update({item.id: item for item in summaries})
    ordered = sorted(
        by_id.values(),
        key=lambda item: (item.project_id, item.scope.key, item.window_start),
    )
    path.write_text(
        "".join(item.model_dump_json() + "\n" for item in ordered),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate production periodic discourse summaries")
    parser.add_argument("--input", required=True, type=Path, help="Canonical-record JSONL")
    parser.add_argument("--output", required=True, type=Path, help="Summary JSONL")
    parser.add_argument("--project", required=True)
    parser.add_argument("--interval-hours", type=int, default=24)
    parser.add_argument("--start", "--from", dest="start")
    parser.add_argument("--end", "--to", dest="end")
    parser.add_argument("--all-windows", action="store_true")
    parser.add_argument("--group-by", action="append", default=[])
    parser.add_argument("--scope", help="overall or DIMENSION=VALUE")
    parser.add_argument("--history-depth", type=int, default=7)
    parser.add_argument("--max-labels", type=int, default=100)
    parser.add_argument("--max-evidence-refs", type=int, default=50)
    args = parser.parse_args(argv)

    records = _load_jsonl(args.input)
    interval = timedelta(hours=args.interval_hours)
    if interval.total_seconds() <= 0:
        parser.error("--interval-hours must be positive")
    limits = PeriodicSummaryLimits(
        history_depth=args.history_depth,
        max_labels_per_family=args.max_labels,
        max_evidence_refs_per_metric=args.max_evidence_refs,
    )
    try:
        requested_scope = SummaryScope.parse(args.scope)
    except ValueError as exc:
        parser.error(str(exc))
    if args.scope and args.group_by:
        parser.error("--scope and --group-by are mutually exclusive")
    if args.start or args.end:
        if not (args.start and args.end):
            parser.error("--start/--end must be supplied together")
        windows = [
            (
                _ensure_aware(datetime.fromisoformat(args.start)),
                _ensure_aware(datetime.fromisoformat(args.end)),
            )
        ]
    elif args.all_windows:
        windows = corpus_windows(records, interval)
    else:
        windows = [latest_completed_window(interval=interval)]

    existing = [item for item in _load_summaries(args.output) if item.project_id == args.project]
    generated_all: list[PeriodicDiscourseSummary] = []
    for start, end in windows:
        if args.scope:
            history = sorted(
                [
                    item
                    for item in existing + generated_all
                    if item.scope.key == requested_scope.key and item.window_end <= start
                ],
                key=lambda item: item.window_end,
                reverse=True,
            )[: limits.history_depth]
            previous = history[0] if history else None
            generated = [
                build_periodic_summary(
                    records,
                    project_id=args.project,
                    window_start=start,
                    window_end=end,
                    scope=requested_scope,
                    previous=previous,
                    history=history[1:],
                    limits=limits,
                )
            ]
        else:
            previous_by_scope: dict[str, PeriodicDiscourseSummary] = {}
            for item in existing + generated_all:
                if item.window_end <= start:
                    current = previous_by_scope.get(item.scope.key)
                    if current is None or item.window_end > current.window_end:
                        previous_by_scope[item.scope.key] = item
            generated = grouped_summaries(
                records,
                project_id=args.project,
                window_start=start,
                window_end=end,
                group_by=args.group_by,
                previous=previous_by_scope,
                limits=limits,
            )
        generated_all.extend(generated)
    _write_jsonl(args.output, generated_all)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
