"""#341: the read-only AI26 CLI - the pipeline, its prompts and its contract, no model call.

The issue asks that each step be understandable, that the exact effective prompt be
reviewable at the CLI without a model call, and that the output be human-readable *and*
machine-readable. It also forbids the CLI from silently doing work. These tests pin all
four, plus the read-only guarantee itself.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from laclaugpt_data_analysis import ai26

REPO_ROOT = pathlib.Path(ai26.__file__).resolve().parents[2]


def capsys_json(capsys):
    captured = capsys.readouterr()
    return json.loads(captured.out)


def test_stages_lists_every_canonical_step_with_a_self_description(capsys) -> None:
    assert ai26.main(["stages", "--json"]) == 0
    payload = capsys_json(capsys)
    assert payload["canonical_steps"] == list(ai26.CANONICAL_STEPS)
    for row in payload["stages"]:
        assert row["module"] in ai26.CANONICAL_STEPS
        assert row["phase_status"]
        assert row["summary"], f"{row['module']} must describe itself"


def test_the_stage_map_keeps_phase_2_separate_and_non_blocking(capsys) -> None:
    assert ai26.main(["stages", "--json"]) == 0
    payload = capsys_json(capsys)
    phase_2 = ai26.PHASE_STATUS["dna"], ai26.PHASE_STATUS["sna"]
    assert all("experimental_phase_2" == value for value in phase_2)
    assert not any(
        row["phase_status"] == "experimental_phase_2" for row in payload["stages"]
    ), "Phase 2 steps are not part of the canonical step list"


def test_stages_is_readable_without_json(capsys) -> None:
    assert ai26.main(["stages"]) == 0
    out = capsys.readouterr().out
    assert "AI26 canonical pipeline" in out
    assert "preprocess" in out
    assert "no model is called" in out


def test_render_prompt_reports_the_ids_and_hashes_without_a_model_call(capsys) -> None:
    assert ai26.main(["render-prompt", "--stage", "discourse", "--profile", "ai26", "--json"]) == 0
    record = capsys_json(capsys)
    assert record["system_prompt_id"] == "laclau.system"
    assert record["task_prompt_id"] == "laclau.discourse_analysis"
    for item in record["files"]:
        payload = (REPO_ROOT / item["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_render_prompt_refuses_an_unknown_stage_with_a_message_not_a_traceback(capsys) -> None:
    assert ai26.main(["render-prompt", "--stage", "not-a-stage"]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_the_ai26_profile_and_the_legacy_profile_resolve_different_prompts() -> None:
    ai26_record = ai26._prompt_record("summary", "ai26")
    legacy_record = ai26._prompt_record("summary", "ep24")
    assert ai26_record["task_prompt_id"] != legacy_record["task_prompt_id"]
    assert ai26_record["system_prompt_id"] != legacy_record["system_prompt_id"]


def test_contract_resolves_the_shipped_project_config(capsys) -> None:
    assert ai26.main(["contract", "--project-config", "config/projects/ai26.yaml", "--json"]) == 0
    contract = capsys_json(capsys)
    assert isinstance(contract, dict)
    assert contract, "the shipped AI26 project config must resolve to a contract"


def test_a_missing_config_is_an_error_not_a_crash(capsys) -> None:
    assert ai26.main(["contract", "--project-config", "config/projects/not-a-project.yaml"]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_status_declares_itself_read_only(capsys) -> None:
    assert ai26.main(["status", "--json"]) == 0
    payload = capsys_json(capsys)
    assert payload["read_only"] is True
    assert payload["calls_a_model"] is False
    assert set(payload["configs"]) == {"project", "machine", "execution"}


def test_the_cli_cannot_reach_a_model_or_write_research_data() -> None:
    """The read-only promise, asserted against the source rather than promised in prose."""
    source = pathlib.Path(ai26.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import ollama",
        "chat_structured(",
        "LLMProvider",
        "from .llm.",
        "mongo",
        ".write_text(",
        "shutil",
        "subprocess",
    ):
        assert forbidden not in source, f"the CLI must not reference {forbidden!r}"


def test_no_subcommand_writes_anything(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    for argv in (
        ["status"],
        ["stages"],
        ["render-prompt", "--stage", "discourse", "--profile", "ai26"],
    ):
        assert ai26.main(argv) == 0
    capsys.readouterr()
    assert list(tmp_path.iterdir()) == [], "the CLI must leave the working directory untouched"
