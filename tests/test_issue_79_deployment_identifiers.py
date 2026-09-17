from pathlib import Path

from laclaugpt_data_analysis.config import load_settings
from laclaugpt_data_analysis.deployment import DeploymentProfile

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_identifiers_are_open_not_hard_coded() -> None:
    profile = DeploymentProfile(
        machine="laskin",
        execution="research-cron",
        storage="shared-ai26",
        llm="local-custom-runtime",
    )

    assert profile.validate() == []
    assert profile.provenance_metadata()["machine"] == "laskin"
    assert profile.provenance_metadata()["execution"] == "research-cron"


def test_empty_deployment_identifiers_are_still_rejected() -> None:
    profile = DeploymentProfile(machine="", execution="", storage="", llm="")

    assert profile.validate() == [
        "machine must not be empty",
        "execution must not be empty",
        "storage must not be empty",
        "llm mode must not be empty",
    ]


def test_load_settings_accepts_laskin_identity_and_preserves_provenance(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LACLAUGPT_MACHINE", "laskin")
    monkeypatch.setenv("LACLAUGPT_EXECUTION", "cron")
    monkeypatch.setenv("LACLAUGPT_STORAGE", "distributed")
    monkeypatch.setenv("LACLAUGPT_DATA_DIR", str(tmp_path / "data"))

    settings = load_settings()

    assert settings.machine == "laskin"
    assert settings.deployment_profile.validate() == []
    assert settings.deployment_profile.provenance_metadata()["machine"] == "laskin"


def test_laskin_runtime_templates_use_laskin_identity() -> None:
    wrapper = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    env_example = (ROOT / "deployment" / "ai26.laskin.env.example").read_text(encoding="utf-8")

    assert "LACLAUGPT_MACHINE=${LACLAUGPT_MACHINE:-laskin}" in wrapper
    assert "LACLAUGPT_MACHINE=laskin" in env_example
    assert "LACLAUGPT_MACHINE=linux-server" not in env_example
