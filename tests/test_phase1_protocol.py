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


def _protocol():
    return compose_protocol(
        defaults=load_mapping(DEFAULTS),
        profile=load_mapping(AI26),
        codebooks=[load_mapping(CODEBOOK)],
    )


def test_ai26_protocol_is_deterministic_and_phase1():
    first = _protocol()
    second = _protocol()
    assert first.study_id == "ai26"
    assert first.config["phase"] == "phase-1"
    assert first.config_hash == second.config_hash
    assert first.codebook_hash == second.codebook_hash
    assert first.provenance()["config_revision"] == first.config_hash
    assert first.provenance()["codebook_revision"] == first.codebook_hash


def test_ai26_uses_existing_canonical_formation_ids():
    protocol = _protocol()
    assert protocol.config["metadata"]["formations"] == (
        "accelerationist",
        "existential_risk",
        "left_accelerationist",
        "ai_safety",
        "critical_ai",
        "anti_ai",
    )


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


def test_protocol_snapshot_is_deeply_immutable():
    protocol = _protocol()
    with pytest.raises(TypeError):
        protocol.config["sampling"]["seed"] = 1
    with pytest.raises(TypeError):
        protocol.codebooks[0]["actors"][0]["label"] = "mutated"


def test_codebook_rejects_alias_collision():
    data = load_mapping(CODEBOOK)
    data["actors"] = [
        {"id": "actor.one", "label": "One", "aliases": ["same"], "state": "authoritative", "provenance": "researcher"},
        {"id": "actor.two", "label": "Two", "aliases": ["SAME"], "state": "authoritative", "provenance": "researcher"},
    ]
    with pytest.raises(ProtocolValidationError, match="alias collision"):
        validate_codebook(data)


def test_codebook_rejects_alias_collision_with_id():
    data = load_mapping(CODEBOOK)
    data["actors"] = [
        {"id": "actor.one", "label": "One", "aliases": ["actor.two"], "state": "authoritative", "provenance": "researcher"},
        {"id": "actor.two", "label": "Two", "state": "authoritative", "provenance": "researcher"},
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


@pytest.mark.parametrize("bad_value", ["not-a-list", [None]])
def test_codebook_rejects_malformed_required_sections(bad_value):
    data = load_mapping(CODEBOOK)
    data["actors"] = bad_value
    with pytest.raises(ProtocolValidationError, match="actors"):
        validate_codebook(data)


def test_redaction_hides_credentials_recursively():
    value = {
        "models": {
            "api_token": "abc",
            "nested": [{"password": "secret"}],
        },
        "safe": "ok",
    }
    result = redact(value)
    assert result["models"]["api_token"] == "<redacted>"
    assert result["models"]["nested"][0]["password"] == "<redacted>"
    assert result["safe"] == "ok"


def test_redaction_sanitizes_connection_url_credentials_and_secret_query():
    result = redact(
        {
            "redis_url": "redis://user:password@example.test:6379/0",
            "endpoint_url": "https://example.test/api?token=abc&region=fi",
        }
    )
    assert result["redis_url"] == "redis://<redacted>@example.test:6379/0"
    assert "abc" not in result["endpoint_url"]
    assert "region=fi" in result["endpoint_url"]


def test_stale_detection_tracks_config_and_codebook_revision():
    protocol = _protocol()
    assert not protocol.stale_against(
        config_revision=protocol.config_hash,
        codebook_revision=protocol.codebook_hash,
    )
    assert protocol.stale_against(config_revision="old")
