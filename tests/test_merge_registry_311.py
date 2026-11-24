"""The AI26 pipeline consumes a pinned merge registry (#311).

Fixtures here are invented on purpose: this repository is public, so a test may not carry real party,
candidate or researcher data. The behaviours under test are the contract, not the names.

What has to hold:

* a settled decision rewrites the label, and only a settled one — ``proposed`` never applies;
* the raw label survives beside the canonical one, so a merge can be revisited;
* a registry that is configured but unreadable, invalid or checksum-mismatched is a hard error;
* scope is honoured: a decision scoped to one country does not touch another country's label;
* sentiment decisions require polarity, and polarity selects the decision;
* the version consumed is recorded, so an output can name what canonicalised it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord, Entity
from laclaugpt_data_analysis.merge_registry import (
    ENTRY_FIELDS,
    ENV_PATH,
    ENV_SHA256,
    MergeRegistry,
    RegistryUnavailable,
    registry_from_env,
)
from laclaugpt_data_analysis.stages.merge_registry_stage import (
    PROVENANCE_NAMESPACE,
    apply_merge_registry,
)


def entry(**overrides) -> dict:
    base = {
        "category": "person",
        "alias": "Testsson",
        "canonical": "Alex Testsson",
        "status": "approved",
        "canonical_id": "wikidata:Q1",
        "wiki_url": "https://en.wikipedia.org/wiki/Alex_Testsson",
        "scope": {"country": "XX"},
        "reviewers": ["r1", "r2", "r3"],
        "evidence": ["https://en.wikipedia.org/wiki/Alex_Testsson"],
        "revision": 1,
    }
    base.update(overrides)
    return base


def write_registry(directory: pathlib.Path, rows: list[dict]) -> tuple[pathlib.Path, str]:
    path = directory / "registry.jsonl"
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")
    return path, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_record(label: str = "Testsson", *, entity_type: str | None = "person") -> CanonicalRecord:
    record = CanonicalRecord(source_url="x:rec-1")
    record.analysis.entities = [Entity(entity_id="e1", label=label, entity_type=entity_type)]
    return record


class TestLoading:
    def test_a_pinned_registry_loads_and_reports_what_it_consumed(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        assert registry.sha256 == digest
        assert len(registry.entries) == 1

    def test_a_checksum_mismatch_refuses_to_load(self, tmp_path):
        path, _digest = write_registry(tmp_path, [entry()])
        with pytest.raises(RegistryUnavailable, match="checksum mismatch"):
            MergeRegistry.load(path, expected_sha256="0" * 64)

    def test_a_missing_file_is_an_error_not_an_empty_registry(self, tmp_path):
        with pytest.raises(RegistryUnavailable, match="not found"):
            MergeRegistry.load(tmp_path / "absent.jsonl")

    def test_an_approved_row_without_three_reviewers_is_refused(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry(reviewers=["r1", "r2"])])
        with pytest.raises(RegistryUnavailable, match="three are required"):
            MergeRegistry.load(path, expected_sha256=digest)

    def test_an_approved_row_without_evidence_is_refused(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry(evidence=[])])
        with pytest.raises(RegistryUnavailable, match="without evidence"):
            MergeRegistry.load(path, expected_sha256=digest)

    def test_an_empty_registry_is_refused(self, tmp_path):
        path, digest = write_registry(tmp_path, [])
        with pytest.raises(RegistryUnavailable, match="empty"):
            MergeRegistry.load(path, expected_sha256=digest)

    def test_env_without_a_path_means_canonicalisation_is_off(self):
        assert registry_from_env({}) is None

    def test_env_with_a_path_that_cannot_be_read_raises(self, tmp_path):
        with pytest.raises(RegistryUnavailable):
            registry_from_env({ENV_PATH: str(tmp_path / "absent.jsonl"), ENV_SHA256: "0" * 64})


class TestSchemaConformance:
    def test_the_adapter_understands_every_field_the_producer_writes(self):
        # The producer is dashboards/ep24_merge_lab/registry.py in the visualization repository. If it gains
        # a field this adapter must learn, this list is where the change is noticed rather than in a run that
        # silently ignores the new decision.
        assert set(ENTRY_FIELDS) == {
            "category", "alias", "canonical", "status", "canonical_id", "wiki_title", "wiki_url",
            "wikidata_qid", "fallback_reason", "polarity", "scope", "evidence", "reviewers", "method",
            "decision", "created_at", "revision", "supersedes",
        }

    def test_a_row_with_the_optional_fields_still_loads(self, tmp_path):
        path, digest = write_registry(
            tmp_path,
            [entry(wiki_title="Alex Testsson", fallback_reason="no article", method="panel",
                   decision="merge", created_at="2026-11-24T00:00:00+00:00", supersedes="")],
        )
        assert MergeRegistry.load(path, expected_sha256=digest).entries


class TestResolution:
    def test_approved_applies(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        resolution = registry.resolve("person", "testsson", country="XX")
        assert resolution.applies
        assert resolution.canonical_label == "Alex Testsson"
        assert resolution.canonical_id == "wikidata:Q1"

    def test_an_unknown_label_is_unresolved_and_unchanged(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        resolution = registry.resolve("person", "Nobody Known", country="XX")
        assert not resolution.applies
        assert resolution.status == "unresolved"
        assert resolution.canonical_label == "Nobody Known"

    def test_a_proposal_never_rewrites_a_label(self, tmp_path):
        path, digest = write_registry(
            tmp_path, [entry(status="proposed", reviewers=["r1"], canonical="Alex Testsson")]
        )
        registry = MergeRegistry.load(path, expected_sha256=digest)
        resolution = registry.resolve("person", "Testsson", country="XX")
        assert not resolution.applies
        assert resolution.status == "proposed"
        assert resolution.canonical_label == "Testsson"

    def test_a_scoped_decision_does_not_touch_another_country(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        assert registry.resolve("person", "Testsson", country="YY").status == "unresolved"

    def test_the_most_specific_scope_wins(self, tmp_path):
        path, digest = write_registry(
            tmp_path,
            [
                entry(scope={}, canonical="Alex Testsson"),
                entry(scope={"country": "XX"}, canonical="Alex Testsson (politician)", revision=2),
            ],
        )
        registry = MergeRegistry.load(path, expected_sha256=digest)
        assert registry.resolve("person", "Testsson", country="XX").canonical_label == "Alex Testsson (politician)"
        assert registry.resolve("person", "Testsson").canonical_label == "Alex Testsson"

    def test_equally_specific_disagreement_is_a_review_not_a_coin_toss(self, tmp_path):
        path, digest = write_registry(
            tmp_path,
            [
                entry(scope={"country": "XX"}, canonical="Alex Testsson"),
                entry(scope={"country": "XX"}, canonical="A. Testsson", canonical_id="wikidata:Q2"),
            ],
        )
        registry = MergeRegistry.load(path, expected_sha256=digest)
        resolution = registry.resolve("person", "Testsson", country="XX")
        assert resolution.status == "review"
        assert not resolution.applies

    def test_keep_separate_maps_a_label_to_itself(self, tmp_path):
        path, digest = write_registry(
            tmp_path,
            [entry(status="keep_separate", canonical="Testsson", canonical_id="", reviewers=["r1", "r2", "r3"])],
        )
        registry = MergeRegistry.load(path, expected_sha256=digest)
        resolution = registry.resolve("person", "Testsson", country="XX")
        assert resolution.status == "keep_separate"
        assert not resolution.applies  # nothing to rewrite, and the decision still travels in the metadata

    def test_sentiment_needs_its_polarity(self, tmp_path):
        rows = [
            entry(category="sentiment", alias="Test issue", canonical="Test issue", polarity="negative",
                  reviewers=["r1", "r2", "r3"], canonical_id="", wiki_url=""),
            entry(category="sentiment", alias="Test issue", canonical="Test issue", polarity="positive",
                  reviewers=["r1", "r2", "r3"], canonical_id="", wiki_url=""),
        ]
        path, digest = write_registry(tmp_path, rows)
        registry = MergeRegistry.load(path, expected_sha256=digest)
        assert registry.resolve("sentiment", "Test issue", country="XX", polarity="negative").status == "approved"
        assert registry.resolve("sentiment", "Test issue", country="XX").status == "unresolved"


class TestApplication:
    def test_a_person_label_is_canonicalised_and_the_raw_label_kept(self, tmp_path):
        # Unscoped on purpose: the record states no country, and the registry must not be consulted with a
        # guessed one, so only a jurisdiction-free decision can apply to it.
        path, digest = write_registry(tmp_path, [entry(scope={})])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        record = make_record()
        assert apply_merge_registry(record, registry) == 1
        entity = record.analysis.entities[0]
        assert entity.label == "Alex Testsson"
        assert "Testsson" in entity.aliases
        assert entity.review_status == "APPROVED"
        assert record.analysis.plugin_results[PROVENANCE_NAMESPACE]["registry_sha256"] == digest

    def test_an_unreviewed_label_is_left_exactly_as_it_was(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        record = make_record(label="Unreviewed Name")
        assert apply_merge_registry(record, registry) == 0
        assert record.analysis.entities[0].label == "Unreviewed Name"
        assert record.analysis.entities[0].review_status == "PROVISIONAL"
        assert PROVENANCE_NAMESPACE not in record.analysis.plugin_results

    def test_an_entity_that_is_not_a_person_is_not_resolved_as_one(self, tmp_path):
        path, digest = write_registry(tmp_path, [entry()])
        registry = MergeRegistry.load(path, expected_sha256=digest)
        record = make_record(label="Testsson", entity_type="organisation")
        assert apply_merge_registry(record, registry) == 0
        assert record.analysis.entities[0].label == "Testsson"
