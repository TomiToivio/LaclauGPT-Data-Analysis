"""The read-only AI26 output audit (issue #435, item 3).

The audit's value is in what it refuses: it never prints a URL, a quotation or a transcript, so its
report can be published; and it distinguishes *complete with findings* from *complete and empty*,
which is the difference between a finished analysis and a plausible-looking gap.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools" / "ai26_output_audit.py"

TEXT = "Ada Example said: open-source models should stay legally available. Others disagreed."


def _audit():
    spec = importlib.util.spec_from_file_location("ai26_output_audit", AUDIT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(**overrides) -> dict:
    """A record shaped like AI26's canonical output, with one correctly grounded quotation."""
    start = TEXT.index("open-source models")
    base = {
        "source_url": "https://example.invalid/video/1",
        "content": {"text": TEXT},
        "evidence": [{
            "evidence_id": "ev-1", "kind": "quote", "source_url": "https://example.invalid/video/1",
            "quote": "open-source models should stay legally available",
            "start_offset": start,
            "end_offset": start + len("open-source models should stay legally available"),
        }],
        "analysis": {
            "status": "complete",
            "relations": [{"relation_id": "r1", "relation_type": "equivalence",
                           "source_ref": "us", "target_ref": "them", "evidence_ids": ["ev-1"]}],
            "us": [{"object_id": "us", "label": "the people"}],
            "model_runs": [{"model": "m", "prompt_version": "v1", "config_revision": "c1"}],
        },
    }
    for key, value in overrides.items():
        if key == "analysis":
            base["analysis"].update(value)
        else:
            base[key] = value
    return base


def test_a_well_grounded_record_passes_every_check():
    module = _audit()
    report = module.audit_stream([record()])
    assert report["failed_checks"] == []
    assert report["records"] == 1


def test_offsets_that_do_not_hold_the_quote_are_reported():
    module = _audit()
    broken = record()
    broken["evidence"][0]["start_offset"] = 0
    broken["evidence"][0]["end_offset"] = 5
    report = module.audit_stream([broken])
    assert report["checks"]["offset_mismatch"] == 1
    # The quotation does occur in the text, just not at those offsets: that is a broken span, not a
    # fabricated quote, and the audit keeps the two apart.
    assert report["checks"]["quote_not_in_text"] == 0


def test_a_quotation_absent_from_the_source_is_reported_separately():
    module = _audit()
    invented = record()
    invented["evidence"][0]["quote"] = "a sentence nobody said"
    report = module.audit_stream([invented])
    assert report["checks"]["offset_mismatch"] == 1
    assert report["checks"]["quote_not_in_text"] == 1


def test_a_quote_without_offsets_is_not_treated_as_verified():
    module = _audit()
    broken = record()
    broken["evidence"][0].pop("start_offset")
    report = module.audit_stream([broken])
    assert report["checks"]["quote_without_offsets"] == 1


def test_relations_pointing_at_unknown_evidence_are_orphans():
    module = _audit()
    broken = record(analysis={"relations": [{
        "relation_id": "r1", "relation_type": "equivalence", "source_ref": "us",
        "target_ref": "them", "evidence_ids": ["ev-missing"]}]})
    report = module.audit_stream([broken])
    assert report["checks"]["orphan_relation_evidence"] == 1


def test_a_relation_without_any_evidence_is_reported():
    module = _audit()
    broken = record(analysis={"relations": [{
        "relation_id": "r1", "relation_type": "equivalence", "source_ref": "us",
        "target_ref": "them", "evidence_ids": []}]})
    report = module.audit_stream([broken])
    assert report["checks"]["relation_without_evidence"] == 1


def test_complete_without_findings_is_a_finding_not_a_success():
    module = _audit()
    empty = record(analysis={"status": "complete", "relations": [], "us": []})
    report = module.audit_stream([empty])
    assert report["checks"]["complete_without_findings"] == 1


def test_complete_without_model_provenance_is_reported():
    module = _audit()
    unprovenanced = record(analysis={"model_runs": []})
    report = module.audit_stream([unprovenanced])
    assert report["checks"]["complete_without_model_runs"] == 1


def test_model_runs_missing_a_configuration_revision_are_reported():
    module = _audit()
    thin = record(analysis={"model_runs": [{"model": "m"}]})
    report = module.audit_stream([thin])
    assert report["checks"]["model_run_without_provenance"] == 1


def test_duplicate_and_empty_identities_are_counted():
    module = _audit()
    first = record()
    second = record()
    third = record(source_url="")
    report = module.audit_stream([first, second, third])
    assert report["checks"]["duplicate_identity"] == 1
    assert report["checks"]["empty_identity"] == 1
    assert report["unique_identities"] == 1


def test_a_plugin_result_that_disagrees_with_its_latest_run_is_reported():
    """The stale-output detector: current plugin result vs the most recent recorded run."""
    module = _audit()
    stale = record()
    stale["analysis"]["plugin_results"] = {"dna_statement_coding": {"proposal": {"statements": [1, 2, 3]}}}
    stale["intermediate"] = {"stage_outputs": {"dna_statement_coding": [
        {"proposal": {"statements": []}}]}}
    report = module.audit_stream([stale])
    assert report["checks"]["plugin_result_disagrees_with_latest_run"] == 1
    assert "dna_statement_coding" in report["samples"]["plugin_result_disagrees_with_latest_run"][0]


def test_the_report_never_contains_source_content(tmp_path):
    module = _audit()
    report = module.audit_stream([record()])
    serialised = json.dumps(report)
    assert "example.invalid" not in serialised
    assert "Ada Example" not in serialised
    assert "open-source models should stay legally available" not in serialised


def test_the_cli_reports_failures_by_check_and_exits_non_zero(tmp_path, capsys):
    module = _audit()
    path = tmp_path / "records.jsonl"
    broken = record()
    broken["evidence"][0]["start_offset"] = 0
    broken["evidence"][0]["end_offset"] = 5
    path.write_text(json.dumps(broken) + "\n", encoding="utf-8")
    code = module.main(["--input", str(path)])
    assert code == 1
    assert "offset_mismatch" in capsys.readouterr().out


def test_the_cli_can_watch_one_check_and_ignore_others(tmp_path):
    module = _audit()
    path = tmp_path / "records.jsonl"
    thin = record(analysis={"model_runs": []})
    path.write_text(json.dumps(thin) + "\n", encoding="utf-8")
    assert module.main(["--input", str(path), "--fail-on", "offset_mismatch"]) == 0
    assert module.main(["--input", str(path), "--fail-on", "complete_without_model_runs"]) == 1
