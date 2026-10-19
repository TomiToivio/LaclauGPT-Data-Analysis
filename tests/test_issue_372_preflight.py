"""Regression coverage for multimodal-inspired AI26 backend preflight (#372)."""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.preflight import _configured_backend_problems


@pytest.mark.parametrize("backend", ["mongodb", "redis"])
@pytest.mark.parametrize("reachable,error", [
    (None, "driver_not_installed"),
    (None, None),
    (False, "ConnectionFailure"),
])
def test_configured_backend_must_be_proven_reachable(
    backend: str, reachable: bool | None, error: str | None
) -> None:
    checks = {
        "mongodb": {"configured": False, "reachable": None},
        "redis": {"configured": False, "reachable": None},
    }
    checks[backend] = {"configured": True, "reachable": reachable, "error": error}
    result = _configured_backend_problems(checks)
    assert len(result) == 1
    assert result[0].startswith(f"{backend} unavailable: ")
    assert result[0].endswith(error or "not_verified")


def test_healthy_and_unconfigured_backends_do_not_block() -> None:
    assert _configured_backend_problems({
        "mongodb": {"configured": True, "reachable": True},
        "redis": {"configured": False, "reachable": None},
    }) == []
    assert _configured_backend_problems({
        "mongodb": {"configured": False, "reachable": None},
        "redis": {"configured": True, "reachable": True},
    }) == []
