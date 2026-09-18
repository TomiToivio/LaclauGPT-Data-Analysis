#!/usr/bin/env python3
"""Offline contract-conformance check for the Analysis module.

Analysis enriches canonical research records produced by Collection and consumed
by Visualization. This tool verifies, without network access or a live database,
that the module still honours the project-wide contracts:

* ``docs/CANONICAL_DATA_CONTRACT.md`` — ``source_url`` is the semantic identity
  and must survive canonicalization and every storage/transport round trip;
* the shared cross-module parity fixture — the versioned schema-drift tripwire
  under ``fixtures/cross_module/canonical_parity_v1.json`` in the meta-repository;
* ``docs/STORAGE_BACKEND_CONTRACT.md`` — ``auto | mongodb | csv`` semantics, with
  local CSV/filesystem operation as a first-class zero-infrastructure mode.

The check is deliberately observational: it reads, reconstructs and compares. It
never writes research data, contacts a service, or mutates configuration. It is
suitable as a local preflight and as a CI gate.

Exit status is 0 when every check passes and 1 otherwise, so it can be wired
into a pipeline directly.

Usage::

    python tools/verify_contracts.py
    python tools/verify_contracts.py --fixture /path/to/canonical_parity_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC = REPOSITORY_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Repository-local vendored copy of the meta-repository fixture.
DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "canonical_parity_v1.json"

# The invariants the fixture README defines as normative.
EXPECTED_SOURCE_URL = "https://example.invalid/laclaugpt/synthetic/record-001"
EXPECTED_LEGACY_ID = "legacy-001"
EXPECTED_LEGACY_FIELD = "must-survive-roundtrip"
EXPECTED_FIXTURE_SHA256 = "e7132b2c24d809b9d841fe7aeef4fbc92c82c2078a5439f27752f9650dddd7aa"


class CheckFailure(Exception):
    """A contract invariant was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def _load_fixture(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"parity fixture not found: {path}")
    raw = path.read_bytes()
    if path.resolve() == DEFAULT_FIXTURE.resolve():
        import hashlib

        digest = hashlib.sha256(raw).hexdigest()
        _require(
            digest == EXPECTED_FIXTURE_SHA256,
            "vendored canonical parity fixture drifted from the authoritative shared bytes "
            f"(expected {EXPECTED_FIXTURE_SHA256}, got {digest})",
        )
    payload = json.loads(raw.decode("utf-8"))
    _require(isinstance(payload, dict), "parity fixture must be a JSON object")
    return payload


def check_fixture_invariants(record: Any) -> None:
    """Verify the normative invariants of the shared fixture.

    These mirror the fixture README, so a change here means either the fixture
    moved on (update this tool) or the module's record model drifted (fix the
    model). Both should fail CI.
    """
    _require(record.source_url == EXPECTED_SOURCE_URL, (
        f"canonical identity changed: {record.source_url!r}"
    ))
    _require(
        record.source_native_ids.get("legacy_document_id") == EXPECTED_LEGACY_ID,
        "legacy source identifier was dropped",
    )
    _require(
        record.source.raw_metadata.get("legacy_optional_field") == EXPECTED_LEGACY_FIELD,
        "legacy optional source metadata was dropped",
    )

    # Optional multimodal-shaped content must be preserved as references only.
    _require(record.content.transcripts, "transcripts were dropped")
    _require(record.content.ocr, "ocr observations were dropped")
    _require(record.content.frames, "frame references were dropped")
    _require(record.content.media_references, "media references were dropped")
    _require(
        record.content.media_references[0].object_ref.startswith("fixture://"),
        "media reference must remain a reference, not embedded media",
    )

    # Identity must be reachable from every evidence-bearing edge.
    for unit in getattr(record, "source_units", []) or []:
        unit_url = (
            unit.get("source_url") if isinstance(unit, dict) else getattr(unit, "source_url", None)
        )
        if unit_url:
            _require(
                unit_url == EXPECTED_SOURCE_URL,
                "a source unit lost the canonical identity",
            )

    _require(
        record.review.status == "PROVISIONAL",
        "review state must remain human-controlled (fixture is PROVISIONAL)",
    )


def check_review_is_not_promoted(record: Any) -> None:
    """A machine pass must never promote provisional evidence.

    The fixture carries a CANDIDATE_INTERPRETATION with PROVISIONAL review
    status. Canonicalization and round trips must not silently upgrade it.
    """
    serialized = json.dumps(record.canonical_dict(), sort_keys=True)
    _require(
        "CANDIDATE_INTERPRETATION" in serialized,
        "candidate interpretation was dropped during reconstruction",
    )
    _require(
        record.review.status == "PROVISIONAL",
        "provisional review state was promoted without human review",
    )


def check_round_trips(record: Any) -> list[str]:
    """Every supported local adapter must reconstruct the same logical record.

    The reference is materialised through the same normalisation the adapters
    apply (``ensure_research_layers``), because writing/reading a record
    deterministically fills the derived ``human_readable`` / ``intermediate`` /
    ``legacy`` layers. Comparing an un-materialised record against a
    round-tripped one would report a difference that is not a loss.
    """
    from laclaugpt_data_analysis.interchange import (
        read_csv,
        read_jsonl,
        read_sqlite,
        write_csv,
        write_jsonl,
        write_sqlite,
    )
    from laclaugpt_data_analysis.research_record import ensure_research_layers

    reference_record = ensure_research_layers(record)
    reference = reference_record.canonical_dict()
    verified: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, suffix, write, read in (
            ("jsonl", "jsonl", write_jsonl, read_jsonl),
            ("csv", "csv", write_csv, read_csv),
            ("sqlite", "sqlite3", write_sqlite, read_sqlite),
        ):
            target = root / f"records.{suffix}"
            write(target, [reference_record])
            restored = read(target)[0]
            _require(
                restored.canonical_dict() == reference,
                f"{name} round trip did not reconstruct the same logical record",
            )
            _require(
                restored.source_url == EXPECTED_SOURCE_URL,
                f"{name} round trip lost the canonical identity",
            )
            verified.append(name)
    return verified


def check_storage_selector_semantics() -> None:
    """``csv`` must never go remote, and a misconfiguration must fail closed.

    Only offline-observable selector behaviour is asserted. Resolving ``auto``
    with a configured endpoint performs a bounded reachability probe by design,
    so no assertion here depends on a live server. The fail-closed rules are
    configuration-only and are the safety-critical part of the contract.
    """
    from laclaugpt_data_analysis.config import Settings
    from laclaugpt_data_analysis.storage import resolved_storage_backend

    # An explicit csv selection resolves to local operation with no endpoint.
    _require(
        resolved_storage_backend(Settings(storage_backend="csv")) == "csv",
        "explicit csv selection must resolve to local operation",
    )

    # auto with no configured endpoint must stay local: it must not invent one.
    _require(
        resolved_storage_backend(Settings(storage_backend="auto")) != "mongodb",
        "auto must not select mongodb without an explicitly configured endpoint",
    )

    # A distributed deployment that resolves to a local backend must fail closed
    # rather than silently degrade to csv.
    try:
        resolved_storage_backend(
            Settings(storage="distributed", storage_backend="csv")
        )
    except ValueError:
        pass
    else:
        raise CheckFailure(
            "distributed storage must fail closed instead of degrading to csv"
        )

    # mongodb without a configured endpoint must fail closed with a clear error.
    try:
        resolved_storage_backend(Settings(storage_backend="mongodb", mongo_url=""))
    except ValueError:
        pass
    else:
        raise CheckFailure("mongodb selection without an endpoint must fail closed")


def check_schema_version_is_declared() -> None:
    """The module must declare the canonical schema version it emits."""
    from laclaugpt_data_analysis.canonical import SCHEMA_VERSION

    _require(bool(SCHEMA_VERSION), "the canonical schema version must be declared")
    parts = str(SCHEMA_VERSION).split(".")
    _require(
        len(parts) >= 2 and all(part.isdigit() for part in parts[:2]),
        f"schema version must be dotted numeric, got {SCHEMA_VERSION!r}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Analysis contract-conformance check.")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="path to the shared canonical parity fixture",
    )
    args = parser.parse_args(argv)

    from laclaugpt_data_analysis.interchange import record_from_json

    payload = _load_fixture(args.fixture)
    record = record_from_json(json.dumps(payload))

    checks: list[tuple[str, Any]] = [
        ("fixture invariants", lambda: check_fixture_invariants(record)),
        ("review state is not promoted", lambda: check_review_is_not_promoted(record)),
        ("schema version declared", check_schema_version_is_declared),
        ("storage selector semantics", check_storage_selector_semantics),
    ]

    failures: list[str] = []
    for name, check in checks:
        try:
            check()
        except CheckFailure as exc:
            failures.append(f"{name}: {exc}")
            print(f"FAIL  {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - report any defect, never crash
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok    {name}")

    try:
        adapters = check_round_trips(record)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"local adapter round trips: {type(exc).__name__}: {exc}")
        print(f"ERROR local adapter round trips: {type(exc).__name__}: {exc}")
    else:
        print(f"ok    local adapter round trips ({', '.join(adapters)})")

    if failures:
        print(f"\n{len(failures)} contract check(s) failed")
        return 1
    print("\nall Analysis contract checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
