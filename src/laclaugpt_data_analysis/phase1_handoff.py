"""Versioned, public-safe Analysis to Visualization handoff for Phase 1."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .canonical import CanonicalRecord
from .canonical_pipeline import build_discourse_graph


HANDOFF_SCHEMA = "laclaugpt-analysis-visualization-v1"


def visualization_handoff(record: CanonicalRecord) -> dict[str, Any]:
    """Project only canonical/public-safe analytical fields.

    Phase 0 raw payloads and the legacy namespace are intentionally excluded.
    """
    canonical = record.canonical_dict()
    return {
        "handoff_schema": HANDOFF_SCHEMA,
        "schema_version": record.schema_version,
        "source_url": record.source_url,
        "source_native_ids": canonical["source_native_ids"],
        "source": canonical["source"],
        "content": canonical["content"],
        "evidence": canonical["evidence"],
        "analysis": canonical["analysis"],
        "human_readable": canonical["human_readable"],
        "provenance": canonical["provenance"],
        "review": canonical["review"],
        "graph": build_discourse_graph(record),
    }


def write_visualization_jsonl(
    path: str | Path,
    records: Iterable[CanonicalRecord],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    visualization_handoff(record),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
