"""Readable incoming/outgoing database boundary for the hand-written pipeline."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pipeline_models import AnalysisBundle, HumanPipelineRecord


class IncomingRecords(Protocol):
    def pending(self, project: str, limit: int | None = None) -> Iterable[HumanPipelineRecord]:
        """Yield records that still need the requested analysis run."""


class OutgoingResults(Protocol):
    def save(self, bundle: AnalysisBundle) -> None:
        """Persist one validated result bundle without changing source_url identity."""


def read_pending(
    source: IncomingRecords, project: str, limit: int | None = None
) -> Iterable[HumanPipelineRecord]:
    """Small seam between storage adapters and the seven readable analysis steps."""
    return source.pending(project=project, limit=limit)


def write_result(destination: OutgoingResults, bundle: AnalysisBundle) -> None:
    """Persist through an adapter; database-specific code stays outside the steps."""
    destination.save(bundle)
