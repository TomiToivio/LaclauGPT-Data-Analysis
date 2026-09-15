from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import SCHEMA_VERSION, CanonicalRecord


class UnsupportedSchemaVersion(ValueError):
    pass


def normalize_schema_version(payload: Mapping[str, Any]) -> CanonicalRecord:
    data = dict(payload)
    version = str(data.get("schema_version") or "")
    if version == "1.0":
        data["schema_version"] = SCHEMA_VERSION
    elif version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"unsupported schema version {version!r}; expected {SCHEMA_VERSION!r}"
        )
    return CanonicalRecord.model_validate(data)
