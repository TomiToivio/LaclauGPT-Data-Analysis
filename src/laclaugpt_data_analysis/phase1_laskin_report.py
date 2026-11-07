"""Mongo-backed periodic Phase 1 reports for the AI26 Laskin node."""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

from .canonical import CanonicalRecord
from .config import Settings, load_settings
from .periodic_summary import (
    PeriodicDiscourseSummary,
    grouped_summaries,
    latest_completed_window,
)
from .phase1_laskin_runtime import load_ai26_runtime_policy


def _mongo_client(settings: Settings):
    if not settings.mongo_url:
        raise ValueError("MongoDB is required for the AI26 Laskin periodic report")
    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("periodic Mongo reports require: pip install '.[remote]'") from exc
    return MongoClient(settings.mongo_url)


def _decode_result(document: dict[str, Any]) -> CanonicalRecord | None:
    payload = document.get("result")
    if not isinstance(payload, dict):
        return None
    try:
        return CanonicalRecord.model_validate(payload)
    except Exception:
        return None


def _as_datetime(value: Any) -> datetime | None:
    """Parse a stored timestamp without pulling the whole record through pydantic."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _record_timestamp_from_document(document: Mapping[str, Any]) -> datetime | None:
    result = document.get("result")
    if not isinstance(result, Mapping):
        return None
    source = result.get("source")
    if not isinstance(source, Mapping):
        return None
    return _as_datetime(source.get("created_at")) or _as_datetime(source.get("collected_at"))


def load_analysis_records(
    settings: Settings,
    *,
    run_id: str,
    window: tuple[datetime, datetime] | None = None,
) -> list[CanonicalRecord]:
    """Load the run's analysis results, optionally only those inside a report window (#416).

    Without a window this reads and validates every result in the run, which is what made the periodic
    report grow past its 900 s ceiling: the cost is `CanonicalRecord.model_validate` per document, and
    the window filter that discarded most of them ran *after* validation.

    With a window it reads timestamps first — a projection of two fields, no validation — and validates
    only the records the summary can actually use. The timestamp used is the one the summary itself uses
    (`source.created_at`, falling back to `source.collected_at`), so the two cannot disagree.
    """
    client = _mongo_client(settings)
    collection = client[settings.mongo_database][
        settings.distributed_namespace.mongo_collection("analysis_results")
    ]
    scope = {"project_id": settings.project_id, "run_id": run_id}
    if window is None:
        cursor = collection.find(scope, {"result": 1, "_id": 0})
        return [record for document in cursor if (record := _decode_result(document)) is not None]

    start, end = window
    selected: list[Any] = []
    projection = {"result.source.created_at": 1, "result.source.collected_at": 1}
    for document in collection.find(scope, projection):
        timestamp = _record_timestamp_from_document(document)
        if timestamp is not None and start <= timestamp < end:
            selected.append(document["_id"])
    if not selected:
        return []
    cursor = collection.find({"_id": {"$in": selected}}, {"result": 1, "_id": 0})
    return [record for document in cursor if (record := _decode_result(document)) is not None]


def _previous_by_scope(
    documents: Sequence[dict[str, Any]],
    *,
    project_id: str,
    run_id: str,
    before: datetime,
) -> dict[str, PeriodicDiscourseSummary]:
    previous: dict[str, PeriodicDiscourseSummary] = {}
    for document in documents:
        if document.get("project_id") != project_id or document.get("run_id") != run_id:
            continue
        payload = document.get("payload")
        if not isinstance(payload, dict):
            continue
        try:
            item = PeriodicDiscourseSummary.model_validate(payload)
        except Exception:
            continue
        if item.window_end > before:
            continue
        current = previous.get(item.scope.key)
        if current is None or item.window_end > current.window_end:
            previous[item.scope.key] = item
    return previous


#: How many stored summaries per scope the previous-window lookup may read with its
#: payload. One is enough in practice; the second keeps the lookup correct when the
#: newest stored payload for a scope can no longer be parsed back into a summary.
PREVIOUS_SUMMARIES_PER_SCOPE = 2


def load_previous_summary_documents(
    collection: Any,
    *,
    project_id: str,
    run_id: str,
    before: datetime,
    per_scope: int = PREVIOUS_SUMMARIES_PER_SCOPE,
) -> list[dict[str, Any]]:
    """Load only the summaries that can be the previous window of some scope (#423).

    The report used to read *every* summary the run had ever produced and let
    ``_previous_by_scope`` keep the newest one per scope. On Laskin that was 136,218
    documents and 1.3 GB on 2026-11-06 — a read projected at ~5,100 s, so the report
    could no longer finish inside its 900 s ceiling and every cycle lost its report.

    The two fields the choice actually needs (``scope_key``, ``window_end``) are small,
    so they are scanned first and only the retained candidates are read again with
    their payload. The window-end comparison stays a parsed-datetime comparison here,
    exactly as ``_previous_by_scope`` does it, so stored string formats cannot change
    which window counts as previous.
    """
    scope = {"project_id": project_id, "run_id": run_id}
    candidates: dict[str, list[tuple[datetime, Any]]] = {}
    for document in collection.find(scope, {"scope_key": 1, "window_end": 1, "_id": 0}):
        scope_key = document.get("scope_key")
        raw_end = document.get("window_end")
        end = _as_datetime(raw_end)
        if not isinstance(scope_key, str) or end is None or end > before:
            continue
        bucket = candidates.setdefault(scope_key, [])
        bucket.append((end, raw_end))
        bucket.sort(key=lambda item: item[0], reverse=True)
        del bucket[per_scope:]
    if not candidates:
        return []
    ends = sorted({raw for bucket in candidates.values() for _, raw in bucket}, key=str)
    return list(
        collection.find(
            {**scope, "scope_key": {"$in": sorted(candidates)}, "window_end": {"$in": ends}},
            {"project_id": 1, "run_id": 1, "payload": 1, "_id": 0},
        )
    )


def generate_latest_reports(
    settings: Settings,
    *,
    run_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = load_ai26_runtime_policy()
    if settings.project_id != policy.study_id:
        raise ValueError(
            f"settings project_id={settings.project_id!r} does not match canonical {policy.study_id!r}"
        )
    if not policy.report_enabled:
        return {"status": "disabled", "generated": 0}

    interval = timedelta(hours=policy.report_interval_hours)
    window_start, window_end = latest_completed_window(now=now, interval=interval)
    records = load_analysis_records(
        settings, run_id=run_id, window=(window_start, window_end)
    )

    client = _mongo_client(settings)
    collection = client[settings.mongo_database][
        settings.distributed_namespace.mongo_collection("periodic_summaries")
    ]
    existing = load_previous_summary_documents(
        collection,
        project_id=settings.project_id,
        run_id=run_id,
        before=window_start,
    )
    previous = _previous_by_scope(
        existing,
        project_id=settings.project_id,
        run_id=run_id,
        before=window_start,
    )

    revisions = {
        "configuration_revision": policy.config_revision,
        "codebook_revision": policy.codebook_revision,
        "run_id": run_id,
        "machine_profile": os.environ.get("LACLAUGPT_MACHINE", "laskin"),
    }
    summaries = grouped_summaries(
        records,
        project_id=settings.project_id,
        window_start=window_start,
        window_end=window_end,
        group_by=policy.report_group_by,
        previous=previous,
        revisions=revisions,
    )

    for summary in summaries:
        document = {
            "report_id": summary.id,
            "project_id": settings.project_id,
            "run_id": run_id,
            "scope_key": summary.scope.key,
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
            "payload": summary.model_dump(mode="json"),
            "sha256": summary.sha256,
            "generated_at": datetime.now(UTC).isoformat(),
            "provenance": {
                **policy.provenance(),
                "run_id": run_id,
                "machine_profile": revisions["machine_profile"],
            },
        }
        collection.update_one(
            {
                "project_id": settings.project_id,
                "run_id": run_id,
                "report_id": summary.id,
            },
            {"$set": document},
            upsert=True,
        )

    collection.create_index(
        [("project_id", 1), ("run_id", 1), ("report_id", 1)],
        unique=True,
        name="periodic_report_identity",
    )
    collection.create_index(
        [("project_id", 1), ("run_id", 1), ("scope_key", 1), ("window_end", -1)],
        name="periodic_report_scope_window",
    )
    return {
        "status": "ok",
        "generated": len(summaries),
        "records_considered": len(records),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "group_by": list(policy.report_group_by),
        "config_revision": policy.config_revision,
        "codebook_revision": policy.codebook_revision,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the latest AI26 Phase 1 Laskin report")
    parser.add_argument("--run-id", default=os.environ.get("LACLAUGPT_RUN_ID", ""))
    args = parser.parse_args(argv)
    if not args.run_id:
        parser.error("--run-id or LACLAUGPT_RUN_ID is required")
    report = generate_latest_reports(load_settings(), run_id=args.run_id)
    print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
