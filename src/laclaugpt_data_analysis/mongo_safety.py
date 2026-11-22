"""MongoDB update-boundary helpers.

MongoDB's _id is immutable. Reusing a mapping returned by a read or modified
by PyMongo's insert_one in a replacement/$set causes WriteError code 66.
Do not mutate the caller's payload; preserve nested domain fields.
"""
from __future__ import annotations

from typing import Any, Mapping


def strip_mongo_id(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new update document without the immutable top-level _id."""
    return {key: value for key, value in document.items() if key != "_id"}
