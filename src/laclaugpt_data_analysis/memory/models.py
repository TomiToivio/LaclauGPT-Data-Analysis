"""Shared vocabulary for the persistent analysis memory.

Stable IDs, canonical kinds/states, surface normalisation and the MemoryRef
interchange reference. Migrated from ``laclaugpt_memory`` with identical ID
semantics: E entities, T topics, S signifiers, C targets, A actors, F
formations; states CANONICAL / PROVISIONAL / MERGED / DEPRECATED / REJECTED.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

KINDS: tuple[str, ...] = ("entity", "topic", "signifier", "target", "actor", "formation")
STATES: tuple[str, ...] = ("CANONICAL", "PROVISIONAL", "MERGED", "DEPRECATED", "REJECTED")
KIND_PREFIX = {"entity": "E", "topic": "T", "signifier": "S",
               "target": "C", "actor": "A", "formation": "F"}
KIND_BY_PREFIX = {v: k for k, v in KIND_PREFIX.items()}

# spaCy NER entity classes (2026-09-06 ruling): the closed type vocabulary
# stored in objects.kind_type for kind='entity'. Kept here so memory, prompts
# and adapters share one definition.
NER_TYPES: tuple[str, ...] = (
    "PERSON",       # People, including fictional
    "NORP",         # Nationalities or religious or political groups
    "FAC",          # Buildings, airports, highways, bridges, etc.
    "ORG",          # Companies, agencies, institutions, etc.
    "GPE",          # Countries, cities, states
    "LOC",          # Non-GPE locations, mountain ranges, bodies of water
    "PRODUCT",      # Objects, vehicles, foods, etc. (not services)
    "EVENT",        # Named hurricanes, battles, wars, sports events, etc.
    "WORK_OF_ART",  # Titles of books, songs, etc.
    "LAW",          # Named documents made into laws
    "LANGUAGE",     # Any named language
    "DATE",         # Absolute or relative dates or periods
    "TIME",         # Times smaller than a day
    "PERCENT",      # Percentage, including "%"
    "MONEY",        # Monetary values, including unit
    "QUANTITY",     # Measurements, as of weight or distance
    "ORDINAL",      # "first", "second", etc.
    "CARDINAL",     # Numerals that do not fall under another type
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_memory_dir() -> Path:
    """LACLAUGPT_MEMORY_DIR wins; else <data_dir>/memory."""
    env = None
    import os
    env = os.environ.get("LACLAUGPT_MEMORY_DIR")
    if env:
        return Path(env)
    return Path(os.environ.get("LACLAUGPT_DATA_DIR", "./var/data")) / "memory"


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Deterministic surface normalisation (the first anti-explosion gate)."""
    if not text:
        return ""
    t = text.strip()
    t = _strip_accents(t).casefold()
    t = " ".join(t.split())
    # strip trailing parenthetical annotations ("Sam Altman (OpenAI CEO)")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
    return t.strip(" \t\n.,;:!?\"'()[]{}")


def display_label(norm: str, kind: str) -> str:
    """Canonical display form: entities/actors Title Case, concepts lower."""
    if kind in ("entity", "actor"):
        return " ".join(w.capitalize() for w in norm.split())
    return norm


@dataclass(frozen=True)
class Candidate:
    """One retrieved candidate shown to the LLM resolver."""

    obj_id: str
    kind: str
    label: str
    state: str
    score: float          # best combined similarity 0..1
    via: str              # exact|alias|fuzzy|embedding|usage
    definition: str = ""


@dataclass(frozen=True)
class Resolution:
    """Outcome of one resolve() call."""

    raw: str
    kind: str
    obj_id: str = ""
    label: str = ""
    decision: str = ""    # EXISTING | NEW | UNCERTAIN
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