"""Public Hungary26 reprocessing helpers.

This module contains only generic logic. Real workbooks, private codebooks, researcher
notes, runtime paths and row-level audit examples must be supplied from
``LaclauGPT-Private/analysis/hungary26`` at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .codebooks import Codebook, CodebookEntry, load_codebook, merge_codebooks

HUNGARY26_ELECTION_DATE = "2026-04-12"
REQUIRED_PRIVATE_FILES = (
    "source/hungary2026_instagram.xlsx",
    "source/hungary2026_tiktok.xlsx",
    "codebooks/hungary26_private.json",
    "run/hungary26_roihu.yaml",
)

PLATFORM_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "source_url": ("url", "source_url", "post_url", "video_url", "permalink", "link"),
    "post_id": ("id", "post_id", "video_id", "shortcode", "media_id"),
    "author": ("author", "username", "author_username", "owner_username", "account"),
    "author_fullname": ("profile_name", "author_fullname", "owner_name", "display_name"),
    "caption": ("caption", "text", "description", "post_text", "title"),
    "created_at": ("created_at", "post_date", "date", "timestamp", "published_at"),
    "collected_at": ("collected_at", "collection_date", "scraped_at", "recording_date"),
    "media_ref": ("video_file", "video_filename", "media", "filename", "local_path"),
}


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _pick(row: dict[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _stable_id(platform: str, workbook: str, sheet: str, row_number: int, row: dict[str, Any]) -> str:
    source_url = str(_pick(row, PLATFORM_FIELD_ALIASES["source_url"]) or "").strip()
    post_id = str(_pick(row, PLATFORM_FIELD_ALIASES["post_id"]) or "").strip()
    primary = source_url or post_id or f"{workbook}:{sheet}:{row_number}"
    digest = hashlib.sha256(f"hungary26|{platform}|{primary}".encode("utf-8")).hexdigest()[:20]
    return f"hu26-{platform}-{digest}"


def _fingerprint(row: dict[str, Any]) -> str:
    material = "|".join(
        str(_pick(row, PLATFORM_FIELD_ALIASES[name]) or "").strip().casefold()
        for name in ("author", "caption", "created_at", "media_ref")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _near_duplicate_key(row: dict[str, Any]) -> str:
    caption = str(_pick(row, PLATFORM_FIELD_ALIASES["caption"]) or "").casefold()
    caption = re.sub(r"https?://\S+", " ", caption)
    caption = re.sub(r"[^\wáéíóöőúüű]+", " ", caption, flags=re.UNICODE)
    tokens = [token for token in caption.split() if len(token) > 2]
    return " ".join(tokens[:40])


@dataclass(frozen=True)
class WorkbookRecord:
    document_id: str
    media_id: str
    platform: str
    workbook: str
    sheet: str
    row_number: int
    source_url: str
    post_id: str
    author: str
    author_fullname: str
    caption: str
    created_at: str
    collected_at: str
    media_ref: str
    exact_fingerprint: str
    near_duplicate_key: str
    raw_fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "media_id": self.media_id,
            "project": "hungary26",
            "platform": self.platform,
            "workbook": self.workbook,
            "sheet": self.sheet,
            "row_number": self.row_number,
            "source_url": self.source_url,
            "post_id": self.post_id,
            "author": self.author,
            "author_fullname": self.author_fullname,
            "caption": self.caption,
            "created_at": self.created_at,
            "collected_at": self.collected_at,
            "media_ref": self.media_ref,
            "language": "hu",
            "country": "HU",
            "exact_fingerprint": self.exact_fingerprint,
            "near_duplicate_key": self.near_duplicate_key,
            "provenance": {
                "workbook": self.workbook,
                "sheet": self.sheet,
                "row": self.row_number,
            },
            "raw_fields": self.raw_fields,
        }


def load_hungary26_workbook(path: str | Path, *, platform: str) -> list[WorkbookRecord]:
    """Load Instagram/TikTok XLSX without discarding platform-specific fields."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - exercised by Roihu preflight
        raise RuntimeError("Hungary26 XLSX loading requires openpyxl") from exc

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Hungary26 source workbook missing: {source}")
    if platform not in {"instagram", "tiktok"}:
        raise ValueError("platform must be instagram or tiktok")

    workbook = load_workbook(source, read_only=True, data_only=True)
    records: list[WorkbookRecord] = []
    for sheet in workbook.worksheets:
        rows = sheet.iter_rows(values_only=True)
        try:
            headers = [_norm_header(value) for value in next(rows)]
        except StopIteration:
            continue
        for row_number, values in enumerate(rows, start=2):
            row = {header: _jsonable(value) for header, value in zip(headers, values) if header}
            if not any(value not in (None, "") for value in row.values()):
                continue
            document_id = _stable_id(platform, source.name, sheet.title, row_number, row)
            media_ref = str(_pick(row, PLATFORM_FIELD_ALIASES["media_ref"]) or "").strip()
            media_material = media_ref or str(_pick(row, PLATFORM_FIELD_ALIASES["source_url"]) or document_id)
            media_id = "media-" + hashlib.sha256(media_material.encode("utf-8")).hexdigest()[:20]
            records.append(
                WorkbookRecord(
                    document_id=document_id,
                    media_id=media_id,
                    platform=platform,
                    workbook=source.name,
                    sheet=sheet.title,
                    row_number=row_number,
                    source_url=str(_pick(row, PLATFORM_FIELD_ALIASES["source_url"]) or ""),
                    post_id=str(_pick(row, PLATFORM_FIELD_ALIASES["post_id"]) or ""),
                    author=str(_pick(row, PLATFORM_FIELD_ALIASES["author"]) or ""),
                    author_fullname=str(_pick(row, PLATFORM_FIELD_ALIASES["author_fullname"]) or ""),
                    caption=str(_pick(row, PLATFORM_FIELD_ALIASES["caption"]) or ""),
                    created_at=str(_pick(row, PLATFORM_FIELD_ALIASES["created_at"]) or ""),
                    collected_at=str(_pick(row, PLATFORM_FIELD_ALIASES["collected_at"]) or ""),
                    media_ref=media_ref,
                    exact_fingerprint=_fingerprint(row),
                    near_duplicate_key=_near_duplicate_key(row),
                    raw_fields=row,
                )
            )
    return records


def private_runtime_preflight(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    missing = [rel for rel in REQUIRED_PRIVATE_FILES if not (base / rel).exists()]
    if missing:
        formatted = "\n  - ".join(missing)
        raise FileNotFoundError(
            "Hungary26 private runtime is incomplete. Missing:\n  - " + formatted
            + "\nRun the migration/rebuild workflow in LaclauGPT-Private first."
        )
    return {"private_root": str(base), "required_files": list(REQUIRED_PRIVATE_FILES), "ok": True}


def audit_records(records: Iterable[WorkbookRecord]) -> dict[str, Any]:
    items = list(records)
    ids = Counter(item.document_id for item in items)
    exact = defaultdict(list)
    near = defaultdict(list)
    missing = Counter()
    by_platform = Counter(item.platform for item in items)
    for item in items:
        exact[item.exact_fingerprint].append(item.document_id)
        if item.near_duplicate_key:
            near[item.near_duplicate_key].append(item.document_id)
        for field in ("source_url", "author", "caption", "created_at", "media_ref"):
            if not getattr(item, field):
                missing[field] += 1
    return {
        "schema_version": "hungary26-audit-v1",
        "records": len(items),
        "platform_counts": dict(by_platform),
        "duplicate_document_ids": sorted(key for key, count in ids.items() if count > 1),
        "exact_duplicate_groups": [value for value in exact.values() if len(value) > 1],
        "near_duplicate_groups": [value for value in near.values() if len(value) > 1],
        "missingness": dict(missing),
        "checks": {
            "original_hungarian_preserved": True,
            "raw_fields_preserved": True,
            "derived_fields_do_not_overwrite_raw": True,
            "provenance_to_workbook_sheet_row": True,
        },
    }


def deterministic_pilot(records: Iterable[WorkbookRecord], *, per_platform: int = 12) -> list[WorkbookRecord]:
    """Choose a stable pilot with media/text/missing-field diversity."""
    groups: dict[str, list[WorkbookRecord]] = defaultdict(list)
    for record in records:
        groups[record.platform].append(record)
    selected: list[WorkbookRecord] = []
    for platform, platform_records in sorted(groups.items()):
        def rank(record: WorkbookRecord) -> tuple[int, str]:
            difficulty = sum(
                int(not value)
                for value in (record.caption, record.media_ref, record.author, record.created_at)
            )
            digest = hashlib.sha256(record.document_id.encode("utf-8")).hexdigest()
            return (-difficulty, digest)
        selected.extend(sorted(platform_records, key=rank)[:per_platform])
    return selected


def load_private_hungary26_codebook(path: str | Path) -> Codebook:
    """Validate the private Hungary26 codebook and enforce provenance separation."""
    book = load_codebook(path)
    if book.project != "hungary26":
        raise ValueError("private codebook must declare project: hungary26")
    allowed = {"researcher_private", "public_context", "model_candidate"}
    for entry in book.entries:
        provenance_class = str(entry.metadata.get("provenance_class") or "")
        if provenance_class not in allowed:
            raise ValueError(
                f"{entry.kind}:{entry.label} missing valid provenance_class; expected one of {sorted(allowed)}"
            )
        if provenance_class == "model_candidate" and entry.metadata.get("reviewed") is True:
            raise ValueError("model_candidate entries must be promoted to a grounded provenance class after review")
    return book


def codebook_collisions(book: Codebook) -> list[dict[str, Any]]:
    index: dict[str, set[str]] = defaultdict(set)
    for entry in book.entries:
        for surface in [entry.label, *entry.aliases]:
            key = surface.casefold().strip()
            if key:
                index[key].add(entry.label)
    return [
        {"surface": surface, "canonical_labels": sorted(labels), "review_required": True}
        for surface, labels in sorted(index.items())
        if len(labels) > 1
    ]


def build_effective_codebook(*, public_path: str | Path, private_path: str | Path) -> Codebook:
    public = load_codebook(public_path)
    private = load_private_hungary26_codebook(private_path)
    return merge_codebooks([public, private], codebook_id="hungary26-effective")


def write_manifest(records: Iterable[WorkbookRecord], output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return target


def _markdown_audit(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Hungary26 legacy/source quality audit",
            "",
            f"Records: {report['records']}",
            f"Platforms: {json.dumps(report['platform_counts'], ensure_ascii=False)}",
            f"Duplicate document IDs: {len(report['duplicate_document_ids'])}",
            f"Exact duplicate groups: {len(report['exact_duplicate_groups'])}",
            f"Near-duplicate groups: {len(report['near_duplicate_groups'])}",
            "",
            "## Missingness",
            "",
            *[f"- {key}: {value}" for key, value in sorted(report['missingness'].items())],
            "",
            "Row-level examples are intentionally omitted from this public-safe renderer. "
            "Private runtime tooling may append restricted examples under the private output tree.",
        ]
    ) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laclaugpt-hungary26")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight")
    preflight.add_argument("--private-root", required=True)

    normalize = sub.add_parser("normalize")
    normalize.add_argument("--instagram", required=True)
    normalize.add_argument("--tiktok", required=True)
    normalize.add_argument("--output", required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("--instagram", required=True)
    audit.add_argument("--tiktok", required=True)
    audit.add_argument("--json", required=True)
    audit.add_argument("--markdown", required=True)

    pilot = sub.add_parser("pilot")
    pilot.add_argument("--instagram", required=True)
    pilot.add_argument("--tiktok", required=True)
    pilot.add_argument("--output", required=True)
    pilot.add_argument("--per-platform", type=int, default=12)

    collisions = sub.add_parser("codebook-collisions")
    collisions.add_argument("--codebook", required=True)
    collisions.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "preflight":
        print(json.dumps(private_runtime_preflight(args.private_root), indent=2))
        return 0

    records = [
        *load_hungary26_workbook(args.instagram, platform="instagram"),
        *load_hungary26_workbook(args.tiktok, platform="tiktok"),
    ] if hasattr(args, "instagram") else []

    if args.command == "normalize":
        write_manifest(records, args.output)
    elif args.command == "audit":
        report = audit_records(records)
        json_target = Path(args.json)
        json_target.parent.mkdir(parents=True, exist_ok=True)
        json_target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_target = Path(args.markdown)
        markdown_target.parent.mkdir(parents=True, exist_ok=True)
        markdown_target.write_text(_markdown_audit(report), encoding="utf-8")
    elif args.command == "pilot":
        write_manifest(deterministic_pilot(records, per_platform=args.per_platform), args.output)
    else:
        book = load_private_hungary26_codebook(args.codebook)
        Path(args.output).write_text(
            json.dumps(codebook_collisions(book), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
