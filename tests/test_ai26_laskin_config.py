"""AI26 + Laskin + cron configuration composition (public templates).

These tests pin the issue #65 acceptance criteria that can be checked offline:
the composed configuration must resolve the local model, the local Ollama mode
and the configured endpoint, and must not leak private paths into provenance.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from laclaugpt_data_analysis.runtime_config import compose_run_config_from_files

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "config" / "projects" / "ai26.yaml"
MACHINE = ROOT / "config" / "machines" / "laskin.yaml"
EXECUTION = ROOT / "config" / "execution" / "laskin-cron.yaml"


def _compose():
    return compose_run_config_from_files(
        project="ai26",
        project_path=PROJECT,
        machine="laskin",
        machine_path=MACHINE,
        execution="cron",
        execution_path=EXECUTION,
    )


def test_all_three_public_layers_exist() -> None:
    for path in (PROJECT, MACHINE, EXECUTION):
        assert path.is_file(), path


def test_composition_identity_and_hash() -> None:
    effective = _compose()
    assert effective.project == "ai26"
    assert effective.machine == "laskin"
    assert effective.execution == "cron"
    assert len(effective.config_hash) == 64
    assert set(effective.source_fingerprints) == {"project", "machine", "execution"}


def test_effective_model_mode_and_endpoint_match_the_issue_requirements() -> None:
    """Issue #65 §2/§10: gemma4:12b, local-ollama, the configured endpoint."""
    llm = _compose().as_dict()["llm"]
    assert llm["model"] == "gemma4:12b"
    assert llm["mode"] == "local-ollama"
    assert llm["endpoint"] == "http://127.0.0.1:11500"
    assert llm["allow_cloud_fallback"] is False


def test_distributed_backends_are_declared_as_roles_not_credentials() -> None:
    storage = _compose().as_dict()["storage"]
    assert storage["records"] == "mongodb"
    assert storage["objects"] == "s3"
    assert storage["cache"] == "redis"
    assert storage["distributed"] is True
    # No connection strings or secrets in a public template.
    rendered = json.dumps(storage)
    for marker in ("mongodb://", "redis://", "AKIA", "password", "secret"):
        assert marker not in rendered


def test_machine_layer_disables_browser_capture() -> None:
    """Laskin must never run Firefox/browser collection."""
    values = _compose().as_dict()
    assert values["capabilities"]["browser_capture"] is False


def test_laskin_machine_identity_is_consistent_across_public_entrypoints() -> None:
    """Issue #115: every shipped Laskin entrypoint must resolve machine=laskin."""
    example = (ROOT / "deployment" / "ai26.laskin.env.example").read_text(encoding="utf-8")
    wrapper = (ROOT / "scripts" / "run_ai26_laskin.sh").read_text(encoding="utf-8")
    legacy_wrapper = (ROOT / "scripts" / "run_ai26_laskin_analysis.sh").read_text(encoding="utf-8")

    assert re.search(r"^LACLAUGPT_MACHINE=laskin$", example, re.MULTILINE)
    assert "export LACLAUGPT_MACHINE=${LACLAUGPT_MACHINE:-laskin}" in wrapper
    assert "export LACLAUGPT_MACHINE=${LACLAUGPT_MACHINE:-laskin}" in legacy_wrapper
    assert "export LACLAUGPT_MACHINE=linux-server" not in wrapper
    assert "export LACLAUGPT_MACHINE=linux-server" not in legacy_wrapper


def test_all_ai26_stages_enabled_by_operator_decision() -> None:
    analysis = _compose().as_dict()["analysis"]
    assert analysis["laclau"] is True
    assert analysis["dna_statement_coding"]["enabled"] is True
    assert analysis["critical_ai"]["enabled"] is True


def test_optional_stages_remain_individually_switchable() -> None:
    """Operator decision sets the default; narrowing a run must not need code edits."""
    values = _compose().as_dict()
    assert isinstance(values["analysis"]["dna_statement_coding"], dict)
    assert isinstance(values["analysis"]["critical_ai"], dict)
    assert "enabled" in values["analysis"]["dna_statement_coding"]
    assert "enabled" in values["analysis"]["critical_ai"]


def test_canonical_formation_vocabulary_is_preserved() -> None:
    assert _compose().as_dict()["formations"] == [
        "accelerationism",
        "doomerism",
        "left-wing accelerationism",
        "ai safety",
        "ai critical",
        "anti-ai",
    ]


def test_media_staging_pruning_is_disabled_by_operator_decision() -> None:
    """Laskin retains staged objects until manually cleared."""
    staging = _compose().as_dict()["media_staging"]
    assert staging["max_cache_bytes"] is None
    assert staging["max_age_seconds"] == 0
    assert staging["max_object_bytes"] > 0


def test_execution_layer_never_starts_a_perpetual_scheduler() -> None:
    behaviour = _compose().as_dict()["behaviour"]
    assert behaviour["perpetual_scheduler"] is False
    assert behaviour["work_until_idle"] is False
    assert behaviour["seed_ready"] is True


def test_overlap_lock_is_configured() -> None:
    assert _compose().as_dict()["concurrency"]["overlap_lock"] == "flock"


def test_provenance_contains_no_absolute_paths() -> None:
    provenance = _compose().provenance()
    rendered = json.dumps(provenance)
    assert "/mnt/" not in rendered
    assert str(ROOT) not in rendered


def test_public_layers_contain_no_credential_markers() -> None:
    for path in (PROJECT, MACHINE, EXECUTION):
        text = path.read_text(encoding="utf-8").casefold()
        for marker in ("password", "secret_key", "bearer ", "akia", "mongodb+srv://"):
            assert marker not in text, f"{path.name} contains {marker!r}"


def test_project_layer_pins_the_paper_as_source_of_truth() -> None:
    text = PROJECT.read_text(encoding="utf-8")
    assert "paper/PAPER.md" in text
    assert "codebooks/public/ai26_v2.yaml" in text


def test_context_composition_order_is_documented() -> None:
    text = PROJECT.read_text(encoding="utf-8")
    # The eight-layer order must stay visible in the project layer.
    assert "current source evidence" in text
    assert "current stage instructions" in text
    assert "RAG context" in text


@pytest.mark.parametrize(
    "prompt_ref",
    [
        "multimodal.system:v1",
        "multimodal.frame_analysis:v1",
        "multimodal.summary_analysis:v1",
        "laclau.system:v1",
        "laclau.discourse_analysis:v1",
        "dna.statement_coding_system:v1",
        "dna.statement_coding:v1",
        "critical_ai.system:v1",
        "critical_ai.analysis:v1",
        "periodic_summary.narrative:v1",
    ],
)
def test_declared_prompt_resources_resolve(prompt_ref: str) -> None:
    """Every prompt the AI26 project layer selects must exist in the registry."""
    from laclaugpt_data_analysis.prompt_library import load_prompt

    prompt_id, _, version = prompt_ref.partition(":")
    resource = load_prompt(prompt_id, version=version)
    assert resource.sha256
    assert resource.text.strip()
