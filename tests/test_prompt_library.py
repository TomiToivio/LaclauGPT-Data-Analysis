from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from laclaugpt_data_analysis.plugin_pipeline import LegacyLaclauPlugin, PluginSpec
from laclaugpt_data_analysis.prompt_library import (
    PromptLibrary,
    PromptNotFoundError,
    PromptRenderError,
    load_prompt,
    prompt_provenance,
)


def test_load_known_prompt_by_id_and_version() -> None:
    prompt = load_prompt("laclau.system", version="v1")
    assert prompt.id == "laclau.system"
    assert prompt.version == "v1"
    assert prompt.path == "laclau/system_v1.md"
    assert len(prompt.sha256) == 64


def test_packaged_prompt_resource_is_available_through_importlib_resources() -> None:
    prompt_path = (
        resources.files("laclaugpt_data_analysis")
        .joinpath("prompts")
        .joinpath("laclau")
        .joinpath("system_v1.md")
    )
    assert prompt_path.is_file()
    assert "Evidence-first" in prompt_path.read_text(encoding="utf-8")


def test_missing_prompt_version_fails_clearly() -> None:
    with pytest.raises(PromptNotFoundError, match="laclau.system:v999"):
        load_prompt("laclau.system", version="v999")


def test_hash_is_stable() -> None:
    first = load_prompt("laclau.system", version="v1")
    second = load_prompt("laclau.system", version="v1")
    assert first.sha256 == second.sha256


def test_changing_prompt_text_changes_hash(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    path = tmp_path / "demo" / "task_v1.md"
    path.write_text("Hello {name}\n", encoding="utf-8")
    first = PromptLibrary(root=tmp_path).load("demo.task", version="v1")
    path.write_text("Hello, {name}!\n", encoding="utf-8")
    second = PromptLibrary(root=tmp_path).load("demo.task", version="v1")
    assert first.sha256 != second.sha256


def test_rendering_is_deterministic_and_validates_required_variables() -> None:
    prompt = load_prompt("laclau.document_analysis", version="v1")
    values = {
        "source_url": "https://example.test/item",
        "source_text": "Evidence text",
        "codebook_context": "candidate context",
    }
    first = prompt.render(**values)
    second = prompt.render(**values)
    assert first.text == second.text
    assert first.sha256 == second.sha256
    assert first.variables == ("source_url", "source_text", "codebook_context")
    with pytest.raises(PromptRenderError, match="source_text"):
        prompt.render(source_url="x", codebook_context="y")


def test_prompt_provenance_contains_resources_and_rendered_hash() -> None:
    system = load_prompt("laclau.system", version="v1")
    task = load_prompt("laclau.document_analysis", version="v1")
    rendered = task.render(source_url="u", source_text="t", codebook_context="c")
    provenance = prompt_provenance(system, task, rendered=rendered)
    assert provenance["prompt_resources"][0]["prompt_id"] == "laclau.system"
    assert provenance["prompt_resources"][1]["prompt_sha256"] == task.sha256
    assert provenance["rendered_prompt_sha256"] == rendered.sha256


def test_plugin_can_declare_prompt_resources() -> None:
    assert "laclau.system:v1" in LegacyLaclauPlugin.spec.prompt_ids
    LegacyLaclauPlugin.spec.validate()


def test_prompt_free_plugin_spec_remains_valid() -> None:
    spec = PluginSpec(name="network", version="1.0", deterministic=True)
    assert spec.prompt_ids == ()
    spec.validate()
