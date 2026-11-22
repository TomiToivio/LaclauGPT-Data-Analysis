"""#437: the operator export path must be testable without a live store (#488 in mind).

`scripts/export_ai26_bundle.py` exists because AI26 had no operator export command --
only `write_research_bundle` buried in a library. These tests pin its contract with the
store and the model calls faked, so the script can be changed without Mongo or Laskin.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_ai26_bundle", ROOT / "scripts" / "export_ai26_bundle.py")
assert spec and spec.loader, "the operator script must be importable by path"
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def test_sha256_matches_hashlib(tmp_path):
    target = tmp_path / "artifact.jsonl"
    target.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    assert export._sha256(target) == hashlib.sha256(target.read_bytes()).hexdigest()


def test_list_runs_returns_counts_and_skips_empty_run_ids(monkeypatch):
    class FakeCollection:
        def aggregate(self, pipeline):
            return [{"_id": "run-a", "records": 5}, {"_id": None, "records": 2}]

    monkeypatch.setattr(export, "_collection", lambda settings: FakeCollection())
    settings = SimpleNamespace(project_id="ai26")
    assert export.list_runs(settings) == [{"run_id": "run-a", "records": 5}]


def test_missing_run_id_and_output_root_is_a_usage_error(monkeypatch):
    monkeypatch.setattr(export, "load_settings", lambda: SimpleNamespace())
    with pytest.raises(SystemExit):
        export.main([])


def test_a_run_without_completed_records_refuses_to_write_a_bundle(monkeypatch, tmp_path, capsys):
    """The operator decision is explicit: no synthetic or empty export passed off as real."""
    monkeypatch.setattr(export, "load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(export, "load_analysis_records", lambda settings, run_id, strict_identity=False: [
        SimpleNamespace(analysis=SimpleNamespace(status="collection-only")),
    ])
    code = export.main(["--run-id", "r1", "--output-root", str(tmp_path / "bundle")])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "no_completed_records" and payload["records_seen"] == 1
    assert not (tmp_path / "bundle").exists()


def test_export_reports_counts_paths_and_checksums_without_source_text(monkeypatch, tmp_path, capsys):
    artifact = tmp_path / "bundle" / "analysis.jsonl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"x": 1}\n', encoding="utf-8")

    monkeypatch.setattr(export, "load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(export, "load_analysis_records", lambda settings, run_id, strict_identity=False: [
        SimpleNamespace(source_url="https://example.invalid/one", source_native_ids={"document_id": "one"},
                        analysis=SimpleNamespace(status="analyzed")),
    ])
    monkeypatch.setattr(export, "write_research_bundle", lambda records, root, stem: {"jsonl": artifact})

    code = export.main(["--run-id", "r1", "--output-root", str(tmp_path / "bundle")])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records_exported"] == 1
    assert payload["artifacts"]["analysis.jsonl"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert set(payload) == {
        "run_id", "exported_at_utc", "deployed_sha", "records_exported",
        "duplicates_collapsed", "records_without_native_id",
        "records_seen_in_run", "output_root", "artifacts",
    }, "the summary is the privacy boundary: counts and paths only, never record content"


def test_limit_caps_the_export(monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(export, "load_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(export, "load_analysis_records", lambda settings, run_id, strict_identity=False: [
        SimpleNamespace(source_url=f"https://example.invalid/{i}", source_native_ids={"document_id": str(i)},
                        analysis=SimpleNamespace(status="analyzed")) for i in range(5)
    ])

    def fake_write(records, root, stem):
        seen["n"] = len(records)
        return {}

    monkeypatch.setattr(export, "write_research_bundle", fake_write)
    assert export.main(["--run-id", "r1", "--output-root", str(tmp_path), "--limit", "2"]) == 0
    assert seen["n"] == 2


def test_identical_duplicate_source_urls_are_counted_and_collapsed():
    record = SimpleNamespace(source_url="https://example.invalid/1",
                             source_native_ids={"document_id": "d1"})
    distinct = SimpleNamespace(source_url="https://example.invalid/2",
                               source_native_ids={})
    kept, collapsed, no_native_id = export.dedupe_by_source_url([record, record, distinct])
    assert kept == [record, distinct]
    assert collapsed == 1
    assert no_native_id == 1


def test_conflicting_analyses_cannot_be_silently_deduplicated():
    first = SimpleNamespace(source_url="https://example.invalid/1",
                            source_native_ids={"document_id": "d1"})
    conflicting = SimpleNamespace(source_url="https://example.invalid/1",
                                  source_native_ids={"document_id": "d2"})
    with pytest.raises(ValueError, match="conflicting analyses"):
        export.dedupe_by_source_url([first, conflicting])


def test_missing_identity_is_rejected_not_collapsed():
    with pytest.raises(ValueError, match="identity missing"):
        export.dedupe_by_source_url([SimpleNamespace(source_url="", source_native_ids={})])
