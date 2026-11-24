"""Apply the pinned merge registry to a record's labels (#311).

The registry decides what a label is *called*; the analysis decides what it *means*. So this module only
rewrites names, keeps the raw label beside the canonical one, and refuses to run when the registry it was
given cannot be trusted.

Two behaviours are deliberate and tested:

* a settled decision (``approved`` or ``keep_separate``) is applied; a ``proposed`` one is not, because
  applying unapproved mappings is how a proposal silently becomes the corpus;
* a run configured with a registry that is missing, corrupt or checksum-mismatched raises, rather than
  producing labels that look canonicalised and are not.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from ..merge_registry import ENV_PATH, ENV_SHA256, MergeRegistry

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..canonical import CanonicalRecord

__all__ = [
    "apply_configured_registry",
    "apply_merge_registry",
    "configured_registry",
    "registry_provenance",
]

logger = logging.getLogger(__name__)

#: Where the registry's name and version are recorded for a record that used it.
PROVENANCE_NAMESPACE = "merge_registry"


@lru_cache(maxsize=4)
def _load(path: str, expected: str | None) -> MergeRegistry:
    return MergeRegistry.load(path, expected_sha256=expected)


def configured_registry() -> MergeRegistry | None:
    """The registry this process was configured with, loaded once.

    Cached because a batch post-processes thousands of records and the file must not be re-hashed per
    record; keyed on the path and the pinned checksum so a changed environment reloads.
    """
    path = (os.environ.get(ENV_PATH) or "").strip()
    if not path:
        return None
    return _load(path, (os.environ.get(ENV_SHA256) or "").strip() or None)


def apply_configured_registry(record: CanonicalRecord) -> int:
    """Apply the configured registry to one record, or do nothing when canonicalisation is off.

    ``registry_from_env`` semantics are preserved: no path means off, a broken file means an exception, and
    an exception here is the point -- a run that believes it canonicalised must not emit raw labels.
    """
    registry = configured_registry()
    if registry is None:
        return 0
    return apply_merge_registry(record, registry)


def apply_merge_registry(record: CanonicalRecord, registry: MergeRegistry) -> int:
    """Canonicalise the record's entity, topic, theme and sentiment labels in place.

    Returns the number of labels that actually changed. Labels without a settled decision are untouched and
    keep their original text, which is the fail-closed default: an unreviewed label is not a merged label.
    """
    country = _country_hint(record)
    changed = 0
    touched: list[str] = []

    for entity in record.analysis.entities:
        resolution = registry.resolve(
            "person" if (entity.entity_type or "").casefold() == "person" else "entity",
            entity.label,
            country=country,
        )
        if resolution.applies:
            entity.aliases = sorted({*entity.aliases, entity.label})
            entity.label = resolution.canonical_label
            entity.review_status = "APPROVED"
            touched.append(f"{resolution.category}:{resolution.raw_label}")
            changed += 1

    for topic in record.analysis.topics:
        label = topic.canonical_label or topic.metadata.get("label", "")
        resolution = registry.resolve("topic", label, country=country)
        if resolution.applies:
            topic.metadata.update({"raw_label": label, **resolution.as_metadata()})
            topic.canonical_label = resolution.canonical_label
            touched.append(f"topic:{label}")
            changed += 1

    for item in record.analysis.themes:
        resolution = registry.resolve("theme", item.label, country=country)
        if resolution.applies:
            item.metadata.update(resolution.as_metadata())
            item.label = resolution.canonical_label
            item.review_status = "APPROVED"
            touched.append(f"theme:{resolution.raw_label}")
            changed += 1

    for item in record.analysis.sentiments:
        polarity = str(item.metadata.get("polarity") or "")
        resolution = registry.resolve("sentiment", item.label, country=country, polarity=polarity)
        if resolution.applies:
            item.metadata.update(resolution.as_metadata())
            item.label = resolution.canonical_label
            item.review_status = "APPROVED"
            touched.append(f"sentiment:{resolution.raw_label}")
            changed += 1

    if changed:
        _record_provenance(record, registry, changed)
    return changed


def registry_provenance(registry: MergeRegistry, applied: int) -> dict[str, object]:
    """The facts a manifest needs to say which registry a run consumed, and how much of it applied."""
    return {
        "registry_sha256": registry.sha256,
        "source": registry.source,
        "entries": len(registry.entries),
        "labels_canonicalised": applied,
    }


def _record_provenance(record: CanonicalRecord, registry: MergeRegistry, applied: int) -> None:
    record.analysis.plugin_results[PROVENANCE_NAMESPACE] = registry_provenance(registry, applied)


def _country_hint(record: CanonicalRecord) -> str:
    """The country the record belongs to, if the record states one.

    The registry scopes decisions by country because "the party" means different parties in different
    countries; guessing a country would apply the wrong scope, so an unknown country stays empty and only
    unscoped decisions will match.
    """
    for attribute in ("country", "country_code"):
        value = getattr(record, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
