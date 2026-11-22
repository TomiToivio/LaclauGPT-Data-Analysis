"""The analysis-field contract: a declared field is produced, or it is registered as empty.

These tests are the reason the module exists. `themes`, `discourses` and `them` were each found by
reading a 5,302-record corpus and noticing a column that was always blank; the same defect could return
the moment somebody adds a field to `AnalysisSection` and forgets the pipeline. It now fails here
instead, and the failure names the field.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from laclaugpt_data_analysis import field_contract as fc

ROOT = Path(__file__).resolve().parents[1]


class TestTheRealContract:
    def test_every_declared_field_is_produced_or_registered(self):
        report = fc.contract()
        assert report["unregistered"] == [], (
            "these fields are declared on AnalysisSection, assigned nowhere, and not registered in "
            f"UNPRODUCED_FIELDS: {report['unregistered']} — either produce them or register the defect"
        )

    def test_no_registration_is_stale(self):
        assert fc.contract()["stale"] == []

    def test_no_registration_names_a_field_the_schema_lost(self):
        assert fc.contract()["unknown"] == []

    def test_every_registration_states_an_issue_a_reason_and_a_decision(self):
        for name, entry in fc.UNPRODUCED_FIELDS.items():
            assert entry.field == name
            assert entry.issue.startswith("#"), name
            assert len(entry.reason) > 40, name
            assert len(entry.decision) > 40, name
            assert entry.defect in {fc.NO_PRODUCER, fc.PRODUCER_WITHOUT_INPUT,
                                   fc.PRODUCER_MISSING_UPSTREAM}, name

    def test_the_three_defect_classes_are_all_represented(self):
        defects = {entry.defect for entry in fc.UNPRODUCED_FIELDS.values()}
        assert defects <= {fc.NO_PRODUCER, fc.PRODUCER_WITHOUT_INPUT, fc.PRODUCER_MISSING_UPSTREAM}

    def test_the_fields_this_batch_is_about_are_registered(self):
        assert "themes" not in fc.UNPRODUCED_FIELDS
        assert "discourses" not in fc.UNPRODUCED_FIELDS
        for name in ("them",):
            assert name in fc.UNPRODUCED_FIELDS, name

    def test_the_report_runs_and_names_the_registered_fields(self):
        # The child is a fresh interpreter: pytest's `pythonpath = ["src"]` only reaches this
        # process, so without passing it on the child cannot import the package at all and the
        # test fails for an environment reason rather than the contract it exists to check.
        env = {**os.environ,
               "PYTHONPATH": os.pathsep.join(filter(None, [str(ROOT / "src"),
                                                           os.environ.get("PYTHONPATH")]))}
        result = subprocess.run([sys.executable, "-m", "laclaugpt_data_analysis.field_contract"],
                                capture_output=True, text=True, timeout=120, cwd=ROOT, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        for name in fc.UNPRODUCED_FIELDS:
            assert name in result.stdout


class TestTheScan:
    def _package(self, tmp_path: Path, source: str) -> Path:
        package = tmp_path / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "mod.py").write_text(textwrap.dedent(source), encoding="utf-8")
        return package

    def test_attribute_assignment_counts_as_a_producer(self, tmp_path):
        package = self._package(tmp_path, "def f(record, x):\n    record.analysis.alpha = x\n")
        assert "alpha" in fc.produced_fields(package)

    def test_mutation_of_a_list_field_counts(self, tmp_path):
        package = self._package(tmp_path, "def f(record, x):\n    record.analysis.beta.append(x)\n")
        assert "beta" in fc.produced_fields(package)

    def test_keyed_assignment_into_a_field_counts(self, tmp_path):
        package = self._package(tmp_path, 'def f(record, x):\n    record.analysis.gamma["k"] = x\n')
        assert "gamma" in fc.produced_fields(package)

    def test_dict_style_assignment_counts(self, tmp_path):
        package = self._package(tmp_path, 'def f(analysis, x):\n    analysis["delta"] = x\n')
        assert "delta" in fc.produced_fields(package)

    def test_reading_a_field_is_not_producing_it(self, tmp_path):
        package = self._package(tmp_path, "def f(record):\n    return record.analysis.epsilon\n")
        assert "epsilon" not in fc.produced_fields(package)

    def test_a_read_inside_an_assignment_to_something_else_is_not_a_producer(self, tmp_path):
        package = self._package(
            tmp_path,
            "def f(record):\n    other = record.analysis.zeta + record.analysis.eta\n",
        )
        produced = fc.produced_fields(package)
        assert "zeta" not in produced and "eta" not in produced

    def test_a_field_that_is_both_produced_and_registered_as_having_no_producer_is_stale(self, tmp_path, monkeypatch):
        package = self._package(tmp_path, "def f(record, x):\n    record.analysis.theta = x\n")
        monkeypatch.setattr(fc, "DEFAULT_PACKAGE", package)
        monkeypatch.setattr(fc, "produced_fields", lambda package=package: {"theta": ["mod.py"]})
        monkeypatch.setattr(fc, "analysis_fields", lambda: ("theta", "iota"))
        monkeypatch.setitem(fc.UNPRODUCED_FIELDS, "theta",
                            fc.UnproducedField("theta", "#0", fc.NO_PRODUCER, "r" * 50, "d" * 50))
        report = fc.contract()
        assert report["stale"] == ["theta"]
        assert report["unregistered"] == ["iota"]

    def test_a_registered_field_with_a_producer_of_another_class_is_not_stale(self, monkeypatch):
        monkeypatch.setattr(fc, "produced_fields", lambda package=fc.DEFAULT_PACKAGE: {"themes": ["x.py"]})
        monkeypatch.setattr(fc, "analysis_fields", lambda: ("themes",))
        assert fc.contract()["stale"] == []


class TestNoMethodologicalChange:
    def test_the_module_only_reads(self):
        source = (ROOT / "src" / "laclaugpt_data_analysis" / "field_contract.py").read_text(encoding="utf-8")
        for forbidden in ("open(", ".write_text(", "requests.", "MongoClient"):
            assert forbidden not in source, f"{forbidden} would make a read-only contract check write"
