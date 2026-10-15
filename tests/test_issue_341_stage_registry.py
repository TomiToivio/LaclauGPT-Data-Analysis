"""#341: the stage registry is the source of truth, and it may not drift from the code.

The issue asks for "a machine-readable stage registry". A registry that quietly disagrees with
the pipeline is worse than none, because it reads like documentation. These tests pin the
registry to the modules it names, to the prompt map, and to the read-only CLI that prints it.
"""
from __future__ import annotations

import importlib
import json
import pathlib

from laclaugpt_data_analysis import ai26
from laclaugpt_data_analysis.stages.prompt_map import prompt_ids_for_stage


def _registry() -> dict:
    return json.loads(ai26.REGISTRY_PATH.read_text(encoding="utf-8"))


def test_the_registry_is_packaged_well_formed_and_versioned() -> None:
    registry = ai26.load_stage_registry()
    assert registry["format"] == "laclaugpt.ai26.stage_registry"
    assert isinstance(registry["version"], int)
    assert registry["reading_order_note"], "the reading-order caveat belongs in the data"
    assert registry["canonical_stages"]


def test_the_cli_view_is_derived_from_the_registry() -> None:
    """No hand-maintained duplicate of the step list anywhere in the code."""
    registry = _registry()
    expected = [s["id"] for s in registry["canonical_stages"] if s.get("in_canonical_list")]
    assert list(ai26.CANONICAL_STEPS) == expected
    for stage in [*registry["canonical_stages"], *registry["phase_2_stages"]]:
        assert ai26.STAGE_NUMBERS[stage["id"]] == tuple(stage["reading_order"])
        assert ai26.PHASE_STATUS[stage["id"]] == stage["phase_status"]


def test_every_canonical_module_exists_and_imports() -> None:
    """A registry naming a module that is not there would be a map to nowhere."""
    for stage in _registry()["canonical_stages"]:
        module = stage["module"]
        if module is None:
            assert stage["id"] == "handoff"
            continue
        with_module = importlib.import_module(f"laclaugpt_data_analysis.stages.{module}")
        assert with_module is not None, stage["id"]


def test_every_phase_2_module_exists_and_is_importable() -> None:
    for stage in _registry()["phase_2_stages"]:
        imported = importlib.import_module(stage["module"])
        assert imported is not None, stage["id"]
        assert stage["phase_status"] == "experimental_phase_2"
        assert stage["note"], "an experimental stage must say so in the registry"


def test_phase_2_never_appears_in_the_canonical_list() -> None:
    phase_2 = {stage["id"] for stage in _registry()["phase_2_stages"]}
    assert phase_2 == set(ai26.PHASE_2_STEPS)
    assert not phase_2.intersection(ai26.CANONICAL_STEPS)


def test_only_the_media_stage_is_conditional_and_it_is_the_only_one_needing_media() -> None:
    registry = _registry()["canonical_stages"]
    canonical = [s for s in registry if s.get("in_canonical_list")]
    needing_media = [s["id"] for s in registry if s.get("requires_media")]
    conditional = [s["id"] for s in canonical if s.get("conditional")]
    assert needing_media == ["frame"]
    assert conditional == ["frame"], "the text-only flow must have no conditional step"
    # The ingest step is conditional too, but it is not part of the analysis step list.
    assert [s["id"] for s in registry if s.get("conditional")] == ["handoff", "frame"]


def test_the_declared_prompt_stages_resolve_for_the_active_profile() -> None:
    """A prompt_stage in the registry must be a stage the prompt map actually knows."""
    for stage in _registry()["canonical_stages"]:
        prompt_stage = stage.get("prompt_stage")
        if prompt_stage is None:
            continue
        system_id, task_id = prompt_ids_for_stage("ai26", prompt_stage)
        assert system_id and task_id, stage["id"]


def test_reading_orders_are_ints_inside_the_issues_range() -> None:
    for stage in [*_registry()["canonical_stages"], *_registry()["phase_2_stages"]]:
        orders = stage["reading_order"]
        assert orders, stage["id"]
        assert all(isinstance(order, int) and 0 <= order <= 9 for order in orders), stage["id"]


def test_the_cli_reports_where_the_registry_lives(capsys) -> None:
    assert ai26.main(["stages", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry"]["path"].endswith("stages/registry.json")
    assert payload["registry"]["version"] == _registry()["version"]
    assert payload["phase_2_steps"] == list(ai26.PHASE_2_STEPS)
    for row in payload["stages"]:
        assert isinstance(row["requires_media"], bool)
        assert isinstance(row["conditional"], bool)


def test_the_module_file_is_the_only_registry() -> None:
    """Guard against a second copy of the step list creeping back into the code."""
    source = pathlib.Path(ai26.__file__).read_text(encoding="utf-8")
    assert '"preprocess",\n    "frame"' not in source, "the step list belongs in the registry"

    stages_dir = pathlib.Path(ai26.__file__).parent / "stages"
    registries = sorted(path.name for path in stages_dir.glob("*registry*.json"))
    assert registries == ["registry.json"]
