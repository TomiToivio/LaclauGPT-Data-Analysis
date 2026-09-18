"""MongoDB helpers for the minimal Phase 0 pipeline."""
from __future__ import annotations

import os
from typing import Any

from pymongo import DESCENDING, MongoClient

DEFAULT_PROJECT_ID = os.getenv("LACLAUGPT_PROJECT_ID", "ai26")

# Phase 0 runs Collection and Analysis from one cron/CLI environment, so both must
# accept the same MongoDB configuration names. Collection's Settings use the
# LACLAUGPT_ namespace; the legacy Phase 0 core used the bare MONGO_ names. Accept
# both, with the legacy names winning for backward compatibility.
MONGO_URI_ENV_VARS = ("MONGO_URI", "LACLAUGPT_MONGODB_URI")
MONGO_DB_ENV_VARS = ("MONGO_DB_NAME", "LACLAUGPT_MONGODB_DATABASE")


def resolve_mongo_config() -> tuple[str, str]:
    """Return ``(uri, database)`` from either the legacy or Collection-style names.

    Raises RuntimeError naming both accepted pairs so a misconfigured cron job says
    what to set rather than failing obscurely.
    """
    uri = next((os.getenv(name) for name in MONGO_URI_ENV_VARS if os.getenv(name)), None)
    database = next((os.getenv(name) for name in MONGO_DB_ENV_VARS if os.getenv(name)), None)
    if not uri or not database:
        pairs = " or ".join(
            f"{u}/{d}" for u, d in zip(MONGO_URI_ENV_VARS, MONGO_DB_ENV_VARS)
        )
        raise RuntimeError(f"MongoDB configuration is required via {pairs}")
    return uri, database


def _collection(project_id: str | None = None):
    mongo_uri, mongo_db_name = resolve_mongo_config()
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
        query["$or"] = [
            {"phase0.discourse.status": {"$exists": False}},
            {"phase0.discourse.status": {"$ne": "ok"}},
        ]
    return list(_collection(project_id).find(query).sort("source_date", DESCENDING).limit(limit))


def upsert_document(source_url: str, fields: dict[str, Any], *, project_id: str | None = None) -> None:
    if not source_url:
        raise ValueError("source_url is required for Phase 0 upsert")
    _collection(project_id).update_one({"source_url": source_url}, {"$set": fields}, upsert=True)


def update_document(record: dict[str, Any], fields: dict[str, Any], *, project_id: str | None = None) -> None:
    source_url = record.get("source_url")
    if not source_url:
        raise ValueError("record has no source_url")
    upsert_document(str(source_url), fields, project_id=project_id)
