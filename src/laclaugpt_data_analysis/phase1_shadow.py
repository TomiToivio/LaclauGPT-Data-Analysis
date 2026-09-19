"""Read-only Phase 1 shadow bridge for stable Phase 0 Mongo-shaped records.

Nothing in this module mutates MongoDB or imports the Phase 0 queue/orchestrator.
It exists so Phase 1 can be exercised safely beside the stable Phase 0 runtime.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import CanonicalRecord
from .canonical_pipeline import preprocess_record
from .interchange import from_phase0_mongo_document, record_to_json


@dataclass(frozen=True)
class ShadowDiagnostic:
    index: int
    source_url: str | None
    document_id: str | None
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "source_url": self.source_url,
            "document_id": self.document_id,
            "error": self.error,
        }


def adapt_phase0_batch(
    documents: Iterable[Mapping[str, Any]],
) -> tuple[list[CanonicalRecord], list[ShadowDiagnostic]]:
    """Adapt a batch in input order and isolate malformed records."""
    records: list[CanonicalRecord] = []
    diagnostics: list[ShadowDiagnostic] = []
    for index, document in enumerate(documents):
        try:
            records.append(from_phase0_mongo_document(document))
        except Exception as exc:
            diagnostics.append(
                ShadowDiagnostic(
                    index=index,
                    source_url=str(document.get("source_url") or "") or None,
                    document_id=str(document.get("document_id") or "") or None,
                    error=str(exc),
                )
            )
    return records, diagnostics


def preprocess_shadow_record(record: CanonicalRecord) -> CanonicalRecord:
    """Run canonical preprocessing once, with no provider/LLM access."""
    if record.intermediate.stage_outputs.get("preprocess_contract"):
        return record
    return preprocess_record(record)


def preprocess_phase0_batch(
    documents: Iterable[Mapping[str, Any]],
) -> tuple[list[CanonicalRecord], list[ShadowDiagnostic]]:
    records, diagnostics = adapt_phase0_batch(documents)
    return [preprocess_shadow_record(record) for record in records], diagnostics


def export_phase0_shadow_jsonl(
    documents: Iterable[Mapping[str, Any]],
    destination: str | Path,
    *,
    run_preprocess: bool = False,
) -> list[ShadowDiagnostic]:
    """Write canonical JSONL without writing to MongoDB."""
    records, diagnostics = adapt_phase0_batch(documents)
    if run_preprocess:
        records = [preprocess_shadow_record(record) for record in records]

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record_to_json(record) + "\n")
    return diagnostics


def _read_phase0_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Phase 0 to canonical Phase 1 shadow export"
    )
    parser.add_argument("input", type=Path, help="JSONL containing copied Phase 0 documents")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/exports/phase0-canonical-shadow.jsonl"),
    )
    parser.add_argument(
        "--diagnostics",
        type=Path,
        default=Path("data/exports/phase0-canonical-shadow.diagnostics.jsonl"),
    )
    parser.add_argument(
        "--preprocess",
        action="store_true",
        help="Also run provider-free canonical preprocess_record once",
    )
    args = parser.parse_args()

    diagnostics = export_phase0_shadow_jsonl(
        _read_phase0_jsonl(args.input),
        args.output,
        run_preprocess=args.preprocess,
    )
    args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
    args.diagnostics.write_text(
        "".join(
            json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for item in diagnostics
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
