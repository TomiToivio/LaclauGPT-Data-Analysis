"""Researcher-facing aggregate reports for prompt context and dashboards."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime

from pydantic import BaseModel, Field

from .canonical import CanonicalRecord


class DailyReport(BaseModel):
    report_date: str
    title: str
    markdown: str
    record_count: int
    filters: dict[str, str] = Field(default_factory=dict)
    top_entities: list[str] = Field(default_factory=list)
    top_signifiers: list[str] = Field(default_factory=list)
    top_formations: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


def _record_date(record: CanonicalRecord) -> date | None:
    value = record.source.created_at or record.source.collected_at
    return value.date() if isinstance(value, datetime) else None


def _matches(record: CanonicalRecord, filters: dict[str, str]) -> bool:
    author = (record.source.author or record.source.author_fullname).casefold()
    signifiers = {x.label.casefold() for x in record.analysis.signifiers}
    formations = {x.label.casefold() for x in record.analysis.formations}
    for key, value in filters.items():
        wanted = value.casefold()
        if key == "author" and wanted not in author:
            return False
        if key == "signifier" and wanted not in signifiers:
            return False
        if key == "formation" and wanted not in formations:
            return False
        if key == "platform" and wanted != record.source.platform.casefold():
            return False
        if key == "country" and wanted != record.source.country.casefold():
            return False
    return True


def build_daily_report(
    records: Iterable[CanonicalRecord],
    *,
    report_date: date | None = None,
    filters: dict[str, str] | None = None,
) -> DailyReport:
    """Build a deterministic report suitable for dashboards and next-run context."""
    target = report_date or date.today()
    active_filters = filters or {}
    selected = [
        record
        for record in records
        if (_record_date(record) in {None, target}) and _matches(record, active_filters)
    ]
    entities = Counter(x.label for record in selected for x in record.analysis.entities)
    signifiers = Counter(x.label for record in selected for x in record.analysis.signifiers)
    formations = Counter(x.label for record in selected for x in record.analysis.formations)

    summaries = [
        record.human_readable.summary or record.analysis.summary or "" for record in selected
    ]
    summaries = [value.strip() for value in summaries if value and value.strip()]
    filter_text = ", ".join(
        f"{key}={value}" for key, value in active_filters.items()
    ) or "none"
    lines = [
        f"# LaclauGPT daily summary — {target.isoformat()}",
        "",
        f"Records: {len(selected)}",
        f"Filters: {filter_text}",
        "",
        "## Current corpus signals",
        f"Top entities: {', '.join(name for name, _ in entities.most_common(15)) or '(none)'}",
        f"Top signifiers: {', '.join(name for name, _ in signifiers.most_common(15)) or '(none)'}",
        f"Top formations: {', '.join(name for name, _ in formations.most_common(15)) or '(none)'}",
        "",
        "## Researcher-readable item summaries",
    ]
    lines.extend(f"- {summary}" for summary in summaries[:50])
    lines.extend(
        [
            "",
            "## Interpretation warning",
            "Counts and recurrence identify candidates for comparison. They do not by themselves establish hegemony, nodal status, empty signification, antagonism, affective investment, or an ideological formation.",
        ]
    )
    return DailyReport(
        report_date=target.isoformat(),
        title=f"LaclauGPT daily summary {target.isoformat()}",
        markdown="\n".join(lines),
        record_count=len(selected),
        filters=active_filters,
        top_entities=[name for name, _ in entities.most_common(15)],
        top_signifiers=[name for name, _ in signifiers.most_common(15)],
        top_formations=[name for name, _ in formations.most_common(15)],
        source_urls=[record.source_url for record in selected],
    )
