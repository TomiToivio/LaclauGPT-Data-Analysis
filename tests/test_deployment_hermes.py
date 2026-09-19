from pathlib import Path

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.deployment import (
    DeploymentProfile,
    laptop_cloud,
    laptop_local,
    linux_server,
    render_cron,
    render_slurm,
    render_systemd,
    roihu,
)
from laclaugpt_data_analysis.integrations.hermes import (
    discover_ollama_models,
    export_results,
    inspect_effective_profile,
    launch_analysis,
    plan_analysis,
    stamp_agent_provenance,
    validate_environment,
)
from laclaugpt_data_analysis.llm.routing import resolve_profile_model


class FakeRunner:
    def __init__(self) -> None:
        self.last_profile = None

    def plan(self, profile):
        self.last_profile = profile
        return {"planned": True}

    def run(self, profile):
        self.last_profile = profile
        return {"run_id": "synthetic-run", "status": "completed"}

    def status(self, run_id):
        return {"run_id": run_id, "status": "completed"}

    def resume(self, run_id):
        return {"run_id": run_id, "status": "resumed"}

    def export(self, run_id, destination):
        return {"run_id": run_id, "destination": str(destination)}


def test_named_profiles_are_composable_and_overrideable() -> None:
    laptop = laptop_local()
    hpc = roihu()
    server = linux_server(distributed=True)
    assert (laptop.machine, laptop.execution, laptop.storage, laptop.model) == (
        "laptop",
        "cli",
        "local",
        "gemma4:e4b",
    )
    assert (hpc.machine, hpc.execution, hpc.model) == ("roihu", "slurm", "gemma4:26b")
    assert (server.machine, server.execution, server.storage, server.model) == (
        "linux-server",
        "cron",
        "distributed",
        "gemma4:12b",
    )
    custom = hpc.with_overrides(storage="distributed", model="gemma4:31b")
    assert custom.storage == "distributed"
    assert custom.model == "gemma4:31b"
    assert custom.validate() == []


def test_cloud_is_explicit_and_never_a_silent_fallback() -> None:
    forbidden = DeploymentProfile(model="gemma4:31b-cloud", llm="ollama-cloud")
    assert forbidden.validate()
    with pytest.raises(ValueError):
        resolve_profile_model(forbidden)

    allowed = laptop_cloud()
    assert allowed.cloud_allowed is True
    assert resolve_profile_model(allowed) == "gemma4:31b-cloud"
    assert resolve_profile_model(laptop_local()) != "gemma4:31b-cloud"


def test_all_documented_gemma4_tags_can_be_selected_explicitly() -> None:
    for tag in ("gemma4:e2b", "gemma4:e4b", "gemma4:12b", "gemma4:26b", "gemma4:31b"):
        profile = laptop_local().with_overrides(model=tag)
        assert resolve_profile_model(profile) == tag


def test_scheduler_templates_are_offline_and_placeholder_safe() -> None:
    slurm = render_slurm("python -m laclaugpt_data_analysis.pipeline")
    assert "#SBATCH --gres=gpu:1" in slurm
    assert "/scratch/" not in slurm
    assert "project_" not in slurm
    assert "data/logs" in slurm

    cron = render_cron("python -m laclaugpt_data_analysis.pipeline")
    assert "data/runs/analysis.lock" in cron
    assert "data/logs/analysis.log" in cron

    units = render_systemd(
        "python -m laclaugpt_data_analysis.pipeline",
        working_directory=Path("/opt/laclaugpt-analysis"),
    )
    assert "Persistent=true" in units["timer"]
    assert "ExecStart=python -m laclaugpt_data_analysis.pipeline" in units["service"]


def test_hermes_dry_run_uses_same_profile_validation_and_redacts_endpoint() -> None:
    runner = FakeRunner()
    profile = laptop_local().with_overrides(
        ollama_endpoint="http://user:credential@example.invalid:11434"
    )
    summary = inspect_effective_profile(profile)
    assert "credential" not in str(summary)
    assert validate_environment(profile)["ok"] is True

    plan = plan_analysis(profile, runner)
    assert plan.dry_run is True
    assert plan.caller == "hermes-agent"
    assert runner.last_profile.execution == "agent"
    assert runner.last_profile.caller == "hermes-agent"


def test_hermes_launch_and_export_use_injected_canonical_runner() -> None:
    runner = FakeRunner()
    result = launch_analysis(linux_server(), runner)
    assert result["run_id"] == "synthetic-run"
    assert runner.last_profile.caller == "hermes-agent"
    assert runner.last_profile.execution == "agent"
    exported = export_results("synthetic-run", "data/exports/result.jsonl", runner)
    assert exported["destination"] == "data/exports/result.jsonl"
    with pytest.raises(ValueError):
        export_results("synthetic-run", "/tmp/result.jsonl", runner)


def test_agent_provenance_preserves_canonical_identity() -> None:
    record = CanonicalRecord(source_url="https://example.invalid/post/1")
    original = record.canonical_dict()
    result = stamp_agent_provenance(record, roihu())
    assert result.source_url == original["source_url"]
    model_run = result.analysis.model_runs[-1]
    assert model_run["caller"] == "hermes-agent"
    assert model_run["execution"] == "agent"
    assert model_run["model"] == "gemma4:26b"
    assert result.provenance[-1].metadata["machine"] == "roihu"


def test_runtime_defaults_remain_under_data_contract() -> None:
    for profile in (laptop_local(), laptop_cloud(), roihu(), linux_server()):
        assert profile.data_dir == Path("data")
        assert "data" in profile.data_dir.parts


def test_discover_ollama_models_rejects_remote_endpoint(monkeypatch) -> None:
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run for remote endpoints")

    monkeypatch.setattr("laclaugpt_data_analysis.integrations.hermes.subprocess.run", fake_run)
    assert discover_ollama_models("https://example.invalid:11434") == []
    assert discover_ollama_models("http://169.254.169.254/latest/meta-data") == []
    assert called is False
