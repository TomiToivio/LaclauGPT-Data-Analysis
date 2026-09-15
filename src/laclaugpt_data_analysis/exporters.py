"""Deterministic serializers for canonical analysis records."""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from .multimodal.evidence import MultimodalEvidenceBundle


def write_multimodal_jsonl(records: Iterable[MultimodalEvidenceBundle], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for record in sorted(records, key=lambda item: item.document_id):
            handle.write(record.model_dump_json())
            handle.write("\n")


def write_multimodal_csv(records: Iterable[MultimodalEvidenceBundle], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "document_id",
        "source_uri",
        "transcript_segments",
        "ocr_observations",
        "visual_observations",
        "missing_modalities",
        "metadata_json",
    ]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in sorted(records, key=lambda item: item.document_id):
            writer.writerow(
                {
                    "document_id": record.document_id,
                    "source_uri": record.source_uri or "",
                    "transcript_segments": len(record.transcript),
                    "ocr_observations": len(record.ocr),
                    "visual_observations": len(record.visuals),
                    "missing_modalities": ",".join(sorted(set(record.missing_modalities))),
                    "metadata_json": json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                }
            )
