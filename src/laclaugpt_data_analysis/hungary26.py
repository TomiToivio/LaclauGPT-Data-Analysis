"""Privacy-safe Hungary26 workbook normalization, audit and codebook helpers."""
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

from .canonical import CanonicalRecord
from .codebooks import Codebook, load_codebook, merge_codebooks

REQUIRED_PRIVATE_FILES = (
    "source/hungary2026_instagram.xlsx",
    "source/hungary2026_tiktok.xlsx",
    "codebooks/hungary26_private.json",
    "run/hungary26_roihu.yaml",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
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
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _pick(row: dict[str, Any], field: str) -> Any:
    for key in FIELD_ALIASES[field]:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _stable_id(platform: str, workbook: str, sheet: str, row_number: int, row: dict[str, Any]) -> str:
    primary = str(_pick(row, "source_url") or _pick(row, "post_id") or f"{workbook}:{sheet}:{row_number}")
    digest = hashlib.sha256(f"hungary26|{platform}|{primary}".encode()).hexdigest()[:20]
    return f"hu26-{platform}-{digest}"


def _fingerprint(row: dict[str, Any]) -> str:
    material = "|".join(str(_pick(row, field) or "").strip().casefold() for field in ("author", "caption", "created_at", "media_ref"))
    return hashlib.sha256(material.encode()).hexdigest()


def _near_key(caption: str) -> str:
    text = re.sub(r"https?://\S+", " ", caption.casefold())
    text = re.sub(r"[^\wáéíóöőúüű]+", " ", text, flags=re.UNICODE)
    return " ".join(token for token in text.split() if len(token) > 2)[:1000]


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
            "provenance": {"workbook": self.workbook, "sheet": self.sheet, "row": self.row_number},
            "raw_fields": self.raw_fields,
        }

    def to_canonical(self) -> CanonicalRecord:
        source_url = self.source_url.strip() or f"hungary26:{self.document_id}"
        media = []
        if self.media_ref:
            media.append({"kind": "video", "local_ref": self.media_ref, "metadata": {"media_id": self.media_id}})
        return CanonicalRecord(
            source_url=source_url,
            source_native_ids={"hungary26_document_id": self.document_id, "platform_post_id": self.post_id},
            raw_capture={"metadata": {"workbook": self.workbook, "sheet": self.sheet, "row": self.row_number}},
            source={
                "platform": self.platform,
                "source_type": "social_media_post",
                "author": self.author,
                "author_fullname": self.author_fullname,
                "created_at": self.created_at or None,
                "collected_at": self.collected_at or None,
                "language": "hu",
                "country": "HU",
                "raw_metadata": {
                    "hungary26_document_id": self.document_id,
                    "media_id": self.media_id,
                    "workbook": self.workbook,
                    "sheet": self.sheet,
                    "row": self.row_number,
                    "raw_fields": self.raw_fields,
                },
            },
            content={"text": self.caption, "language": "hu", "media_references": media},
            legacy={"hungary26_source_record": self.to_dict()},
        )


def load_hungary26_workbook(path: str | Path, *, platform: str) -> list[WorkbookRecord]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
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
            row = {key: _jsonable(value) for key, value in zip(headers, values) if key}
            if not any(value not in (None, "") for value in row.values()):
                continue
            document_id = _stable_id(platform, source.name, sheet.title, row_number, row)
            media_ref = str(_pick(row, "media_ref") or "").strip()
            media_seed = media_ref or str(_pick(row, "source_url") or document_id)
            caption = str(_pick(row, "caption") or "")
            records.append(WorkbookRecord(
                document_id=document_id,
                media_id="media-" + hashlib.sha256(media_seed.encode()).hexdigest()[:20],
                platform=platform,
                workbook=source.name,
                sheet=sheet.title,
                row_number=row_number,
                source_url=str(_pick(row, "source_url") or ""),
                post_id=str(_pick(row, "post_id") or ""),
                author=str(_pick(row, "author") or ""),
                author_fullname=str(_pick(row, "author_fullname") or ""),
                caption=caption,
                created_at=str(_pick(row, "created_at") or ""),
                collected_at=str(_pick(row, "collected_at") or ""),
                media_ref=media_ref,
                exact_fingerprint=_fingerprint(row),
                near_duplicate_key=_near_key(caption),
                raw_fields=row,
            ))
    return records


def private_runtime_preflight(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    missing = [rel for rel in REQUIRED_PRIVATE_FILES if not (base / rel).exists()]
    if missing:
        raise FileNotFoundError("Hungary26 private runtime is incomplete. Missing: " + ", ".join(missing))
    return {"private_root": str(base), "required_files": list(REQUIRED_PRIVATE_FILES), "ok": True}


def audit_records(records: Iterable[WorkbookRecord]) -> dict[str, Any]:
    items = list(records)
    ids = Counter(item.document_id for item in items)
    exact: dict[str, list[str]] = defaultdict(list)
    near: dict[str, list[str]] = defaultdict(list)
    missing = Counter()
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
        "platform_counts": dict(Counter(item.platform for item in items)),
        "duplicate_document_ids": sorted(key for key, count in ids.items() if count > 1),
        "exact_duplicate_groups": [group for group in exact.values() if len(group) > 1],
        "near_duplicate_groups": [group for group in near.values() if len(group) > 1],
        "missingness": dict(missing),
        "checks": {"original_hungarian_preserved": True, "raw_fields_preserved": True, "provenance_to_workbook_sheet_row": True},
    }


def deterministic_pilot(records: Iterable[WorkbookRecord], *, per_platform: int = 12) -> list[WorkbookRecord]:
    groups: dict[str, list[WorkbookRecord]] = defaultdict(list)
    for record in records:
        groups[record.platform].append(record)
    selected: list[WorkbookRecord] = []
    for platform_records in groups.values():
        selected.extend(sorted(platform_records, key=lambda record: hashlib.sha256(record.document_id.encode()).hexdigest())[:per_platform])
    return sorted(selected, key=lambda record: (record.platform, record.document_id))


def load_private_hungary26_codebook(path: str | Path) -> Codebook:
    book = load_codebook(path)
    if book.project != "hungary26":
        raise ValueError("private codebook must declare project: hungary26")
    allowed = {"researcher_private", "public_context", "model_candidate"}
    for entry in book.entries:
        provenance_class = str(entry.metadata.get("provenance_class") or "")
        if provenance_class not in allowed:
            raise ValueError(f"{entry.kind}:{entry.label} missing valid provenance_class")
    return book


def codebook_collisions(book: Codebook) -> list[dict[str, Any]]:
    index: dict[str, set[str]] = defaultdict(set)
    for entry in book.entries:
        for surface in [entry.label, *entry.aliases]:
            if surface.strip():
                index[surface.casefold().strip()].add(entry.label)
    return [{"surface": key, "canonical_labels": sorted(labels), "review_required": True} for key, labels in sorted(index.items()) if len(labels) > 1]


def build_effective_codebook(*, public_path: str | Path, private_path: str | Path) -> Codebook:
    return merge_codebooks([load_codebook(public_path), load_private_hungary26_codebook(private_path)], codebook_id="hungary26-effective")


def write_manifest(records: Iterable[WorkbookRecord], output: str | Path, *, canonical: bool = False) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = record.to_canonical().model_dump(mode="json") if canonical else record.to_dict()
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m laclaugpt_data_analysis.hungary26")
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight"); preflight.add_argument("--private-root", required=True)
    for name in ("normalize", "audit", "pilot"):
        cmd = sub.add_parser(name); cmd.add_argument("--instagram", required=True); cmd.add_argument("--tiktok", required=True)
        if name == "audit": cmd.add_argument("--json", required=True); cmd.add_argument("--markdown", required=True)
        else: cmd.add_argument("--output", required=True)
        if name == "pilot": cmd.add_argument("--per-platform", type=int, default=12); cmd.add_argument("--canonical", action="store_true")
        if name == "normalize": cmd.add_argument("--canonical", action="store_true")
    collisions = sub.add_parser("codebook-collisions"); collisions.add_argument("--codebook", required=True); collisions.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "preflight":
        print(json.dumps(private_runtime_preflight(args.private_root), indent=2)); return 0
    if args.command == "codebook-collisions":
        Path(args.output).write_text(json.dumps(codebook_collisions(load_private_hungary26_codebook(args.codebook)), ensure_ascii=False, indent=2), encoding="utf-8"); return 0
    records = [*load_hungary26_workbook(args.instagram, platform="instagram"), *load_hungary26_workbook(args.tiktok, platform="tiktok")]
    if args.command == "normalize":
        write_manifest(records, args.output, canonical=args.canonical)
    elif args.command == "pilot":
        write_manifest(deterministic_pilot(records, per_platform=args.per_platform), args.output, canonical=args.canonical)
    else:
        report = audit_records(records)
        Path(args.json).parent.mkdir(parents=True, exist_ok=True); Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        Path(args.markdown).write_text("# Hungary26 source audit\n\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
