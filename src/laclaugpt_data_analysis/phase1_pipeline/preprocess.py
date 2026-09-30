"""Step 1: preprocess one canonical source record.

This stage prepares derived material without changing the meaning of the source.
Project-specific media extraction can be supplied through the existing
preprocessor callback. The source record, raw metadata, and legacy fields remain
preserved for auditability and backwards compatibility.
"""
from __future__ import annotations

from ..canonical import CanonicalRecord
from ..canonical_pipeline import Preprocessor, preprocess_record


def run_preprocess(
    record: CanonicalRecord,
    *,
    preprocessor: Preprocessor | None = None,
) -> CanonicalRecord:
    """Prepare text/media derivatives and record the preprocessing contract."""
    return preprocess_record(record, preprocessor=preprocessor)
