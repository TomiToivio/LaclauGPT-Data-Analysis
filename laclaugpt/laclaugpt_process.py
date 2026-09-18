"""Simple CLI orchestrator for the Phase 0 MongoDB RSS/text pipeline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from laclaugpt_discourse import analyze_discourse
from laclaugpt_mongo import find_documents, update_document
from laclaugpt_postprocess import validate_summary
from laclaugpt_preprocess import preprocess_record
from laclaugpt_summary import summarize_record

STAGES = ("preprocess", "summary", "postprocess", "discourse")


def _status(status: str, error: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if error:
        value["error"] = error
    return value


def run_document(source: dict[str, Any], stage: str = "all", dry_run: bool = False) -> None:
    working = dict(source)

    if stage in ("all", "preprocess"):
        try:
            processed = preprocess_record(working)
            working.update(processed)
            if not dry_run:
                update_document(source, {
                    "document_id": processed["document_id"],
                    "normalized_text": processed["normalized_text"],
                    "content_hash": processed["content_hash"],
                    "metadata": processed["metadata"],
                    "phase0.preprocess": processed["phase0"]["preprocess"],
                })
        except Exception as exc:
            if not dry_run:
                update_document(source, {"phase0.preprocess": _status("error", str(exc))})
            return

    if not working.get("normalized_text"):
        existing = source.get("normalized_text")
        if existing:
            working["normalized_text"] = existing
            working["document_id"] = source.get("document_id")
            working["metadata"] = source.get("metadata") or {}
        else:
            return

    summary_data = source.get("phase0_summary")
    if stage in ("all", "summary"):
        try:
            raw, summary_data = summarize_record(working, working["normalized_text"])
            if not dry_run:
                update_document(source, {
                    "phase0_summary_raw": raw,
                    "phase0_summary": summary_data,
                    "phase0.summary": _status("ok"),
                })
        except Exception as exc:
            if not dry_run:
                update_document(source, {"phase0.summary": _status("error", str(exc))})
            return

    if stage in ("all", "postprocess"):
        try:
            if not summary_data:
                summary_data = source.get("phase0_summary") or {}
            validated = validate_summary(working, summary_data).model_dump()
            if not dry_run:
                update_document(source, {
                    "phase0_summary_validated": validated,
                    "phase0.postprocess": _status("ok"),
                })
        except Exception as exc:
            if not dry_run:
                update_document(source, {
                    "phase0_summary_validation_error": str(exc),
                    "phase0.postprocess": _status("error", str(exc)),
                })
            return

    if stage in ("all", "discourse"):
        try:
            if not summary_data:
                summary_data = source.get("phase0_summary") or {}
            raw, discourse = analyze_discourse(working, working["normalized_text"], summary_data)
            if not dry_run:
                update_document(source, {
                    "phase0_discourse_raw": raw,
                    "phase0_discourse": discourse,
                    "phase0.discourse": _status("ok"),
                })
        except Exception as exc:
            if not dry_run:
                update_document(source, {"phase0.discourse": _status("error", str(exc))})


def main() -> None:
    parser = argparse.ArgumentParser(description="LaclauGPT Phase 0 RSS/text processor")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--project", default="ai26")
    parser.add_argument("--document-id")
    parser.add_argument("--stage", choices=(*STAGES, "all"), default="all")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for source in find_documents(limit=args.limit, document_id=args.document_id, retry_errors=args.retry_errors):
        run_document(source, stage=args.stage, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
