"""Auditable agent-facing operations layered over canonical Analysis APIs."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..canonical import CanonicalRecord
from ..deployment import DeploymentProfile


class AnalysisRunner(Protocol):
    def plan(self, profile: DeploymentProfile) -> dict[str, object]: ...
    def run(self, profile: DeploymentProfile) -> dict[str, object]: ...
    def status(self, run_id: str) -> dict[str, object]: ...
    def resume(self, run_id: str) -> dict[str, object]: ...
    def export(self, run_id: str, destination: Path) -> dict[str, object]: ...


@dataclass(frozen=True)
class AgentPlan:
    dry_run: bool
    caller: str
    profile: dict[str, object]


def inspect_effective_profile(profile: DeploymentProfile) -> dict[str, object]:
    """Return a redacted, serializable profile summary."""
    endpoint = profile.ollama_endpoint
    if "@" in endpoint:
        scheme, rest = endpoint.split("://", 1) if "://" in endpoint else ("", endpoint)
        host = rest.split("@", 1)[-1]
        endpoint = f"{scheme}://***@{host}" if scheme else f"***@{host}"
    return {
        **profile.provenance_metadata(),
        "endpoint": endpoint,
        "data_dir": str(profile.data_dir),
        "scratch_dir": str(profile.scratch_dir) if profile.scratch_dir else None,
        "collection_data_dir": (
            str(profile.collection_data_dir) if profile.collection_data_dir else None
        ),
    }


def validate_environment(profile: DeploymentProfile) -> dict[str, object]:
    errors = profile.validate()
    return {
        "ok": not errors,
        "errors": errors,
        "data_dir": str(profile.data_dir),
        "data_dir_private": profile.data_dir.name == "data" or "data" in profile.data_dir.parts,
        "cloud_allowed": profile.cloud_allowed,
    }


def discover_ollama_models(endpoint: str = "http://127.0.0.1:11434") -> list[str]:
    """Explicit runtime probe. Never called at import time or by dry-run planning."""
    try:
        result = subprocess.run(
            ["curl", "-fsS", f"{endpoint.rstrip('/')}/api/tags"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return []
        payload = json.loads(result.stdout or "{}")
        return sorted(str(row.get("name")) for row in payload.get("models", []) if row.get("name"))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def plan_analysis(profile: DeploymentProfile, runner: AnalysisRunner | None = None) -> AgentPlan:
    """Plan an agent-triggered run without executing analysis or contacting services."""
    agent_profile = profile.with_overrides(execution="agent", caller="hermes-agent")
    errors = agent_profile.validate()
    if errors:
        raise ValueError("; ".join(errors))
    if runner is not None:
        runner.plan(agent_profile)
    return AgentPlan(
        dry_run=True,
        caller="hermes-agent",
        profile=inspect_effective_profile(agent_profile),
    )


def launch_analysis(profile: DeploymentProfile, runner: AnalysisRunner) -> dict[str, object]:
    agent_profile = profile.with_overrides(execution="agent", caller="hermes-agent")
    errors = agent_profile.validate()
    if errors:
        raise ValueError("; ".join(errors))
    return runner.run(agent_profile)


def inspect_run(run_id: str, runner: AnalysisRunner) -> dict[str, object]:
    return runner.status(run_id)


def resume_run(run_id: str, runner: AnalysisRunner) -> dict[str, object]:
    return runner.resume(run_id)


def export_results(run_id: str, destination: str | Path, runner: AnalysisRunner) -> dict[str, object]:
    path = Path(destination)
    if "data" not in path.parts:
        raise ValueError("agent exports must stay under the private data/ runtime boundary")
    return runner.export(run_id, path)


def stamp_agent_provenance(record: CanonicalRecord, profile: DeploymentProfile) -> CanonicalRecord:
    """Mark a canonical record as agent-triggered without changing its source identity."""
    source_url = record.source_url
    agent_profile = profile.with_overrides(execution="agent", caller="hermes-agent")
    record.append_analysis_provenance(
        method="analysis-execution",
        model=agent_profile.model,
        metadata=agent_profile.provenance_metadata(),
    )
    if record.source_url != source_url:
        raise RuntimeError("deployment metadata must not mutate canonical source identity")
    record.analysis.model_runs.append(
        {
            "model": agent_profile.model,
            "backend": agent_profile.llm,
            "endpoint": agent_profile.ollama_endpoint,
            "execution": agent_profile.execution,
            "machine": agent_profile.machine,
            "caller": agent_profile.caller,
            "cloud_allowed": agent_profile.cloud_allowed,
        }
    )
    return record
