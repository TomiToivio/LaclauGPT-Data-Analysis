"""Privacy-safe EP24 legacy audit and old-vs-new comparison helpers.

The functions in this module operate on researcher-provided CSVs at runtime. They
never contain project rows themselves and are deliberately conservative: the audit
reports observable data-quality risks rather than pretending to decide whether a
political interpretation is substantively correct.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

COUNTRY_NAMES = {"finland": "Finland", "poland": "Poland"}
ID_FIELDS = ("new_id", "video_id", "old_id", "video_filename", "allas_filename")
STRATA_FIELDS = ("source_type", "author_username", "political_preference")
EVIDENCE_FIELDS = (
    "whisper_transcript",
    "whisper_translated",
    "ocr_1",
    "frame_1",
    "summary_analysis",
)
INTERPRETIVE_FIELDS = (
    "entities",
    "topics",
    "political_themes",
    "formula_of_populism_analysis",
    "us",
    "them",
)


def _clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"nan", "none", "nat"} else text


def _stable_id(row: dict[str, str], row_number: int) -> str:
    for field in ID_FIELDS:
        value = _clean(row.get(field))
        if value:
            return value
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"row-{row_number}-{digest}"


def load_country_rows(path: str | Path, country: str) -> tuple[list[dict[str, str]], list[str]]:
    expected = COUNTRY_NAMES[country]
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader if _clean(row.get("country")) == expected]
    return rows, fields


def audit_legacy_csv(path: str | Path, country: str) -> dict[str, Any]:
    rows, fields = load_country_rows(path, country)
    ids = [_stable_id(row, i + 2) for i, row in enumerate(rows)]
    counts = Counter(ids)
    duplicate_ids = sorted(key for key, count in counts.items() if count > 1)

    missingness = {
        field: sum(not _clean(row.get(field)) for row in rows)
        for field in (*EVIDENCE_FIELDS, *INTERPRETIVE_FIELDS, "allas_filename")
        if field in fields
    }
    language = Counter(_clean(row.get("whisper_language")) or "missing" for row in rows)
    source_types = Counter(_clean(row.get("source_type")) or "missing" for row in rows)
    authors = Counter(_clean(row.get("author_username")) or "missing" for row in rows)

    potential_metadata_leakage = sum(
        bool(_clean(row.get("political_preference"))) and bool(_clean(row.get("summary_analysis")))
        for row in rows
    )
    evidence_thin = sum(
        not any(_clean(row.get(field)) for field in ("whisper_transcript", "ocr_1", "frame_1"))
        for row in rows
    )
    interpretation_without_evidence = sum(
        any(_clean(row.get(field)) for field in INTERPRETIVE_FIELDS)
        and not any(_clean(row.get(field)) for field in ("whisper_transcript", "ocr_1", "frame_1"))
        for row in rows
    )

    return {
        "country": COUNTRY_NAMES[country],
        "source": str(path),
        "rows": len(rows),
        "columns": len(fields),
        "duplicate_document_ids": duplicate_ids,
        "duplicate_document_id_count": len(duplicate_ids),
        "missingness": missingness,
        "languages": dict(language.most_common()),
        "source_types": dict(source_types.most_common()),
        "unique_authors": len(authors),
        "evidence_thin_rows": evidence_thin,
        "interpretation_without_basic_evidence_rows": interpretation_without_evidence,
        "rows_with_political_preference_and_summary": potential_metadata_leakage,
        "audit_notes": [
            "Political-preference metadata coexisting with summaries is a leakage risk to inspect, not proof of leakage.",
            "Missing transcript/OCR/frame evidence makes downstream discourse claims harder to verify.",
            "Duplicate stable IDs require review before aggregate statistics or old-vs-new matching.",
            "Substantive correctness of entity/theme/Laclau labels still requires researcher review of source evidence.",
        ],
    }


def deterministic_sample(
    rows: list[dict[str, str]], *, size: int, country: str
) -> list[dict[str, str]]:
    """Round-robin deterministic sample across source/author/metadata strata.

    political_preference is used only to diversify the regression sample. It must never be
    injected into substantive model prompts as evidence about a particular document.
    """
    buckets: dict[tuple[str, ...], list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        key = tuple(_clean(row.get(field)) or "unknown" for field in STRATA_FIELDS)
        buckets[key].append((_stable_id(row, row_number), row))
    for values in buckets.values():
        values.sort(key=lambda item: item[0])

    selected: list[dict[str, str]] = []
    while len(selected) < size and any(buckets.values()):
        for key in sorted(buckets):
            if buckets[key] and len(selected) < size:
                _, row = buckets[key].pop(0)
                selected.append(row)
    return selected


def write_sample_csv(source: str | Path, country: str, output: str | Path, size: int) -> Path:
    rows, fields = load_country_rows(source, country)
    sample = deterministic_sample(rows, size=size, country=country)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sample)
    return target


def _index_rows(path: str | Path) -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return {_stable_id(dict(row), i + 2): dict(row) for i, row in enumerate(reader)}


def compare_csvs(old_path: str | Path, new_path: str | Path) -> dict[str, Any]:
    old = _index_rows(old_path)
    new = _index_rows(new_path)
    shared = sorted(set(old) & set(new))
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))

    dimensions: dict[str, dict[str, int]] = {}
    for field in (*EVIDENCE_FIELDS, *INTERPRETIVE_FIELDS):
        old_present = new_present = changed = 0
        for key in shared:
            before = _clean(old[key].get(field))
            after = _clean(new[key].get(field))
            old_present += bool(before)
            new_present += bool(after)
            changed += bool(before != after)
        dimensions[field] = {
            "old_nonempty": old_present,
            "new_nonempty": new_present,
            "changed_on_shared_records": changed,
        }

    provenance_fields = (
        "canonical_json",
        "evidence_json",
        "codebook_refs_json",
        "model_runs_json",
        "uncertainty_json",
        "abstentions_json",
    )
    provenance_coverage = {
        field: sum(bool(_clean(row.get(field))) for row in new.values())
        for field in provenance_fields
    }
    return {
        "old_source": str(old_path),
        "new_source": str(new_path),
        "old_records": len(old),
        "new_records": len(new),
        "shared_records": len(shared),
        "only_old": len(only_old),
        "only_new": len(only_new),
        "field_comparison": dimensions,
        "new_provenance_coverage": provenance_coverage,
        "interpretation": [
            "Changed output is not automatically improved output.",
            "Use this report to select records for human review of entity normalization, themes, evidence grounding, translation and theoretical claims.",
            "Prefer improvements in traceability, supported abstention and source-linked evidence over verbosity.",
        ],
    }


def _markdown_report(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", "", "```json", json.dumps(payload, ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def _write_report(payload: dict[str, Any], output: str | Path, title: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.casefold() == ".md":
        target.write_text(_markdown_report(title, payload), encoding="utf-8")
    else:
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m laclaugpt_data_analysis.ep24_quality")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit-legacy")
    audit.add_argument("--country", choices=sorted(COUNTRY_NAMES), required=True)
    audit.add_argument("--source", required=True)
    audit.add_argument("--output", required=True)

    sample = sub.add_parser("sample")
    sample.add_argument("--country", choices=sorted(COUNTRY_NAMES), required=True)
    sample.add_argument("--source", required=True)
    sample.add_argument("--output", required=True)
    sample.add_argument("--size", type=int, default=20)

    compare = sub.add_parser("compare")
    compare.add_argument("--old", required=True)
    compare.add_argument("--new", required=True)
    compare.add_argument("--output", required=True)

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "audit-legacy":
        payload = audit_legacy_csv(args.source, args.country)
        _write_report(payload, args.output, f"EP24 legacy audit: {COUNTRY_NAMES[args.country]}")
    elif args.command == "sample":
        write_sample_csv(args.source, args.country, args.output, args.size)
    else:
        payload = compare_csvs(args.old, args.new)
        _write_report(payload, args.output, "EP24 old-vs-new regression comparison")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
