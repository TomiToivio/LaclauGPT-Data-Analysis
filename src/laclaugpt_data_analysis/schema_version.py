from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import (
    SCHEMA_VERSION,
    CanonicalRecord,
    HumanReadableSection,
    IntermediateSection,
    RawCaptureSection,
)


class UnsupportedSchemaVersion(ValueError):
    pass


def normalize_schema_version(payload: Mapping[str, Any]) -> CanonicalRecord:
    """Normalize supported historical records to the current four-layer contract."""
    data = dict(payload)
    version = str(data.get("schema_version") or "")
    if version in {"1.0", "1.0.0"}:
        source = dict(data.get("source") or {})
        content = dict(data.get("content") or {})
        raw_ref = source.get("raw_ref")
        data["schema_version"] = SCHEMA_VERSION
        data.setdefault(
            "raw_capture",
            RawCaptureSection(
                ref=str(raw_ref) if raw_ref else None,
                metadata={
                    "preservation": (
                        "legacy-durable-reference" if raw_ref else "compatibility-missing-original"
                    )
                },
            ).model_dump(mode="python"),
        )
        data.setdefault("intermediate", IntermediateSection().model_dump(mode="python"))
        preview = str(content.get("text") or "")
        data.setdefault(
            "human_readable",
            HumanReadableSection(
                summary=preview[:500],
                markdown=(
                    f"# Research record\n\n## Collected content\n{preview[:2000]}"
                    if preview
                    else "# Research record"
                ),
                generator="laclaugpt-data-analysis/schema-migration",
                sections={"content": preview[:2000]},
            ).model_dump(mode="python"),
        )
    elif version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            f"unsupported schema version {version!r}; expected {SCHEMA_VERSION!r}"
        )
    return CanonicalRecord.model_validate(data)
