"""MongoDB helpers for the minimal Phase 0 pipeline."""
from __future__ import annotations

import os
from typing import Any

from pymongo import MongoClient, DESCENDING

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
LACLAUGPT_PROJECT_ID = os.getenv("LACLAUGPT_PROJECT_ID", "ai26")


def _collection():
    if not MONGO_URI or not MONGO_DB_NAME:
        raise RuntimeError("MONGO_URI and MONGO_DB_NAME are required")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    return db[f"laclaugpt2_{LACLAUGPT_PROJECT_ID}_scraper_collection"]


def find_documents(*, limit: int = 100, document_id: str | None = None, retry_errors: bool = False):
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
    return list(_collection().find(query).sort("source_date", DESCENDING).limit(limit))


def upsert_document(source_url: str, fields: dict[str, Any]) -> None:
    if not source_url:
        raise ValueError("source_url is required for Phase 0 upsert")
    _collection().update_one({"source_url": source_url}, {"$set": fields}, upsert=True)


def update_document(record: dict[str, Any], fields: dict[str, Any]) -> None:
    source_url = record.get("source_url")
    if not source_url:
        raise ValueError("record has no source_url")
    upsert_document(str(source_url), fields)
