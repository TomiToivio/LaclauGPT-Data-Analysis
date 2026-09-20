"""Canonical Phase 1 AI26 runtime policy used by the Laskin deployment.

This module is the bridge between the research-protocol resources introduced for
Phase 1 and the older distributed worker/deployment code.  Operational code must
read study semantics from this policy rather than copy values into Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from types import MappingProxyType
from typing import Any

from .phase1_protocol import compose_protocol, load_mapping


_RESOURCE_ROOT = resources.files("laclaugpt_data_analysis").joinpath("resources", "phase1")
_DEFAULTS = _RESOURCE_ROOT.joinpath("defaults.yaml")
_AI26 = _RESOURCE_ROOT.joinpath("ai26.yaml")
_CODEBOOK = _RESOURCE_ROOT.joinpath("phase1_v1.yaml")

_REPORT_DIMENSIONS = (
    "signifier",
    "formation",
    "author",
    "arena",
    "language",
    "region",
    "topic",
)


@dataclass(frozen=True, slots=True)
class AI26RuntimePolicy:
    study_id: str
    phase: str
    date_after: str | None
    report_enabled: bool
    report_interval_hours: int
    report_group_by: tuple[str, ...]
    stages: MappingProxyType
    config_revision: str
    codebook_revision: str

    def provenance(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "study_id": self.study_id,
            "phase1_config_revision": self.config_revision,
            "phase1_codebook_revision": self.codebook_revision,
            "phase1_date_after": self.date_after or "",
            "phase1_report_interval_hours": self.report_interval_hours,
        }


def _normalise_boundary(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=UTC)
    return candidate.astimezone(UTC).isoformat()


def load_ai26_runtime_policy() -> AI26RuntimePolicy:
    """Load the packaged canonical AI26 Phase 1 policy deterministically."""
    protocol = compose_protocol(
        defaults=load_mapping(_DEFAULTS),
        profile=load_mapping(_AI26),
        codebooks=[load_mapping(_CODEBOOK)],
    )
    if protocol.study_id != "ai26":
        raise ValueError(f"canonical Laskin runtime requires study_id=ai26, got {protocol.study_id!r}")
    if protocol.config.get("phase") != "phase-1":
        raise ValueError("canonical Laskin runtime requires phase=phase-1")

    reports = protocol.config.get("periodic_reports", {})
    metadata = protocol.config.get("metadata", {})
    configured_dimensions = set(metadata.get("dimensions", ()))
    group_by = tuple(item for item in _REPORT_DIMENSIONS if item in configured_dimensions)

    interval = int(reports.get("interval_hours", 24))
    if interval < 1:
        raise ValueError("periodic_reports.interval_hours must be positive")

    return AI26RuntimePolicy(
        study_id=protocol.study_id,
        phase=str(protocol.config["phase"]),
        date_after=_normalise_boundary(protocol.config.get("filters", {}).get("date_after")),
        report_enabled=bool(reports.get("enabled", False)),
        report_interval_hours=interval,
        report_group_by=group_by,
        stages=protocol.config["stages"],
        config_revision=protocol.config_hash,
        codebook_revision=protocol.codebook_hash,
    )
