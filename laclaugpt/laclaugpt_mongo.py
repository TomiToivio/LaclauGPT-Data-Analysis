"""MongoDB helpers for the minimal Phase 0 pipeline."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING, MongoClient

DEFAULT_PROJECT_ID = os.getenv("LACLAUGPT_PROJECT_ID", "ai26")


def _collection(project_id: str | None = None):
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("LACLAUGPT_MONGODB_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME") or os.getenv("LACLAUGPT_MONGODB_DATABASE")
    if not mongo_uri or not mongo_db_name:
        raise RuntimeError(
            "MongoDB configuration is required via MONGO_URI/MONGO_DB_NAME "
            "or LACLAUGPT_MONGODB_URI/LACLAUGPT_MONGODB_DATABASE"
        )
    client = MongoClient(mongo_uri)
    db = client[mongo_db_name]
    project = project_id or DEFAULT_PROJECT_ID
    return db[f"laclaugpt2_{project}_scraper_collection"]


def find_documents(
    *,
    limit: int = 100,
    document_id: str | None = None,
    retry_errors: bool = False,
    project_id: str | None = None,
):
    query: dict[str, Any] = {}
    if document_id:
        query["document_id"] = document_id
    elif retry_errors:
        query["$or"] = [
            {"phase0.preprocess.status": "error"},
            {"phase0.summary.status": "error"},
            {"phase0.postprocess.status": "error"},
            {"phase0.discourse.status": "error"},
        ]
    else:
        # Normal cron processing must not immediately retry documents that already
        # failed an earlier stage. Those records are handled only by --retry-errors.
        # Merely checking for a missing discourse status is insufficient because a
        # preprocess/summary/postprocess failure also leaves discourse absent.
        query.update(
            {
                "phase0.discourse.status": {"$exists": False},
                "phase0.preprocess.status": {"$ne": "error"},
                "phase0.summary.status": {"$ne": "error"},
                "phase0.postprocess.status": {"$ne": "error"},
            }
        )
    return list(_collection(project_id).find(query).sort("source_date", DESCENDING).limit(limit))


_PHASE0_DERIVED_FIELDS = (
    "phase0",
    "phase0_summary_raw",
    "phase0_summary",
    "phase0_summary_error_metadata",
    "phase0_summary_validated",
    "phase0_summary_validation_error",
    "phase0_discourse_raw",
    "phase0_discourse",
    "phase0_discourse_error_metadata",
    "phase0_ontology",
)


def upsert_document(
    source_url: str,
    fields: dict[str, Any],
    *,
    project_id: str | None = None,
    reset_phase0_on_content_change: bool = False,
) -> None:
    if not source_url:
        raise ValueError("source_url is required for Phase 0 upsert")

    collection = _collection(project_id)
    content_hash = fields.get("content_hash")
    existing = None
    if reset_phase0_on_content_change and content_hash:
        existing = collection.find_one({"source_url": source_url}, {"content_hash": 1})

    update: dict[str, Any] = {"$set": fields}
    existing_hash = existing.get("content_hash") if existing else None
    if (
        reset_phase0_on_content_change
        and existing_hash
        and content_hash
        and existing_hash != content_hash
    ):
        # The source URL is stable identity, but publishers can edit an article in
        # place. Any analysis derived from the old content must be invalidated so
        # the normal Phase 0 queue processes the revised text again.
        update["$unset"] = {field: "" for field in _PHASE0_DERIVED_FIELDS}

    collection.update_one({"source_url": source_url}, update, upsert=True)


def update_document(record: dict[str, Any], fields: dict[str, Any], *, project_id: str | None = None) -> None:
    source_url = record.get("source_url")
    if not source_url:
        raise ValueError("record has no source_url")
    upsert_document(str(source_url), fields, project_id=project_id)


def record_stage_failure(
    record: dict[str, Any],
    stage: str,
    error: str,
    *,
    extra_fields: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> None:
    """Persist a visible failure record and increment its attempt counter."""
    source_url = record.get("source_url")
    if not source_url:
        raise ValueError("record has no source_url")

    now = datetime.now(timezone.utc).isoformat()
    stage_prefix = f"phase0.{stage}"
    set_fields: dict[str, Any] = {
        f"{stage_prefix}.status": "error",
        f"{stage_prefix}.error": error,
        f"{stage_prefix}.updated_at": now,
        f"{stage_prefix}.last_failure_at": now,
    }
    if extra_fields:
        set_fields.update(extra_fields)

    _collection(project_id).update_one(
        {"source_url": str(source_url)},
        {
            "$set": set_fields,
            "$setOnInsert": {f"{stage_prefix}.first_failure_at": now},
            "$inc": {f"{stage_prefix}.attempt_count": 1},
        },
        upsert=True,
    )

    # Preserve first_failure_at on existing documents as well.
    _collection(project_id).update_one(
        {
            "source_url": str(source_url),
            f"{stage_prefix}.first_failure_at": {"$exists": False},
        },
        {"$set": {f"{stage_prefix}.first_failure_at": now}},
    )
