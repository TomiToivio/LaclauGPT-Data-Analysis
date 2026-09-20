from __future__ import annotations

from pathlib import Path

import pytest

from laclaugpt_data_analysis.phase1_protocol import (
    ProtocolValidationError,
    compose_protocol,
    fingerprint,
    load_mapping,
    redact,
    validate_codebook,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "config" / "phase1" / "defaults.yaml"
AI26 = ROOT / "config" / "phase1" / "ai26.yaml"
CODEBOOK = ROOT / "codebooks" / "public" / "phase1_v1.yaml"


def test_ai26_protocol_is_deterministic_and_phase1():
    defaults = load_mapping(DEFAULTS)
    profile = load_mapping(AI26)
    codebook = load_mapping(CODEBOOK)
    first = compose_protocol(defaults=defaults, profile=profile, codebooks=[codebook])
    second = compose_protocol(defaults=defaults, profile=profile, codebooks=[codebook])
    assert first.study_id == "ai26"
    assert first.config["phase"] == "phase-1"
    assert first.config_hash == second.config_hash
    assert first.codebook_hash == second.codebook_hash
    assert first.provenance()["config_revision"] == first.config_hash
    assert first.provenance()["codebook_revision"] == first.codebook_hash


def test_private_overlay_has_high_precedence():
    protocol = compose_protocol(
        defaults=load_mapping(DEFAULTS),
        profile=load_mapping(AI26),
        codebooks=[load_mapping(CODEBOOK)],
        private_overlay={"models": {"routing": {"analysis": "private-model"}}},
    )
    assert protocol.config["models"]["routing"]["analysis"] == "private-model"


def test_fingerprint_ignores_mapping_order_but_not_meaningful_edits():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


def test_codebook_rejects_alias_collision():
    data = load_mapping(CODEBOOK)
    data["actors"] = [
        {"id": "actor.one", "label": "One", "aliases": ["same"], "state": "authoritative", "provenance": "researcher"},
        {"id": "actor.two", "label": "Two", "aliases": ["SAME"], "state": "authoritative", "provenance": "researcher"},
    ]
    with pytest.raises(ProtocolValidationError, match="alias collision"):
        validate_codebook(data)


def test_codebook_rejects_model_candidate_promoted_to_authoritative():
    data = load_mapping(CODEBOOK)
    data["actors"] = [
        {"id": "actor.bad", "label": "Bad", "state": "authoritative", "provenance": "model"}
    ]
    with pytest.raises(ProtocolValidationError, match="cannot be authoritative"):
        validate_codebook(data)


def test_codebook_rejects_dangling_reference():
    data = load_mapping(CODEBOOK)
    data["actors"] = [
        {"id": "actor.one", "label": "One", "refs": ["missing.ref"], "state": "authoritative", "provenance": "researcher"}
    ]
    with pytest.raises(ProtocolValidationError, match="dangling"):
        validate_codebook(data)


def test_redaction_hides_credentials_recursively():
    value = {"models": {"api_token": "abc", "nested": [{"password": "secret"}]}, "safe": "ok"}
    result = redact(value)
    assert result["models"]["api_token"] == "<redacted>"
    assert result["models"]["nested"][0]["password"] == "<redacted>"
    assert result["safe"] == "ok"


def test_stale_detection_tracks_config_and_codebook_revision():
    protocol = compose_protocol(
        defaults=load_mapping(DEFAULTS),
        profile=load_mapping(AI26),
        codebooks=[load_mapping(CODEBOOK)],
    )
    assert not protocol.stale_against(
        config_revision=protocol.config_hash,
        codebook_revision=protocol.codebook_hash,
    )
    assert protocol.stale_against(config_revision="old")
