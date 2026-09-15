"""Composable execution, storage and LLM deployment profiles for Analysis."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

LOCAL_MODELS = {
    "gemma4:e2b",
    "gemma4:e4b",
    "gemma4:12b",
    "gemma4:26b",
    "gemma4:31b",
}
CLOUD_MODELS = {"gemma4:31b-cloud"}


@dataclass(frozen=True)
class DeploymentProfile:
    machine: str = "laptop"
    execution: str = "cli"
    storage: str = "local"
    llm: str = "local-ollama"
    model: str = "gemma4:e4b"
    cloud_allowed: bool = False
    data_dir: Path = Path("data")
    scratch_dir: Path | None = None
    collection_data_dir: Path | None = None
    ollama_endpoint: str = "http://127.0.0.1:11434"
    caller: str = "human-cli"

    def with_overrides(self, **changes: object) -> "DeploymentProfile":
        return replace(self, **changes)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.machine not in {"laptop", "roihu", "linux-server", "custom"}:
            errors.append(f"unsupported machine: {self.machine}")
        if self.execution not in {"cli", "slurm", "cron", "systemd", "agent", "custom"}:
            errors.append(f"unsupported execution: {self.execution}")
        if self.storage not in {"local", "distributed", "custom"}:
            errors.append(f"unsupported storage: {self.storage}")
        if self.llm not in {"local-ollama", "ollama-cloud", "custom"}:
            errors.append(f"unsupported llm mode: {self.llm}")
        if self.model in CLOUD_MODELS and not self.cloud_allowed:
            errors.append("cloud model requires explicit cloud_allowed=True")
        if self.llm == "ollama-cloud" and not self.cloud_allowed:
            errors.append("ollama-cloud requires explicit cloud_allowed=True")
        if self.model in CLOUD_MODELS and self.llm != "ollama-cloud":
            errors.append("cloud model requires llm='ollama-cloud'")
        if self.llm == "local-ollama" and self.model in CLOUD_MODELS:
            errors.append("local Ollama mode cannot select a cloud model")
        return errors

    def provenance_metadata(self) -> dict[str, object]:
        return {
            "machine": self.machine,
            "execution": self.execution,
            "storage": self.storage,
            "llm": self.llm,
            "model": self.model,
            "endpoint": self.ollama_endpoint,
            "cloud_allowed": self.cloud_allowed,
            "caller": self.caller,
        }


def laptop_local(data_dir: str | Path = "data") -> DeploymentProfile:
    return DeploymentProfile(data_dir=Path(data_dir), model="gemma4:e4b")


def laptop_cloud(data_dir: str | Path = "data") -> DeploymentProfile:
    return DeploymentProfile(
        data_dir=Path(data_dir),
        llm="ollama-cloud",
        model="gemma4:31b-cloud",
        cloud_allowed=True,
    )


def roihu(data_dir: str | Path = "data") -> DeploymentProfile:
    return DeploymentProfile(
        machine="roihu",
        execution="slurm",
        storage="local",
        llm="local-ollama",
        model="gemma4:26b",
        data_dir=Path(data_dir),
        caller="scheduler",
    )


def linux_server(data_dir: str | Path = "data", *, distributed: bool = False) -> DeploymentProfile:
    return DeploymentProfile(
        machine="linux-server",
        execution="cron",
        storage="distributed" if distributed else "local",
        llm="local-ollama",
        model="gemma4:12b",
        data_dir=Path(data_dir),
        caller="scheduler",
    )


def render_slurm(command: str, *, job_name: str = "laclaugpt-analysis") -> str:
    """Return a public-safe SLURM template without site/user/project identifiers."""
    return "\n".join(
        [
            "#!/bin/bash",
            f"#SBATCH --job-name={job_name}",
            "#SBATCH --gres=gpu:1",
            "#SBATCH --time=04:00:00",
            "# Add site-specific account/partition directives privately.",
            "set -euo pipefail",
            "mkdir -p data/logs data/runs data/tmp",
            command,
        ]
    )


def render_cron(command: str, *, minute: int = 0, hour: int = 3) -> str:
    return (
        f"{minute} {hour} * * * mkdir -p data/logs data/runs && "
        f"flock -n data/runs/analysis.lock {command} >> data/logs/analysis.log 2>&1"
    )


def render_systemd(command: str, *, working_directory: str | Path) -> dict[str, str]:
    wd = Path(working_directory)
    service = "\n".join(
        [
            "[Unit]",
            "Description=LaclauGPT Data Analysis",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={wd}",
            f"ExecStart={command}",
        ]
    )
    timer = "\n".join(
        [
            "[Unit]",
            "Description=Schedule LaclauGPT Data Analysis",
            "[Timer]",
            "OnCalendar=*-*-* 03:00:00",
            "Persistent=true",
            "[Install]",
            "WantedBy=timers.target",
        ]
    )
    return {"service": service, "timer": timer}
