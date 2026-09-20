"""Versioned machine-readable codebooks and safe memory seeding.

Codebooks are public methodology or externally supplied private runtime inputs.
The loader validates structure, supports JSON/YAML, computes a stable content
fingerprint, and can merge layered project/arena additions without exposing the
source path in provenance.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from .memory.models import KIND_PREFIX, KINDS


class CodebookEntry(BaseModel):
    kind: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    provenance: str = ""
    language: str | None = None
    country: str | None = None
    actor_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Codebook(BaseModel):
    codebook_id: str
    version: str
    title: str
    description: str = ""
    project: str | None = None
    arena: str | None = None
    required_sections: list[str] = Field(default_factory=list)
    optional_sections: list[str] = Field(default_factory=list)
    entries: list[CodebookEntry] = Field(default_factory=list)
    sections: dict[str, Any] = Field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def provenance_snapshot(self) -> dict[str, Any]:
        return {
            "codebook_id": self.codebook_id,
            "version": self.version,
            "sha256": self.fingerprint(),
            "project": self.project or "",
            "arena": self.arena or "",
            "entry_count": len(self.entries),
        }


def stable_codebook_id(entry: CodebookEntry) -> str:
    if entry.kind not in KINDS:
        raise ValueError(f"unsupported memory kind: {entry.kind}")
    digest = hashlib.sha256(f"{entry.kind}:{entry.label.casefold().strip()}".encode()).hexdigest()[:12]
    return f"{KIND_PREFIX[entry.kind]}-{digest}"


def _read_payload(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        raise ValueError("machine-readable codebooks must use JSON or YAML")
    if not isinstance(data, dict):
        raise ValueError("codebook root must be an object/mapping")
    return data


def validate_codebook(codebook: Codebook) -> list[str]:
    warnings: list[str] = []
    labels: set[tuple[str, str]] = set()
    for entry in codebook.entries:
        if entry.kind not in KINDS:
            warnings.append(f"unsupported memory kind: {entry.kind}")
        key = (entry.kind, entry.label.casefold().strip())
        if key in labels:
            warnings.append(f"duplicate entry: {entry.kind}:{entry.label}")
        labels.add(key)
    missing_sections = [name for name in codebook.required_sections if name not in codebook.sections]
    if missing_sections:
        warnings.append("missing required sections: " + ", ".join(sorted(missing_sections)))
    return warnings


def load_codebook(path: str | Path, *, strict: bool = True) -> Codebook:
    source = Path(path)
    try:
        codebook = Codebook.model_validate(_read_payload(source))
    except (ValidationError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid codebook {source.name}: {exc}") from exc
    warnings = validate_codebook(codebook)
    if strict and warnings:
        raise ValueError("invalid codebook: " + "; ".join(warnings))
    return codebook


def merge_codebooks(codebooks: Iterable[Codebook], *, codebook_id: str = "effective") -> Codebook:
    books = list(codebooks)
    if not books:
        raise ValueError("at least one codebook is required")
    merged_entries: dict[tuple[str, str], CodebookEntry] = {}
    sections: dict[str, Any] = {}
    required: list[str] = []
    optional: list[str] = []
    for book in books:
        for entry in book.entries:
            merged_entries[(entry.kind, entry.label.casefold().strip())] = entry
        sections.update(book.sections)
        required.extend(book.required_sections)
        optional.extend(book.optional_sections)
    version_hash = hashlib.sha256(
        "|".join(book.fingerprint() for book in books).encode("utf-8")
    ).hexdigest()[:12]
    return Codebook(
        codebook_id=codebook_id,
        version=f"merged-{version_hash}",
        title="Effective merged codebook",
        description="Layered runtime codebook assembled from supplied sources.",
        project=books[-1].project or books[0].project,
        arena=books[-1].arena or books[0].arena,
        required_sections=sorted(set(required)),
        optional_sections=sorted(set(optional)),
        entries=list(merged_entries.values()),
        sections=sections,
    )


def select_codebooks(
    paths: Iterable[str | Path], *, project: str | None = None, arena: str | None = None
) -> list[Codebook]:
    selected: list[Codebook] = []
    for path in paths:
        book = load_codebook(path)
        if book.project and project and book.project != project:
            continue
        if book.arena and arena and book.arena != arena:
            continue
        selected.append(book)
    return selected


def seed_memory(codebook: Codebook, store, *, accepted: bool = True) -> list[str]:
    ids: list[str] = []
    for entry in codebook.entries:
        obj_id = stable_codebook_id(entry)
        existing = store.resolve(entry.label, entry.kind)
        if existing.decision != "EXISTING":
            store.create(
                obj_id,
                entry.kind,
                entry.label,
                provenance=entry.provenance,
                state="CANONICAL" if accepted else "PROVISIONAL",
            )
        for alias in entry.aliases:
            store.add_alias(obj_id, alias)
        ids.append(obj_id)
    return ids
