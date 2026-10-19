"""Regression tests for the worker preflight that runs before the first claim (issue #372).

Upstream multimodal #292/#293: the Step 3 preflight did not notice a missing ``pymongo`` or
``redis``, so the job started and failed later, mid-run. AI26's shell wrapper already
checks the endpoint, the model, the private files and the composed settings, and
``preflight.py`` reports the store drivers — but the *worker* still imported the provider
lazily, so a missing ``ollama`` package only surfaced after a task had been claimed.
"""
from __future__ import annotations

import importlib.util

import pytest

from laclaugpt_data_analysis.distributed_worker import (
    AI26_MODEL,
    FrozenRunManifest,
    enforce_local_model,
)


def _manifest() -> FrozenRunManifest:
    return FrozenRunManifest(
        project_id="ai26",
        run_id="ai26-run",
        schema_version="x",
        config_sha256="config",
        codebook_sha256="codebook",
        model=AI26_MODEL,
        public_git_sha="sha",
    )


def test_a_missing_provider_dependency_fails_before_any_task_is_claimed(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "local")
    real_find_spec = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name == "ollama":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)

    with pytest.raises(ValueError, match="ollama package is required"):
        enforce_local_model(_manifest())


def test_an_installed_provider_dependency_passes(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "local")
    monkeypatch.setenv("LACLAUGPT_LLM_MODEL", AI26_MODEL)
    monkeypatch.setenv("LLM_ALLOW_CLOUD_FALLBACK", "0")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: object())

    enforce_local_model(_manifest())  # must not raise


def test_cloud_mode_is_still_refused_before_claiming(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "cloud")
    monkeypatch.delenv("LACLAUGPT_LLM_MODE", raising=False)

    with pytest.raises(ValueError, match="forbids cloud/external"):
        enforce_local_model(_manifest())
