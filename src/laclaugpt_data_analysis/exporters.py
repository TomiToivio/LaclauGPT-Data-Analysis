"""Deterministic serializers for canonical analysis records and researcher bundles."""
from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from pathlib import Path

from .canonical import CanonicalRecord
from .interchange import write_csv, write_jsonl
from .multimodal.evidence import MultimodalEvidenceBundle
from .research_record import ensure_research_layers


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


def _safe_report_name(source_url: str, index: int) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", source_url).strip("_")
    return f"{index:06d}_{slug[:120] or 'record'}.md"


def write_human_reports(
    records: Iterable[CanonicalRecord],
    directory: str | Path,
) -> list[Path]:
    """Write one complete human-readable Markdown report per canonical record."""
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, record in enumerate(records, start=1):
        ensure_research_layers(record)
        path = destination / _safe_report_name(record.source_url, index)
        path.write_text(record.human_readable.markdown, encoding="utf-8")
        written.append(path)
    return written


def write_research_bundle(
    records: Iterable[CanonicalRecord],
    output_root: str | Path,
    *,
    stem: str = "analysis",
) -> dict[str, Path | list[Path]]:
    """Emit canonical JSONL, wide legacy-compatible CSV and Markdown reports together.

    Materializing once is intentional: every representation is generated from the same
    synchronized record objects, preventing the CSV/dashboard view from drifting away
    from the canonical JSON/DB representation.
    """
    items = [ensure_research_layers(record) for record in records]
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    jsonl_path = root / f"{stem}.jsonl"
    csv_path = root / f"{stem}_researchers.csv"
    reports_dir = root / f"{stem}_reports"
    write_jsonl(jsonl_path, items)
    write_csv(csv_path, items)
    reports = write_human_reports(items, reports_dir)
    return {
        "jsonl": jsonl_path,
        "csv": csv_path,
        "reports": reports,
    }
