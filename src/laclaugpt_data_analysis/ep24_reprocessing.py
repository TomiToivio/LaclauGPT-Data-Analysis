"""EP24 Finland/Poland reprocessing helpers.

This module is intentionally public and contains no row-level research data. It bridges
three things needed by the restricted EP24 reruns:

1. a public methodology/language codebook,
2. a private human-grounded country codebook compiled from researcher workbooks, and
3. a lossless dashboard export that preserves the historical EP24 dataframe columns
   while appending the modern canonical LaclauGPT record.

Private entity/theme mappings and research notes are loaded only at runtime and are never
written back to the repository.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .canonical import CanonicalRecord
from .codebooks import Codebook, CodebookEntry, load_codebook, merge_codebooks

EP24_LEGACY_COLUMNS: tuple[str, ...] = (
    "country", "author_username", "account_type", "source_type", "source_recording",
    "video_filename", "video_file", "whisper_transcript", "whisper_language",
    "whisper_translated", "ocr_1", "frame_1", "summary_analysis", "entities", "topics",
    "positive", "neutral", "negative", "recording_date", "day_number", "political_themes",
    "formula_of_populism_analysis", "formula_of_populism_us", "formula_of_populism_frontier",
    "formula_of_populism_us_elements", "formula_of_populism_frontier_elements",
    "formula_of_populism_us_affects", "formula_of_populism_frontier_affects", "video_id",
    "sequence_number", "recording_datetime", "political_preference", "allas_filename",
    "lda_topic", "lda_minor_topics", "lda_topic_words", "lda_minor_topic", "lda_15_topic",
    "lda_15_minor_topic", "lda_15_topic_words", "lda_40_topic", "lda_40_minor_topic",
    "lda_40_topic_words", "lda_country_topic", "lda_country_minor_topic",
    "lda_country_topic_words", "manifestoberta_predicted_class", "manifestoberta_probabilities",
    "corrected_date", "original_date", "corresponding_date", "split_number", "new_entity",
    "new_theme", "frames", "ocr_2", "ocr_3", "ocr_4", "ocr_5", "ocr_6", "frame_2",
    "frame_3", "frame_4", "frame_5", "frame_6", "video_duration", "profile_name",
    "daily_file_number", "new_id", "new_filename", "old_id", "puhti_filename",
    "spacy_entities", "us", "them",
)

EP24_MODERN_COLUMNS: tuple[str, ...] = (
    "canonical_schema_version", "human_summary", "human_readable_markdown",
    "canonical_json", "intermediate_json", "analysis_json", "evidence_json",
    "codebook_refs_json", "model_runs_json", "uncertainty_json", "abstentions_json",
    "review_json",
)


def _private_provenance(item: dict[str, Any]) -> str:
    provenance = item.get("provenance") or {}
    if not isinstance(provenance, dict):
        return "private-human-codebook"
    workbook = str(provenance.get("workbook") or "private-workbook")
    sheet = str(provenance.get("sheet") or "")
    row = str(provenance.get("row") or "")
    parts = [workbook]
    if sheet:
        parts.append(sheet)
    if row:
        parts.append(f"row:{row}")
    return "private:" + "/".join(parts)


def load_private_ep24_human_codebook(path: str | Path) -> Codebook:
    """Adapt the private workbook compiler output into the public Codebook contract.

    The source JSON is expected to be the country payload produced by the private EP24
    workbook compiler. The adapter deliberately keeps researcher notes in private runtime
    sections and never serializes them unless the caller explicitly writes the merged book
    outside the repository.
    """
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    country_code = str(payload.get("country_code") or "").upper()
    country = str(payload.get("country") or country_code)
    if country_code not in {"FI", "PL"}:
        raise ValueError("EP24 reprocessing currently expects FI or PL private codebooks")

    entries: list[CodebookEntry] = []
    for item in payload.get("entities", []):
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        entries.append(
            CodebookEntry(
                kind="entity",
                label=label,
                aliases=[str(v) for v in item.get("aliases", []) if str(v).strip()],
                definition="Human-grounded EP24 entity normalization.",
                provenance=_private_provenance(item),
                country=country_code,
                metadata={"private_runtime": True, "entity_type": item.get("type", "entity")},
            )
        )
    for item in payload.get("themes", []):
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        entries.append(
            CodebookEntry(
                kind="topic",
                label=label,
                aliases=[str(v) for v in item.get("aliases", []) if str(v).strip()],
                definition="Human-grounded EP24 theme normalization.",
                provenance=_private_provenance(item),
                country=country_code,
                metadata={"private_runtime": True},
            )
        )

    notes = []
    for item in payload.get("research_notes", []):
        text = str(item.get("text") or "").strip()
        if text:
            notes.append({"text": text, "provenance": _private_provenance(item)})

    return Codebook(
        codebook_id=f"ep24-{country_code.casefold()}-human-private",
        version="runtime",
        title=f"Private human-grounded EP24 codebook: {country}",
        description="Runtime-only researcher grounding compiled from controlled workbooks.",
        project="ep24",
        arena="european-parliament-election-2024",
        entries=entries,
        sections={"human_research_notes": notes, "private_runtime": True},
    )


def build_effective_ep24_codebook(
    *, public_path: str | Path, private_path: str | Path
) -> Codebook:
    """Merge public EP24 methodology with the private country researcher layer."""
    public = load_codebook(public_path)
    private = load_private_ep24_human_codebook(private_path)
    return merge_codebooks([public, private], codebook_id="ep24-effective")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _labels(items: Iterable[Any]) -> str:
    labels: list[str] = []
    for item in items:
        label = getattr(item, "label", None)
        if label:
            labels.append(str(label))
    return ", ".join(dict.fromkeys(labels))


def project_ep24_dashboard_row(record: CanonicalRecord) -> dict[str, str]:
    """Project one canonical record into old-dashboard-compatible + modern columns.

    Existing legacy values always win. Missing legacy fields are backfilled from canonical
    evidence where the mapping is deterministic. No interpretive result is fabricated.
    """
    row = {name: str(record.legacy.get(name, "") or "") for name in EP24_LEGACY_COLUMNS}
    row["country"] = row["country"] or record.source.country
    row["author_username"] = row["author_username"] or record.source.author
    row["source_type"] = row["source_type"] or record.source.platform or record.source.source_type
    row["video_id"] = row["video_id"] or record.source_native_ids.get("video_id", "")
    row["whisper_language"] = row["whisper_language"] or (record.content.language or record.source.language)
    row["whisper_transcript"] = row["whisper_transcript"] or record.content.text
    row["whisper_translated"] = row["whisper_translated"] or (record.content.translated_text or "")
    row["summary_analysis"] = row["summary_analysis"] or record.human_readable.summary or (record.analysis.summary or "")
    row["entities"] = row["entities"] or _labels(record.analysis.entities)
    row["topics"] = row["topics"] or _labels(record.analysis.topics)
    row["us"] = row["us"] or _labels(record.analysis.us)
    row["them"] = row["them"] or _labels(record.analysis.them)
    row["political_themes"] = row["political_themes"] or _labels(record.analysis.themes)

    if not row["formula_of_populism_analysis"] and record.analysis.formula_of_populism:
        row["formula_of_populism_analysis"] = _json(record.analysis.formula_of_populism)

    ocr = list(record.intermediate.ocr)
    frame_analysis = list(record.intermediate.frame_analysis)
    for index in range(6):
        ocr_key = f"ocr_{index + 1}"
        frame_key = f"frame_{index + 1}"
        if not row[ocr_key] and index < len(ocr):
            item = ocr[index]
            row[ocr_key] = str(item.get("text") if isinstance(item, dict) else item)
        if not row[frame_key] and index < len(frame_analysis):
            item = frame_analysis[index]
            if isinstance(item, dict):
                row[frame_key] = str(item.get("analysis") or item.get("description") or _json(item))
            else:
                row[frame_key] = str(item)
    if not row["frames"] and record.intermediate.frames:
        row["frames"] = _json(record.intermediate.frames)

    payload = record.model_dump(mode="json")
    row.update(
        {
            "canonical_schema_version": record.schema_version,
            "human_summary": record.human_readable.summary or (record.analysis.summary or ""),
            "human_readable_markdown": record.human_readable.markdown,
            "canonical_json": _json(payload),
            "intermediate_json": _json(payload.get("intermediate", {})),
            "analysis_json": _json(payload.get("analysis", {})),
            "evidence_json": _json(payload.get("evidence", [])),
            "codebook_refs_json": _json(record.analysis.codebook_refs),
            "model_runs_json": _json(record.analysis.model_runs),
            "uncertainty_json": _json(record.analysis.uncertainty),
            "abstentions_json": _json(record.analysis.abstentions),
            "review_json": _json(payload.get("review", {})),
        }
    )
    return row


def write_ep24_dashboard_csv(records: Iterable[CanonicalRecord], output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [*EP24_LEGACY_COLUMNS, *EP24_MODERN_COLUMNS]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(project_ep24_dashboard_row(record))
    return target


def _load_records(path: str | Path) -> list[CanonicalRecord]:
    records: list[CanonicalRecord] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CanonicalRecord.model_validate(json.loads(line)))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-ep24")
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge-codebooks")
    merge.add_argument("--public", required=True)
    merge.add_argument("--private", required=True)
    merge.add_argument("--output", required=True)

    export = sub.add_parser("export-dashboard")
    export.add_argument("--records", required=True, help="Canonical JSONL input")
    export.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "merge-codebooks":
        book = build_effective_ep24_codebook(public_path=args.public, private_path=args.private)
        Path(args.output).write_text(
            json.dumps(book.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0
    write_ep24_dashboard_csv(_load_records(args.records), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
