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
    assert ai26.PHASE_STATUS["dna"] == "experimental_phase_2"
    assert ai26.PHASE_STATUS["sna"] == "experimental_phase_2"
    assert not any(
        row["phase_status"] == "experimental_phase_2" for row in payload["stages"]
    ), "Phase 2 steps are not part of the canonical step list"


def test_stages_is_readable_without_json(capsys) -> None:
    assert ai26.main(["stages"]) == 0
    out = capsys.readouterr().out
    assert "AI26 canonical pipeline" in out
    assert "preprocess" in out
    assert "no model is called" in out


def test_prompt_ids_resolve_to_the_files_behind_them(capsys) -> None:
    """The point of the subcommand: the exact prompt a run used, with its hash.

    The digest covers the **text**, not the file's on-disk bytes: those differ on a checkout whose
    line endings were converted, and a digest that cannot verify the text beside it is not a
    provenance record (issue #382, upstream #298's class). On an LF checkout the two are equal, so
    this pins the same values CI has always seen.
    """
    assert ai26.main(["render-prompt", "--stage", "discourse", "--profile", "ai26", "--json"]) == 0
    record = capsys_json(capsys)
    assert record["system_prompt_id"] == "laclau.system"
    assert record["task_prompt_id"] == "laclau.discourse_analysis"
    assert record["files"], "the discourse prompt exists and must be found"
    for item in record["files"]:
        text = (REPO_ROOT / item["path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == item["sha256"]
        assert item["chars"] == len(text)
        assert item["version"]


def test_every_prompt_version_is_listed_rather_than_collapsed(capsys) -> None:
    """A later version must not erase the record of an earlier one."""
    assert ai26.main(["render-prompt", "--stage", "discourse", "--profile", "ai26", "--json"]) == 0
    record = capsys_json(capsys)
    systems = [item for item in record["files"] if item["prompt_id"] == "laclau.system"]
    assert len(systems) >= 1
    versions = {item["version"] for item in systems}
    assert all(version.startswith("system_v") for version in versions)


def test_show_prints_the_prompt_text_itself(capsys) -> None:
    assert ai26.main(
        ["render-prompt", "--stage", "discourse", "--profile", "ai26", "--show"]
    ) == 0
    out = capsys.readouterr().out
    assert "### laclau.discourse_analysis" in out
    assert len(out) > 400, "the prompt text itself is what a researcher comes here to read"


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


def test_an_unknown_prompt_id_resolves_to_no_files_rather_than_guessing() -> None:
    assert ai26.prompt_files("notafamily.notaprompt") == []


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


def test_show_json_includes_prompt_bodies_and_remains_valid_json(capsys) -> None:
    """--show must not silently override the machine-readable --json contract."""
    assert ai26.main(["render-prompt", "--stage", "discourse", "--json", "--show"]) == 0
    record = capsys_json(capsys)
    assert record["files"]
    for item in record["files"]:
        assert item["text"] == (REPO_ROOT / item["path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(item["text"].encode("utf-8")).hexdigest() == item["sha256"]

