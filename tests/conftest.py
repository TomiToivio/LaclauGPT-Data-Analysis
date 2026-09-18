"""Test configuration for the repository.

The Phase 0 core lives in ``laclaugpt/`` as plain, hand-maintained scripts rather
than an installed package (see ``laclaugpt/README.md``). Its tests import those
modules directly, so the directory must be importable regardless of the directory
pytest is invoked from.
"""
from __future__ import annotations

import sys
from pathlib import Path

PHASE0_CORE = Path(__file__).resolve().parents[1] / "laclaugpt"
if PHASE0_CORE.is_dir() and str(PHASE0_CORE) not in sys.path:
    sys.path.insert(0, str(PHASE0_CORE))
