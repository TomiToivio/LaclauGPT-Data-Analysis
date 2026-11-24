"""Consume the pinned label-merge registry (#311).

The registry is the one durable record of what a label in this corpus is called: it is written by the
curation tooling (``dashboards/ep24_merge_lab`` in the visualization repository, with the review evidence
kept in the private repository) and consumed here. This module is the **consumer adapter**, not a second
registry: it reads the same JSONL schema, applies the same precedence and the same fail-closed rules, and
records the version it consumed.

Three rules matter more than the code:

* **Only settled decisions rewrite output.** ``approved`` and ``keep_separate`` apply; ``proposed``,
  ``rejected`` and ``superseded`` do not. Applying a proposal would let one reviewer's guess reseal the
  whole corpus, which is exactly what the review queue exists to prevent.
* **A configured registry that cannot be read is an error, not a fallback.** If a run is told to canonicalise
  and the file is missing, corrupt, unvalidated or does not match its pinned checksum, the run fails. Silent
  fallback produces outputs whose labels look canonicalised but are not, and nothing downstream can tell.
* **The raw label survives.** A canonical label is written alongside the original, never instead of it, so a
  decision can be revisited and a wrong merge stays reversible.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "CATEGORIES",
    "MergeRegistry",
    "RegistryEntry",
    "RegistryUnavailable",
    "Resolution",
    "SETTLED_STATUSES",
    "STATUSES",
    "registry_from_env",
]

CATEGORIES = ("entity", "person", "theme", "topic", "sentiment")
STATUSES = ("approved", "proposed", "rejected", "keep_separate", "superseded")
SETTLED_STATUSES = ("approved", "keep_separate")

#: The fields a registry line may carry. Unknown fields are tolerated (the producing tool may add one), but
#: these must be understood, and a test pins the set so a silent schema drift fails here rather than later.
ENTRY_FIELDS = (
    "category",
    "alias",
    "canonical",
    "status",
    "canonical_id",
    "wiki_title",
    "wiki_url",
    "wikidata_qid",
    "fallback_reason",
    "polarity",
    "scope",
    "evidence",
    "reviewers",
    "method",
    "decision",
    "created_at",
    "revision",
    "supersedes",
)

ENV_PATH = "LACLAUGPT_MERGE_REGISTRY"
ENV_SHA256 = "LACLAUGPT_MERGE_REGISTRY_SHA256"


class RegistryUnavailable(RuntimeError):
    """A registry was configured but cannot be trusted; the run must not canonicalise labels."""


@dataclass(frozen=True)
class RegistryEntry:
    category: str
    alias: str
    canonical: str
    status: str
    canonical_id: str = ""
    wiki_url: str = ""
    wikidata_qid: str = ""
    polarity: str = ""
    country: str = ""
    language: str = ""
    source: str = ""
    reviewers: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    revision: int = 1
    supersedes: str = ""

    @property
    def specificity(self) -> int:
        return sum(1 for part in (self.country, self.language, self.source) if part)

    def matches_scope(self, *, country: str, language: str, source: str) -> bool:
        for wanted, given in (
            (self.country, country),
            (self.language, language),
            (self.source, source),
        ):
            if wanted and wanted.casefold() != (given or "").casefold():
                return False
        return True

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> RegistryEntry:
        scope = payload.get("scope") or {}
        if not isinstance(scope, Mapping):
            raise RegistryUnavailable(f"scope is not an object on alias {payload.get('alias')!r}")
        return cls(
            category=str(payload.get("category") or ""),
            alias=str(payload.get("alias") or ""),
            canonical=str(payload.get("canonical") or ""),
            status=str(payload.get("status") or ""),
            canonical_id=str(payload.get("canonical_id") or ""),
            wiki_url=str(payload.get("wiki_url") or ""),
            wikidata_qid=str(payload.get("wikidata_qid") or ""),
            polarity=str(payload.get("polarity") or ""),
            country=str(scope.get("country") or ""),
            language=str(scope.get("language") or ""),
            source=str(scope.get("source") or ""),
            reviewers=tuple(str(v) for v in (payload.get("reviewers") or ())),
            evidence=tuple(str(v) for v in (payload.get("evidence") or ())),
            revision=int(payload.get("revision") or 1),
            supersedes=str(payload.get("supersedes") or ""),
        )

    def problems(self) -> list[str]:
        """Why this line cannot be trusted, in the words an operator can act on."""
        out: list[str] = []
        if self.category not in CATEGORIES:
            out.append(f"unknown category {self.category!r}")
        if not self.alias.strip():
            out.append("empty alias")
        if self.status not in STATUSES:
            out.append(f"unknown status {self.status!r}")
        if self.status in SETTLED_STATUSES and not self.canonical.strip():
            out.append("settled decision without a canonical label")
        if self.status == "keep_separate" and self.canonical.strip() != self.alias.strip():
            out.append("keep_separate must point at the alias itself")
        if self.status == "approved" and len(set(self.reviewers)) < 3:
            out.append(f"approved with {len(set(self.reviewers))} reviewer(s); three are required")
        if self.status == "approved" and not self.evidence:
            out.append("approved without evidence")
        if self.category == "sentiment" and self.status in SETTLED_STATUSES and not self.polarity:
            out.append("sentiment decision without polarity")
        return out


@dataclass(frozen=True)
class Resolution:
    """What the registry says about one label, and whether the caller may rewrite it."""

    raw_label: str
    canonical_label: str
    canonical_id: str
    status: str
    registry_sha256: str
    category: str

    @property
    def applies(self) -> bool:
        return self.status in SETTLED_STATUSES and self.canonical_label != self.raw_label

    def as_metadata(self) -> dict[str, str]:
        return {
            "registry_sha256": self.registry_sha256,
            "registry_status": self.status,
            "raw_label": self.raw_label,
            **({"canonical_id": self.canonical_id} if self.canonical_id else {}),
        }


class MergeRegistry:
    """A validated, checksum-pinned view of the registry file."""

    def __init__(self, entries: list[RegistryEntry], *, sha256: str, source: str = "") -> None:
        self.entries = entries
        self.sha256 = sha256
        self.source = source
        # Collapse revisions per identity, keeping the highest revision; superseded lines are history, not
        # decisions. Two *different* identities may share an alias (one per scope), and those must both
        # survive so that an equally specific disagreement is visible as a disagreement.
        # Group by identity and keep only the highest revision. Two entries at the *same* revision that
        # disagree are both kept, so the conflict surfaces at resolution time instead of one silently
        # overwriting the other -- a correction carries a higher revision, a contradiction carries the same.
        groups: dict[tuple[str, str, str, str, str, str], list[RegistryEntry]] = {}
        for entry in entries:
            if entry.status == "superseded":
                continue
            key = (
                entry.category,
                entry.alias.strip().casefold(),
                entry.polarity.casefold(),
                entry.country.casefold(),
                entry.language.casefold(),
                entry.source.casefold(),
            )
            groups.setdefault(key, []).append(entry)
        in_force: list[RegistryEntry] = []
        for group in groups.values():
            top = max(entry.revision for entry in group)
            in_force.extend(entry for entry in group if entry.revision == top)
        self._in_force = in_force

    @classmethod
    def load(cls, path: str | Path, *, expected_sha256: str | None = None) -> MergeRegistry:
        target = Path(path)
        if not target.exists():
            raise RegistryUnavailable(f"merge registry not found: {target}")
        raw = target.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise RegistryUnavailable(
                f"merge registry checksum mismatch: expected {expected_sha256[:12]}, file is {digest[:12]}"
            )
        entries: list[RegistryEntry] = []
        problems: list[str] = []
        for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RegistryUnavailable(f"{target.name}:{number}: not JSON ({exc})") from exc
            if not isinstance(payload, Mapping):
                raise RegistryUnavailable(f"{target.name}:{number}: not a registry object")
            entry = RegistryEntry.from_json(payload)
            problems.extend(
                f"{entry.category}/{entry.alias}: {problem}" for problem in entry.problems()
            )
            entries.append(entry)
        if problems:
            raise RegistryUnavailable("; ".join(problems[:5]))
        if not entries:
            raise RegistryUnavailable(f"merge registry is empty: {target}")
        return cls(entries, sha256=digest, source=str(target))

    def latest(self, category: str, alias: str, **context: str) -> RegistryEntry | None:
        """The single in-force decision for this alias, or ``None`` when absent or contradictory."""
        resolution = self.resolve(category, alias, **context)
        if resolution.status not in SETTLED_STATUSES:
            return None
        return next(
            (
                entry
                for entry in self._in_force
                if entry.category == category
                and entry.alias.strip().casefold() == (alias or "").strip().casefold()
                and entry.status == resolution.status
                and (entry.canonical or alias) == resolution.canonical_label
            ),
            None,
        )

    def resolve(
        self,
        category: str,
        alias: str,
        *,
        country: str = "",
        language: str = "",
        source: str = "",
        polarity: str = "",
    ) -> Resolution:
        if category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r}")
        folded = (alias or "").strip().casefold()
        candidates = [
            entry
            for entry in self._in_force
            if entry.category == category
            and entry.alias.strip().casefold() == folded
            and entry.matches_scope(country=country, language=language, source=source)
            and (
                category != "sentiment"
                or (polarity and entry.polarity.casefold() in {polarity.casefold(), "*"})
            )
        ]
        if not candidates:
            return Resolution(alias, alias, "", "unresolved", self.sha256, category)
        if category == "sentiment":
            exact = [entry for entry in candidates if entry.polarity.casefold() != "*"]
            if exact:
                candidates = exact
        widest = max(entry.specificity for entry in candidates)
        best = [entry for entry in candidates if entry.specificity == widest]
        decided = {(entry.status, entry.canonical, entry.canonical_id) for entry in best}
        if len(decided) != 1:
            # Two equally specific decisions disagree: that is a review matter, and rewriting the label would
            # pick a winner the evidence does not.
            return Resolution(alias, alias, "", "review", self.sha256, category)
        entry = best[0]
        canonical = entry.canonical or alias if entry.status in SETTLED_STATUSES else alias
        return Resolution(alias, canonical, entry.canonical_id, entry.status, self.sha256, category)


def registry_from_env(environ: Mapping[str, str] | None = None) -> MergeRegistry | None:
    """The registry this process was told to use, or ``None`` when canonicalisation is off.

    ``None`` means "this run does not canonicalise labels". A path that is set but unusable raises: that
    distinction is the whole fail-closed contract.
    """
    env = os.environ if environ is None else environ
    path = (env.get(ENV_PATH) or "").strip()
    if not path:
        return None
    expected = (env.get(ENV_SHA256) or "").strip() or None
    return MergeRegistry.load(path, expected_sha256=expected)
