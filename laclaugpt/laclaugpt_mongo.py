"""MongoDB helpers for the minimal Phase 0 pipeline."""
from __future__ import annotations

import os
from typing import Any

from pymongo import DESCENDING, MongoClient

DEFAULT_PROJECT_ID = os.getenv("LACLAUGPT_PROJECT_ID", "ai26")


def _collection(project_id: str | None = None):
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME")
    if not mongo_uri or not mongo_db_name:
        raise RuntimeError("MONGO_URI and MONGO_DB_NAME are required")
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
