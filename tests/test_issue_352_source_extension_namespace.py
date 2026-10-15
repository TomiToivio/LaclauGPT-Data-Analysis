"""#352: the consumer preserves producer source fields it does not declare.

A record was valid by the published contract - both JSON schemas leave ``source`` open - and
unloadable by the code, because ``SourceSection`` forbids undeclared keys. These tests pin the
fix: undeclared keys are preserved verbatim under ``source.extensions``, declared fields keep
their place, and everything else stays strict.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from laclaugpt_data_analysis.canonical import SCHEMA_VERSION, SourceSection
from laclaugpt_data_analysis.schema_version import (
    UnsupportedSchemaVersion,
    normalize_schema_version,
)


def _record(**source_extra):
    """A minimal 1.1.0-shaped record, as the producer and its adapter view present it."""
    source = {
        "platform": "synthetic-platform",
        "source_type": "social_post",
        "author": "synthetic-author",
        "created_at": "2026-09-18T09:00:00Z",
        "collected_at": "2026-09-18T09:00:05Z",
        "collector": "laclaugpt-data-collection",
        "language": "en",
        "country": "XX",
        "raw_ref": "fixture://synthetic/raw/001",
    }
    source.update(source_extra)
    return {
        "schema_version": "1.1.0",
        "source_url": "https://example.invalid/synthetic/record-001",
        "source": source,
        "content": {"text": "Synthetic text.", "language": "en"},
        "raw_capture": {"ref": "fixture://synthetic/raw/001", "content_type": "application/json"},
        "intermediate": {},
        "analysis": {},
        "human_readable": {"summary": "Synthetic."},
        "provenance": [],
        "review": {},
        "legacy": {},
    }


def test_the_reproduction_from_the_issue_no_longer_fails() -> None:
    """The exact pair of fields a live record carries."""
    record = normalize_schema_version(
        _record(backfill="#250", backfilled_at="20261012T071912Z")
    )
    assert record.schema_version == SCHEMA_VERSION
    assert record.source_url == "https://example.invalid/synthetic/record-001"


def test_undeclared_keys_are_preserved_verbatim_not_discarded() -> None:
    record = normalize_schema_version(
        _record(backfill="#250", backfilled_at="20261012T071912Z")
    )
    assert record.source.extensions["backfill"] == "#250"
    assert record.source.extensions["backfilled_at"] == "20261012T071912Z"


def test_declared_fields_keep_their_place_rather_than_moving_into_extensions() -> None:
    record = normalize_schema_version(_record(backfill="#250"))
    assert record.source.platform == "synthetic-platform"
    assert record.source.author == "synthetic-author"
    assert set(record.source.extensions) == {"backfill"}


def test_a_record_without_undeclared_keys_is_unchanged() -> None:
    """The extension namespace stays empty, so existing records round-trip as they did."""
    record = normalize_schema_version(_record())
    assert record.source.extensions == {}


def test_every_undeclared_key_is_kept_not_only_the_two_we_knew_about() -> None:
    """The point of a namespace rather than two declared fields: the next field works too."""
    record = normalize_schema_version(
        _record(backfill="#250", something_new="value", nested_extra={"a": 1})
    )
    assert record.source.extensions["something_new"] == "value"
    assert record.source.extensions["nested_extra"] == {"a": 1}


def test_the_extension_namespace_survives_a_second_pass() -> None:
    """Normalising an already-normalised record must not nest extensions inside extensions."""
    once = normalize_schema_version(_record(backfill="#250"))
    twice = normalize_schema_version(once.model_dump(mode="json"))
    assert twice.source.extensions == {"backfill": "#250"}


def test_strictness_is_kept_where_it_belongs() -> None:
    """A namespace for ``source`` does not loosen the declared record or its other sections."""
    with pytest.raises(ValidationError):
        normalize_schema_version({**_record(), "not_a_section": {"x": 1}})

    with pytest.raises(ValidationError):
        normalize_schema_version({**_record(), "source_url": ""})

    with pytest.raises(UnsupportedSchemaVersion):
        normalize_schema_version({**_record(), "schema_version": "9.9.9"})


def test_the_model_still_declares_what_it_declares() -> None:
    declared = set(SourceSection.model_fields)
    assert "backfill" not in declared, "the fix is a namespace, not two more fields"
    assert "extensions" in declared
    assert {"platform", "author", "created_at", "raw_ref"} <= declared
