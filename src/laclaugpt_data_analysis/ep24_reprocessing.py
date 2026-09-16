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
from .research_record import legacy_projection

# Exact field order observed in the historical Finland/Poland dashboard dataframes.
# Keep this separate from the broader generic LEGACY_RESEARCH_COLUMNS contract because
# the old EP24 dashboard code expects these names and ordering.
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
    workbook compiler. Research notes remain runtime context and are not promoted into
    source evidence or public codebook entries.
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


def _formula_value(formula: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = formula.get(key)
        if value not in (None, "", [], {}):
            return value if isinstance(value, str) else _json(value)
    return ""


def project_ep24_dashboard_row(record: CanonicalRecord) -> dict[str, str]:
    """Project one canonical record into exact old-dashboard + modern columns.

    The shared research-record projector supplies canonical EP24-era aliases. The exact
    historical FI/PL columns are then selected in their original order, with imported
    study-specific extras retained from ``record.legacy``. No missing interpretation is
    fabricated merely to fill an old column.
    """
    projected = legacy_projection(record)
    row = {name: str(projected.get(name, record.legacy.get(name, "")) or "") for name in EP24_LEGACY_COLUMNS}

    # The exact historical dataframes had four additional Formula-of-Populism
    # decomposition columns that the generic projector predates. Populate them only when
    # the current structured formula actually provides matching components.
    formula = record.analysis.formula_of_populism or {}
    formula_mapping = {
        "formula_of_populism_us_elements": ("us_elements", "people_elements"),
        "formula_of_populism_frontier_elements": ("frontier_elements", "them_elements"),
        "formula_of_populism_us_affects": ("us_affects", "people_affects"),
        "formula_of_populism_frontier_affects": ("frontier_affects", "them_affects"),
    }
    for column, keys in formula_mapping.items():
        if not row[column]:
            row[column] = _formula_value(formula, *keys)

    # Some migrated historical frame rows use ``analysis`` rather than the generic
    # projector's ``description``/``text`` keys. Support both without interpreting them.
    for index, item in enumerate(record.intermediate.frame_analysis[:6], start=1):
        key = f"frame_{index}"
        if not row[key] and isinstance(item, dict):
            row[key] = str(item.get("analysis") or item.get("description") or item.get("text") or "")

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
    """Load canonical JSONL or a Roihu checkpoint CSV containing canonical_json."""
    source = Path(path)
    records: list[CanonicalRecord] = []
    if source.suffix.casefold() == ".csv":
        with source.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                raw = str(row.get("canonical_json") or "").strip()
                if raw:
                    records.append(CanonicalRecord.model_validate(json.loads(raw)))
        return records
    for line in source.read_text(encoding="utf-8").splitlines():
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
    export.add_argument("--records", required=True, help="Canonical JSONL or checkpoint CSV")
    export.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "merge-codebooks":
        book = build_effective_ep24_codebook(public_path=args.public, private_path=args.private)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(book.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0
    write_ep24_dashboard_csv(_load_records(args.records), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
