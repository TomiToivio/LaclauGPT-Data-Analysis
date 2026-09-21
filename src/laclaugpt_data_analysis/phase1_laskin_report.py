"""Mongo-backed periodic Phase 1 reports for the AI26 Laskin node."""
from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

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


def load_analysis_records(settings: Settings, *, run_id: str) -> list[CanonicalRecord]:
    client = _mongo_client(settings)
    collection = client[settings.mongo_database][
        settings.distributed_namespace.mongo_collection("analysis_results")
    ]
    cursor = collection.find(
        {"project_id": settings.project_id, "run_id": run_id},
        {"result": 1, "_id": 0},
    )
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
    records = load_analysis_records(settings, run_id=run_id)

    client = _mongo_client(settings)
    collection = client[settings.mongo_database][
        settings.distributed_namespace.mongo_collection("periodic_summaries")
    ]
    existing = list(
        collection.find(
            {"project_id": settings.project_id, "run_id": run_id},
            {"payload": 1, "project_id": 1, "run_id": 1, "_id": 0},
        )
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
