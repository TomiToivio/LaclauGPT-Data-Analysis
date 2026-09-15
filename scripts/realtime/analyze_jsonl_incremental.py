#!/usr/bin/env python3
"""Incrementally analyze canonical JSONL and refresh researcher-facing outputs.

The canonical output file is append-only and keyed by ``source_url``. After each pass,
the script deterministically refreshes a wide legacy-compatible researcher CSV and one
Markdown report per record from that same canonical JSONL.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from laclaugpt_data_analysis.codebooks import load_codebook
from laclaugpt_data_analysis.exporters import write_human_reports
from laclaugpt_data_analysis.interchange import (
    read_jsonl,
    record_from_json,
    record_to_json,
    write_csv,
)
from laclaugpt_data_analysis.llm.ollama import OllamaProvider
from laclaugpt_data_analysis.pipeline import analyze_record


def _seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = record_from_json(line)
        seen.add(record.source_url)
    return seen


def _refresh_research_outputs(output: Path) -> tuple[Path, Path]:
    records = read_jsonl(output)
    csv_path = output.with_name(f"{output.stem}_researchers.csv")
    reports_dir = output.with_name(f"{output.stem}_reports")
    write_csv(csv_path, records)
    write_human_reports(records, reports_dir)
    return csv_path, reports_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--codebook", type=Path)
    parser.add_argument("--model", default="auto")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="maximum new records this run; 0 means unlimited",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"input JSONL does not exist: {args.input}")
    if args.input.resolve() == args.output.resolve():
        raise SystemExit("input and output must be different files")

    entries = load_codebook(args.codebook).entries if args.codebook else []
    provider = OllamaProvider()
    seen = _seen(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    with args.input.open("r", encoding="utf-8") as source, args.output.open(
        "a", encoding="utf-8"
    ) as target:
        for line in source:
            if not line.strip():
                continue
            record = record_from_json(line)
            if record.source_url in seen:
                continue
            analyzed = analyze_record(
                record,
                provider=provider,
                codebook_entries=entries,
                model=args.model,
                allow_cloud_fallback=False,
            )
            target.write(record_to_json(analyzed) + "\n")
            target.flush()
            seen.add(record.source_url)
            processed += 1
            if args.limit and processed >= args.limit:
                break

    csv_path, reports_dir = _refresh_research_outputs(args.output)
    print(
        f"analyzed_new_records={processed} output={args.output} "
        f"researcher_csv={csv_path} reports={reports_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
