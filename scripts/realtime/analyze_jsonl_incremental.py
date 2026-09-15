#!/usr/bin/env python3
"""Incrementally analyze canonical JSONL without mutating Collection data.

The output file is append-only and keyed by canonical ``source_url``. Existing
output records are skipped, making the script suitable for a timer/systemd loop
on a research server. Real study codebooks and data paths remain runtime-only.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.codebooks import load_codebook
from laclaugpt_data_analysis.llm.ollama import OllamaProvider
from laclaugpt_data_analysis.pipeline import analyze_record


def _seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = CanonicalRecord.model_validate_json(line)
        seen.add(record.source_url)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--codebook", type=Path)
    parser.add_argument("--model", default="auto")
    parser.add_argument("--limit", type=int, default=0,
                        help="maximum new records this run; 0 means unlimited")
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
            record = CanonicalRecord.model_validate_json(line)
            if record.source_url in seen:
                continue
            analyzed = analyze_record(
                record,
                provider=provider,
                codebook_entries=entries,
                model=args.model,
                allow_cloud_fallback=False,
            )
            target.write(analyzed.model_dump_json() + "\n")
            target.flush()
            seen.add(record.source_url)
            processed += 1
            if args.limit and processed >= args.limit:
                break

    print(f"analyzed_new_records={processed} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
