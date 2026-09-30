"""Human-readable Phase 1 analysis pipeline.

Open this package when you want to understand the scientific execution order.
Each major research step has its own module, while the older canonical_pipeline
module remains the compatibility engine for schemas, provenance, and validated
behaviour.
"""

from .runner import run_phase1_pipeline

__all__ = ["run_phase1_pipeline"]
