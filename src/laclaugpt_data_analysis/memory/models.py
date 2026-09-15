"""Shared vocabulary for the persistent analysis memory.

Stable IDs, canonical kinds/states, surface normalisation and the MemoryRef
interchange reference. Migrated from ``laclaugpt_memory`` with identical ID
semantics: E entities, T topics, S signifiers, C targets, A actors, F
formations; states CANONICAL / PROVISIONAL / MERGED / DEPRECATED / REJECTED.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

KINDS: tuple[str, ...] = ("entity", "topic", "signifier", "target", "actor", "formation")
STATES: tuple[str, ...] = ("CANONICAL", "PROVISIONAL", "MERGED", "DEPRECATED", "REJECTED")
KIND_PREFIX = {
    "entity": "E",
    "topic": "T",
    "signifier": "S",
    "target": "C",
    "actor": "A",
    "formation": "F",
}
KIND_BY_PREFIX = {value: key for key, value in KIND_PREFIX.items()}

NER_TYPES: tuple[str, ...] = (
    "PERSON",
    "NORP",
    "FAC",
    "ORG",
    "GPE",
    "LOC",
    "PRODUCT",
    "EVENT",
    "WORK_OF_ART",
    "LAW",
    "LANGUAGE",
    "DATE",
    "TIME",
    "PERCENT",
    "MONEY",
    "QUANTITY",
    "ORDINAL",
    "CARDINAL",
)

NER_TYPES_DESCRIPTION = {
    "PERSON": "People, including fictional",
    "NORP": "Nationalities or religious or political groups",
    "FAC": "Buildings, airports, highways, bridges, etc.",
    "ORG": "Companies, agencies, institutions, etc.",
    "GPE": "Countries, cities, states",
    "LOC": "Non-GPE locations, mountain ranges, bodies of water",
    "PRODUCT": "Objects, vehicles, foods, etc. (not services)",
    "EVENT": "Named hurricanes, battles, wars, sports events, etc.",
    "WORK_OF_ART": "Titles of books, songs, etc.",
    "LAW": "Named documents made into laws",
    "LANGUAGE": "Any named language",
    "DATE": "Absolute or relative dates or periods",
    "TIME": "Times smaller than a day",
    "PERCENT": "Percentage, including \"%\"",
    "MONEY": "Monetary values, including unit",
    "QUANTITY": "Measurements, as of weight or distance",
    "ORDINAL": "\"first\", \"second\", etc.",
    "CARDINAL": "Numerals that do not fall under another type",
}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_memory_dir() -> Path:
    """LACLAUGPT_MEMORY_DIR wins; otherwise use the private data root."""
    configured = os.environ.get("LACLAUGPT_MEMORY_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ.get("LACLAUGPT_DATA_DIR", "./data")) / "memory"


def _strip_accents(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def normalize(text: str) -> str:
    """Deterministic surface normalisation (the first anti-explosion gate)."""
    if not text:
        return ""
    normalized = _strip_accents(text.strip()).casefold()
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"\s*\([^)]*\)\s*$", "", normalized).strip()
    return normalized.strip(" \t\n.,;:!?\"'()[]{}")


def display_label(norm: str, kind: str) -> str:
    """Canonical display form: entities/actors Title Case, concepts lower."""
    if kind in ("entity", "actor"):
        return " ".join(word.capitalize() for word in norm.split())
    return norm


@dataclass(frozen=True)
class Candidate:
    """One retrieved candidate shown to the LLM resolver."""

    obj_id: str
    kind: str
    label: str
    state: str
    score: float
    via: str
    definition: str = ""


@dataclass(frozen=True)
class Resolution:
    """Outcome of one resolve() call."""

    raw: str
    kind: str
    obj_id: str = ""
    label: str = ""
    decision: str = ""
    matched_via: str = ""
    score: float = 0.0


class MemoryRef:
    """Stable reference to a canonical memory object (interchange type)."""

    __slots__ = ("obj_id", "label", "kind", "raw")

    def __init__(self, obj_id: str, label: str, kind: str, raw: str = ""):
        self.obj_id = obj_id
        self.label = label
        self.kind = kind
        self.raw = raw

    def __repr__(self) -> str:
        return f"MemoryRef({self.obj_id}={self.label!r})"

    def __eq__(self, other) -> bool:
        return isinstance(other, MemoryRef) and self.obj_id == other.obj_id

    def __hash__(self) -> int:
        return hash(self.obj_id)
