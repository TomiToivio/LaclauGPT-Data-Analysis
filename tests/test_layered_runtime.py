from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_data_analysis.codebooks import load_codebook, merge_codebooks
from laclaugpt_data_analysis.context_profiles import load_context_profile
from laclaugpt_data_analysis.context_runtime import ContextItem, assemble_context, load_text_context
from laclaugpt_data_analysis.runtime_config import compose_run_config, compose_run_config_from_files


def test_layered_precedence_and_identity_are_explicit():
    effective = compose_run_config(
        project="demo",
        arena="grassroots",
        machine="server",
        execution="cron",
        project_config={"analysis": {"signifiers": True}, "models": {"main": "small"}, "x": 1},
        arena_config={"models": {"main": "medium"}, "x": 2},
        machine_config={"storage": {"backend": "mongo"}, "x": 3},
        execution_config={"retry": {"max_attempts": 2}, "x": 4},
        overrides={"models": {"main": "large"}, "x": 5},
    )
    payload = effective.as_dict()
    assert payload["project"] == "demo"
    assert payload["arena"] == "grassroots"
    assert payload["machine"] == "server"
    assert payload["execution"] == "cron"
    assert payload["models"]["main"] == "large"
    assert payload["storage"]["backend"] == "mongo"
    assert payload["retry"]["max_attempts"] == 2
    assert payload["x"] == 5
    assert len(effective.config_hash) == 64


def test_explicit_override_cannot_replace_layer_identity():
    with pytest.raises(ValueError):
        compose_run_config(project="demo", overrides={"project": "other"})


def test_private_external_config_files_are_supported_without_path_leak(tmp_path: Path):
    project = tmp_path / "private-project.yaml"
    machine = tmp_path / "private-machine.yaml"
    project.write_text("context_profile: high_accuracy\nanalysis:\n  discourse: true\n", encoding="utf-8")
    machine.write_text("storage:\n  backend: mongo\n", encoding="utf-8")
    effective = compose_run_config_from_files(
        project="private-demo",
        project_path=project,
        machine="server",
        machine_path=machine,
    )
    provenance = effective.provenance()
    assert provenance["context_profile"] == "high_accuracy"
    assert provenance["storage"]["backend"] == "mongo"
    assert "private-project.yaml" not in json.dumps(provenance)
    assert set(provenance["source_fingerprints"]) == {"project", "machine"}


def test_context_profiles_match_expected_runtime_policies():
    assert load_context_profile("fast_local").max_context_chars == 2000
    assert load_context_profile("balanced").context_provenance is True
    assert load_context_profile("high_accuracy").inject_previous_batch_summary is True
    assert load_context_profile("validation").fail_on_missing_codebook is True


def test_context_runtime_is_bounded_and_offline():
    snapshot = assemble_context(
        profile="high_accuracy",
        codebook_items=[ContextItem("codebook", "AI safety", "synthetic-codebook")],
        previous_summary=[ContextItem("previous_summary", "Yesterday summary", "previous.json")],
        corpus_context=[ContextItem("corpus_stats", "documents=10", "stats.json")],
        researcher_validation=[ContextItem("validation", "human accepted actor A", "review.csv", trust="human")],
    )
    assert "AI safety" in snapshot.text
    assert "Yesterday summary" in snapshot.text
    assert "documents=10" in snapshot.text
    assert snapshot.provenance["profile"] == "high_accuracy"
    assert snapshot.provenance["item_count"] == 4
    assert len(snapshot.sha256) == 64


def test_validation_profile_fails_closed_without_codebook():
    with pytest.raises(RuntimeError):
        assemble_context(profile="validation")


def test_no_context_no_rag_fallback_is_valid():
    snapshot = assemble_context(profile="fast_local")
    assert snapshot.text == ""
    assert snapshot.provenance["vector_rag"] is False
    assert snapshot.provenance["item_count"] == 0


def test_previous_summary_loader_records_content_hash_not_private_path(tmp_path: Path):
    source = tmp_path / "secret" / "previous.json"
    source.parent.mkdir()
    source.write_text('{"review_status":"human_reviewed","summary":"ok"}', encoding="utf-8")
    item = load_text_context(source, kind="previous_summary", trust="human_reviewed")
    assert item.source == "previous.json"
    assert "secret" not in json.dumps(dict(item.metadata))
    assert len(item.metadata["sha256"]) == 64


def test_codebook_yaml_validation_hash_and_merge(tmp_path: Path):
    base = tmp_path / "base.yaml"
    arena = tmp_path / "arena.json"
    base.write_text(
        """codebook_id: demo\nversion: '1'\ntitle: Demo\nproject: demo\nentries:\n  - kind: signifier\n    label: AI\n    aliases: [artificial intelligence]\n""",
        encoding="utf-8",
    )
    arena.write_text(
        json.dumps(
            {
                "codebook_id": "demo-arena",
                "version": "1",
                "title": "Arena",
                "project": "demo",
                "arena": "grassroots",
                "entries": [{"kind": "actor", "label": "Researcher"}],
            }
        ),
        encoding="utf-8",
    )
    a = load_codebook(base)
    b = load_codebook(arena)
    merged = merge_codebooks([a, b])
    assert len(a.fingerprint()) == 64
    assert merged.arena == "grassroots"
    assert {entry.kind for entry in merged.entries} == {"signifier", "actor"}
    assert len(merged.provenance_snapshot()["sha256"]) == 64


def test_malformed_codebook_is_reported(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("title: Missing required fields\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_codebook(bad)
