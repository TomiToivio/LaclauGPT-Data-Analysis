"""Periodic discourse/ideology summaries over canonical analysis records.

The module is deliberately storage- and provider-neutral. Deterministic aggregation is
always authoritative; optional LLM synthesis only turns already-computed aggregates into
researcher-readable prose. Previous summaries are contextual memory, never source evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord
from .context_runtime import ContextItem
from .llm.structured_output import chat_structured
from .prompt_library import load_prompt, prompt_provenance
from .storage import RecordStore

SUMMARY_SCHEMA_VERSION = "periodic-summary-v1"
DEFAULT_INTERVAL = timedelta(hours=24)


class SummaryScope(BaseModel):
    """Project-wide or one metadata/category slice."""

    dimension: str = "overall"
    value: str = "all"

    @property
    def key(self) -> str:
        return "overall" if self.dimension == "overall" else f"{self.dimension}={self.value}"


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

    def context_text(self, *, max_chars: int = 12_000) -> str:
        """Bounded context for later analysis. It is explicitly not current evidence."""
        header = (
            "HISTORICAL SUMMARY CONTEXT — NOT CURRENT-SOURCE EVIDENCE\n"
            f"summary_id={self.id}\nproject={self.project_id}\nscope={self.scope.key}\n"
            f"window={self.window_start.isoformat()}..{self.window_end.isoformat()}\n"
        )
        return (header + self.narrative.strip())[:max_chars]


class NarrativeProposal(BaseModel):
    markdown: str


class PeriodicSummaryRepository:
    """Persist summary payloads through the repository's existing RecordStore port."""

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
    now: datetime | None = None, interval: timedelta = DEFAULT_INTERVAL
) -> tuple[datetime, datetime]:
    current_start, _ = floor_window(now or datetime.now(UTC), interval)
    return current_start - interval, current_start


def corpus_windows(
    records: Iterable[CanonicalRecord], interval: timedelta = DEFAULT_INTERVAL
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


def _topic_labels(record: CanonicalRecord) -> set[str]:
    values = set()
    for item in record.analysis.topics:
        label = getattr(item, "canonical_label", None) or getattr(item, "label", None)
        if label:
            values.add(str(label).casefold())
    return values


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
        return wanted in {item.label.casefold() for item in _labels(record, "signifiers")}
    if scope.dimension == "formation":
        return wanted in {item.label.casefold() for item in _labels(record, "formations")}
    if scope.dimension in {"topic", "theme"}:
        labels = _topic_labels(record) | {item.label.casefold() for item in _labels(record, "themes")}
        return wanted in labels
    return wanted == _metadata_value(record, scope.dimension).casefold()


def _previous_counts(previous: PeriodicDiscourseSummary | None, field: str) -> dict[str, int]:
    if previous is None:
        return {}
    return {item.label: item.count for item in getattr(previous.statistics, field)}


def _trend_metrics(
    records: Sequence[CanonicalRecord],
    field: str,
    previous: PeriodicDiscourseSummary | None,
) -> list[TrendMetric]:
    counts: Counter[str] = Counter()
    authors: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, Counter[str]] = defaultdict(Counter)
    formation_dist: dict[str, Counter[str]] = defaultdict(Counter)
    evidence: dict[str, set[str]] = defaultdict(set)
    role_meta: dict[str, set[str]] = defaultdict(set)
    for record in records:
        formations = {item.label for item in _labels(record, "formations")}
        seen: set[str] = set()
        for item in _labels(record, field):
            label = item.label
            counts[label] += 1
            seen.add(label)
            author = record.source.author or record.source.author_fullname
            if author:
                authors[label].add(author)
            if record.source.platform:
                sources[label][record.source.platform] += 1
            for formation in formations:
                formation_dist[label][formation] += 1
            refs = list(getattr(item, "evidence_ids", []) or [])
            evidence[label].update(refs or [record.source_url])
            if getattr(item, "kind", None):
                role_meta[label].add(str(item.kind))
        # document frequency is represented by one count per record below when labels repeat
        for label in seen:
            pass
    previous_counts = _previous_counts(previous, field)
    total = max(1, len(records))
    result = []
    for label, count in counts.most_common():
        doc_frequency = sum(
            1 for record in records if label in {item.label for item in _labels(record, field)}
        )
        result.append(
            TrendMetric(
                label=label,
                count=count,
                document_frequency=doc_frequency,
                normalized_frequency=doc_frequency / total,
                delta=count - previous_counts.get(label, 0) if previous is not None else None,
                distinct_authors=len(authors[label]),
                source_distribution=dict(sources[label]),
                formation_distribution=dict(formation_dist[label]),
                evidence_refs=sorted(evidence[label])[:50],
                metadata={"candidate_roles": sorted(role_meta[label])},
            )
        )
    if previous is not None:
        current = set(counts)
        for label, old_count in previous_counts.items():
            if label not in current:
                result.append(TrendMetric(label=label, delta=-old_count))
    return result


def _relation_metrics(
    records: Sequence[CanonicalRecord], previous: PeriodicDiscourseSummary | None
) -> tuple[list[RelationMetric], dict[str, int], dict[str, int]]:
    counts: Counter[tuple[str, str, str]] = Counter()
    evidence: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    degree: Counter[str] = Counter()
    for record in records:
        for relation in record.analysis.relations:
            key = (relation.relation_type, relation.source_ref, relation.target_ref)
            counts[key] += 1
            evidence[key].update(relation.evidence_ids or [record.source_url])
            degree[relation.source_ref] += 1
            degree[relation.target_ref] += 1
    old = {}
    old_degree: dict[str, int] = {}
    if previous is not None:
        old = {
            (item.relation_type, item.source, item.target): item.count
            for item in previous.statistics.relations
        }
        old_degree = previous.statistics.graph_degree
    metrics = [
        RelationMetric(
            relation_type=key[0],
            source=key[1],
            target=key[2],
            count=count,
            delta=count - old.get(key, 0) if previous is not None else None,
            evidence_refs=sorted(evidence[key])[:50],
        )
        for key, count in counts.most_common()
    ]
    if previous is not None:
        for key, count in old.items():
            if key not in counts:
                metrics.append(
                    RelationMetric(
                        relation_type=key[0], source=key[1], target=key[2], delta=-count
                    )
                )
    degree_delta = {
        node: value - old_degree.get(node, 0)
        for node, value in degree.items()
        if value - old_degree.get(node, 0)
    }
    for node, value in old_degree.items():
        if node not in degree and value:
            degree_delta[node] = -value
    return metrics, dict(degree), degree_delta


def _changes(statistics: PeriodicSummaryStatistics) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for family in ("signifiers", "formations", "us", "them", "frontiers"):
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
    revisions: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "schema": SUMMARY_SCHEMA_VERSION,
            "project": project_id,
            "scope": scope.key,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "revisions": revisions,
        },
        sort_keys=True,
        default=str,
    )
    return "periodic:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _format_metric(items: list[TrendMetric], limit: int = 12) -> str:
    if not items:
        return "- (none supported in this window)"
    lines = []
    for item in items[:limit]:
        delta = "" if item.delta is None else f", Δ {item.delta:+d}"
        lines.append(
            f"- **{item.label}**: {item.document_frequency} documents ({item.normalized_frequency:.1%}{delta})"
        )
    return "\n".join(lines)


def render_markdown(summary: PeriodicDiscourseSummary) -> str:
    stats = summary.statistics
    changes = stats.change_categories
    changed = []
    for category in ("new", "increasing", "decreasing", "disappearing", "frontier_shift"):
        values = changes.get(category, [])
        if values:
            changed.append(f"- **{category}**: {', '.join(values[:10])}")
    return "\n".join(
        [
            f"# Discourse and ideology summary — {summary.project_id} — {summary.window_start.date().isoformat()}",
            "",
            "## Executive summary",
            *(changed or ["- No comparison signal is available or the measured aggregates are stable."]),
            "",
            "## Emerging and declining signifiers",
            _format_metric(stats.signifiers),
            "",
            "## Articulations and chains of equivalence/difference",
            *(
                [
                    f"- {item.relation_type}: **{item.source} → {item.target}** (n={item.count}, Δ {item.delta:+d})"
                    if item.delta is not None
                    else f"- {item.relation_type}: **{item.source} → {item.target}** (n={item.count})"
                    for item in stats.relations[:15]
                ]
                or ["- (none represented in canonical relation data)"]
            ),
            "",
            "## Discursive / ideological formations",
            _format_metric(stats.formations),
            "",
            "## Collective identities and political frontiers",
            "### Us",
            _format_metric(stats.us, 8),
            "### Them",
            _format_metric(stats.them, 8),
            "### Frontiers",
            _format_metric(stats.frontiers, 8),
            "",
            "## Affects and demands",
            _format_metric(stats.affects, 8),
            "",
            "## Imaginaries / projected futures",
            "- Use document-level imaginary candidates as provisional evidence; institutional stabilization requires corpus-level validation.",
            "",
            "## Actor, author and source shifts",
            f"- Distinct authors: {stats.coverage.distinct_authors}",
            f"- Sources/platforms: {json.dumps(stats.coverage.source_distribution, ensure_ascii=False, sort_keys=True)}",
            "",
            "## Comparison with previous period",
            *(changed or ["- No compatible previous summary was supplied."]),
            "",
            "## Uncertainty, contradictory evidence and items requiring human review",
            "- Frequency/centrality are descriptive signals, not evidence of hegemony.",
            "- Negative sentiment is not automatically antagonism; polysemy is not empty signification.",
            "- Formation and signifier roles remain provisional unless supported by the required corpus-level evidence.",
            "",
            "## Data coverage and provenance",
            f"- Records: {stats.coverage.record_count}",
            f"- Window: {summary.window_start.isoformat()} to {summary.window_end.isoformat()}",
            f"- Scope: {summary.scope.key}",
            f"- Previous summaries used as context only: {', '.join(summary.previous_summary_ids) or '(none)'}",
        ]
    )


def build_periodic_summary(
    records: Iterable[CanonicalRecord],
    *,
    project_id: str,
    window_start: datetime,
    window_end: datetime,
    scope: SummaryScope | None = None,
    previous: PeriodicDiscourseSummary | None = None,
    revisions: dict[str, Any] | None = None,
) -> PeriodicDiscourseSummary:
    scope = scope or SummaryScope()
    start, end = _ensure_aware(window_start), _ensure_aware(window_end)
    if end <= start:
        raise ValueError("window_end must be after window_start")
    selected = [
        record
        for record in records
        if (timestamp := record_timestamp(record)) is not None
        and start <= timestamp < end
        and record_matches_scope(record, scope)
    ]
    source_distribution = Counter(record.source.platform or "unknown" for record in selected)
    language_distribution = Counter(
        record.content.language or record.source.language or "unknown" for record in selected
    )
    authors = {
        record.source.author or record.source.author_fullname
        for record in selected
        if record.source.author or record.source.author_fullname
    }
    statistics = PeriodicSummaryStatistics(
        coverage=CoverageStatistics(
            record_count=len(selected),
            distinct_authors=len(authors),
            source_distribution=dict(source_distribution),
            language_distribution=dict(language_distribution),
            failed_or_incomplete=sum(1 for record in selected if record.analysis.status != "analyzed"),
        ),
        signifiers=_trend_metrics(selected, "signifiers", previous),
        formations=_trend_metrics(selected, "formations", previous),
        us=_trend_metrics(selected, "us", previous),
        them=_trend_metrics(selected, "them", previous),
        frontiers=_trend_metrics(selected, "frontier", previous),
        affects=_trend_metrics(selected, "affects", previous),
    )
    relations, degree, degree_delta = _relation_metrics(selected, previous)
    statistics.relations = relations
    statistics.graph_degree = degree
    statistics.graph_degree_delta = degree_delta
    statistics.change_categories = _changes(statistics)
    cutoff = max((record_timestamp(record) for record in selected), default=None)
    revision_payload = dict(revisions or {})
    summary = PeriodicDiscourseSummary(
        id=_summary_id(project_id, scope, start, end, revision_payload),
        project_id=project_id,
        scope=scope,
        window_start=start,
        window_end=end,
        interval_seconds=int((end - start).total_seconds()),
        source_data_cutoff=cutoff,
        previous_summary_ids=[previous.id] if previous else [],
        statistics=statistics,
        evidence_refs=sorted({record.source_url for record in selected}),
        provenance={
            "aggregation": SUMMARY_SCHEMA_VERSION,
            "revisions": revision_payload,
            "source_record_count": len(selected),
            "previous_summary_context_only": bool(previous),
        },
    )
    summary.narrative = render_markdown(summary)
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
) -> list[PeriodicDiscourseSummary]:
    values = list(records)
    scopes = [SummaryScope()]
    for dimension in group_by:
        discovered: set[str] = set()
        if dimension == "signifier":
            discovered = {item.label for record in values for item in record.analysis.signifiers}
        elif dimension == "formation":
            discovered = {item.label for record in values for item in record.analysis.formations}
        elif dimension in {"topic", "theme"}:
            discovered = {
                *(label for record in values for label in _topic_labels(record)),
                *(item.label for record in values for item in record.analysis.themes),
            }
        else:
            discovered = {
                value
                for record in values
                if (value := _metadata_value(record, dimension))
            }
        scopes.extend(SummaryScope(dimension=dimension, value=value) for value in sorted(discovered))
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
        )
        for scope in scopes
    ]


def summary_context_item(summary: PeriodicDiscourseSummary) -> ContextItem:
    return ContextItem(
        kind="historical_summary_context",
        text=summary.context_text(),
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


def inject_summary_context(context: Any, summary: PeriodicDiscourseSummary) -> Any:
    """Inject summary into PipelineContext-like objects without creating global state."""
    provenance = {key: list(values) for key, values in getattr(context, "provenance", {}).items()}
    provenance.setdefault("periodic_summary_id", []).append(summary.id)
    provenance.setdefault("periodic_summary_sha256", []).append(summary.sha256)
    return context.model_copy(
        update={"situational_context": summary.context_text(), "provenance": provenance}
    )


def synthesize_narrative(
    summary: PeriodicDiscourseSummary,
    *,
    provider: Any,
    model: str,
    project_context: str = "",
    history: Sequence[PeriodicDiscourseSummary] = (),
    allow_cloud_fallback: bool | None = None,
) -> PeriodicDiscourseSummary:
    """Optional theory-guided prose synthesis over deterministic aggregates."""
    system_resource = load_prompt("laclau.system", version="v1")
    task_resource = load_prompt("periodic_summary.narrative", version="v1")
    rendered = task_resource.render(
        project_context=project_context or "(none supplied)",
        current_aggregates=json.dumps(
            summary.statistics.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        ),
        previous_context=json.dumps(
            [
                {
                    "id": item.id,
                    "window_start": item.window_start.isoformat(),
                    "window_end": item.window_end.isoformat(),
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
    copy.narrative = proposal.markdown.strip() or summary.narrative
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


def _write_jsonl(path: Path, summaries: Sequence[PeriodicDiscourseSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(item.model_dump_json() + "\n" for item in summaries), encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate periodic discourse summaries")
    parser.add_argument("--input", required=True, type=Path, help="Canonical-record JSONL")
    parser.add_argument("--output", required=True, type=Path, help="Summary JSONL")
    parser.add_argument("--project", required=True)
    parser.add_argument("--interval-hours", type=int, default=24)
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--all-windows", action="store_true")
    parser.add_argument("--group-by", action="append", default=[])
    args = parser.parse_args(argv)

    records = _load_jsonl(args.input)
    interval = timedelta(hours=args.interval_hours)
    if interval.total_seconds() <= 0:
        parser.error("--interval-hours must be positive")
    if args.start or args.end:
        if not (args.start and args.end):
            parser.error("--from and --to must be supplied together")
        windows = [(_ensure_aware(datetime.fromisoformat(args.start)), _ensure_aware(datetime.fromisoformat(args.end)))]
    elif args.all_windows:
        windows = corpus_windows(records, interval)
    else:
        windows = [latest_completed_window(interval=interval)]

    summaries: list[PeriodicDiscourseSummary] = []
    previous_by_scope: dict[str, PeriodicDiscourseSummary] = {}
    for start, end in windows:
        generated = grouped_summaries(
            records,
            project_id=args.project,
            window_start=start,
            window_end=end,
            group_by=args.group_by,
            previous=previous_by_scope,
        )
        summaries.extend(generated)
        previous_by_scope.update({item.scope.key: item for item in generated})
    _write_jsonl(args.output, summaries)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
