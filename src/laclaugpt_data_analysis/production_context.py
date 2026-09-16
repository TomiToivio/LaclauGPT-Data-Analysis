"""Resolve public-safe/default analysis-context policy for production runners."""
from __future__ import annotations

import os
from pathlib import Path

from .config import Settings
from .context_orchestration import AnalysisContextPolicy
from .periodic_summary import PeriodicSummaryRepository
from .rag import RetrievalBackend, backend_from_settings
from .storage import record_store


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _existing(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def default_project_context_path(project_id: str, project_profile: str = "generic") -> str | None:
    """Choose only public-safe project resources; private overlays are explicit/env-configured."""
    root = _repo_root() / "contexts" / "projects"
    value = (project_profile or project_id).casefold()
    if value == "ai26" or project_id.casefold() == "ai26":
        return _existing(root / "ai26_v1.md")
    if value == "ep24" or project_id.casefold() == "ep24":
        return _existing(root / "ep24_generic_v1.md")
    if value in {"hungary26", "hu26"} or project_id.casefold() in {"hungary26", "hu26"}:
        return _existing(root / "hungary26_generic_v1.md")
    return None


def production_context_policy(
    settings: Settings,
    *,
    project_profile: str = "generic",
) -> AnalysisContextPolicy:
    """Resolve context policy from explicit env overrides plus public-safe defaults."""
    root = _repo_root()
    project_path = os.getenv("LACLAUGPT_PROJECT_CONTEXT_PATH") or default_project_context_path(
        settings.project_id, project_profile
    )
    theory_path = os.getenv("LACLAUGPT_THEORY_CONTEXT_PATH") or _existing(
        root / "contexts" / "theory" / "evidence_first_v1.md"
    )
    profile = os.getenv("LACLAUGPT_CONTEXT_PROFILE", "high_accuracy").strip() or "high_accuracy"
    use_summary = os.getenv("LACLAUGPT_USE_PERIODIC_SUMMARY_CONTEXT", "1").strip().casefold()
    summary_enabled = use_summary not in {"0", "false", "no", "off"}
    policy = AnalysisContextPolicy(
        profile=profile,
        project_background_path=project_path,
        theory_path=theory_path,
    )
    if not summary_enabled:
        for stage in policy.stages.values():
            stage.use_situational_summary = False
    return policy


def production_summary_repository(settings: Settings) -> PeriodicSummaryRepository:
    return PeriodicSummaryRepository(record_store(settings, "periodic_summaries"))


def production_retrieval_backend(settings: Settings) -> RetrievalBackend | None:
    """Use configured RAG if enabled; ordinary analysis remains functional without it."""
    if not settings.rag_enabled:
        return None
    return backend_from_settings(settings)
