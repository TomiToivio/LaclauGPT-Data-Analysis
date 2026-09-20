"""Canonical Phase 1 research protocol configuration and codebook support.

This module is intentionally independent from inference and storage backends. It turns
public defaults, study profiles and optional private overlays into deterministic,
validated protocol snapshots whose fingerprints can be propagated through the existing
config_revision/codebook_revision provenance fields.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

PHASE = "phase-1"
SCHEMA_VERSION = "1"
_ALLOWED_ENTRY_STATES = {"authoritative", "discovered", "derived"}
_ALLOWED_PROVENANCE = {"theory", "researcher", "synthetic", "model", "derived"}
_SECRET_TOKENS = (
    "password", "secret", "token", "api_key", "access_key", "private_key",
    "credential", "authorization",
)
_REQUIRED_CONFIG_KEYS = {
    "schema_version", "phase", "study_id", "codebooks", "stages", "models",
    "storage", "execution", "filters", "outputs", "sampling", "retry", "provenance",
}
_REQUIRED_CODEBOOK_SECTIONS = {
    "evidence_modalities", "social_semiotic", "actors", "topics", "demands",
    "signifiers", "chains", "frontiers", "collective_subjects", "affects",
    "formations", "arenas", "languages", "regions", "platforms",
    "uncertainty", "provenance",
}


class ProtocolValidationError(ValueError):
    """Raised when Phase 1 protocol resources violate the public contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    if source.suffix.casefold() in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
    elif source.suffix.casefold() == ".json":
        data = json.loads(text)
    else:
        raise ProtocolValidationError(f"unsupported protocol format: {source.suffix}")
    if not isinstance(data, dict):
        raise ProtocolValidationError(f"protocol root must be a mapping: {source}")
    return data


def deep_merge(base: Mapping[str, Any], *overlays: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for overlay in overlays:
        _merge_into(merged, overlay)
    return merged


def _merge_into(target: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _merge_into(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).casefold()
            out[str(key)] = "<redacted>" if any(token in lowered for token in _SECRET_TOKENS) else redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _validate_id(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolValidationError(f"{location} must be a non-empty string")
    candidate = value.strip()
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")
    if any(ch not in allowed for ch in candidate):
        raise ProtocolValidationError(f"{location} contains unsupported characters: {candidate!r}")
    return candidate


def validate_config(config: Mapping[str, Any], *, strict: bool = True) -> None:
    missing = sorted(_REQUIRED_CONFIG_KEYS - set(config))
    if missing:
        raise ProtocolValidationError(f"Phase 1 config missing keys: {', '.join(missing)}")
    if str(config.get("schema_version")) != SCHEMA_VERSION:
        raise ProtocolValidationError(
            f"unsupported Phase 1 config schema_version={config.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    if config.get("phase") != PHASE:
        raise ProtocolValidationError(f"Phase 1 config must set phase={PHASE!r}")
    _validate_id(config.get("study_id"), "study_id")
    codebooks = config.get("codebooks")
    if not isinstance(codebooks, Mapping) or not codebooks.get("paths"):
        raise ProtocolValidationError("codebooks.paths must contain at least one codebook path")
    stages = config.get("stages")
    if not isinstance(stages, Mapping) or not stages:
        raise ProtocolValidationError("stages must be a non-empty mapping")
    sampling = config.get("sampling")
    if not isinstance(sampling, Mapping) or "seed" not in sampling:
        raise ProtocolValidationError("sampling.seed is required for reproducible sampling")
    if strict:
        allowed = _REQUIRED_CONFIG_KEYS | {
            "profile", "prompts", "context_memory", "periodic_reports", "machine",
            "multimodal", "metadata", "git_commit",
        }
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ProtocolValidationError(f"unknown Phase 1 config keys: {', '.join(unknown)}")


def _iter_entries(codebook: Mapping[str, Any]):
    for section, values in codebook.items():
        if section in {"schema_version", "phase", "codebook_id", "revision", "description"}:
            continue
        if isinstance(values, list):
            for index, entry in enumerate(values):
                if isinstance(entry, Mapping):
                    yield section, index, entry


def validate_codebook(codebook: Mapping[str, Any]) -> None:
    if str(codebook.get("schema_version")) != SCHEMA_VERSION:
        raise ProtocolValidationError(
            f"unsupported codebook schema_version={codebook.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    if codebook.get("phase") != PHASE:
        raise ProtocolValidationError(f"Phase 1 codebook must set phase={PHASE!r}")
    _validate_id(codebook.get("codebook_id"), "codebook_id")
    missing = sorted(_REQUIRED_CODEBOOK_SECTIONS - set(codebook))
    if missing:
        raise ProtocolValidationError(f"Phase 1 codebook missing sections: {', '.join(missing)}")

    ids: set[str] = set()
    aliases: dict[str, str] = {}
    for section, index, entry in _iter_entries(codebook):
        entry_id = _validate_id(entry.get("id"), f"{section}[{index}].id")
        if entry_id in ids:
            raise ProtocolValidationError(f"duplicate codebook id: {entry_id}")
        ids.add(entry_id)
        state = entry.get("state", "authoritative")
        if state not in _ALLOWED_ENTRY_STATES:
            raise ProtocolValidationError(f"{entry_id}: invalid state {state!r}")
        provenance = entry.get("provenance", "theory")
        if provenance not in _ALLOWED_PROVENANCE:
            raise ProtocolValidationError(f"{entry_id}: invalid provenance {provenance!r}")
        if state == "discovered" and provenance != "model":
            raise ProtocolValidationError(f"{entry_id}: discovered entries must use provenance=model")
        if state == "authoritative" and provenance == "model":
            raise ProtocolValidationError(
                f"{entry_id}: model-discovered entries cannot be authoritative without researcher promotion"
            )
        for alias in entry.get("aliases", []) or []:
            if not isinstance(alias, str) or not alias.strip():
                raise ProtocolValidationError(f"{entry_id}: aliases must be non-empty strings")
            norm = alias.casefold().strip()
            owner = aliases.get(norm)
            if owner and owner != entry_id:
                raise ProtocolValidationError(f"alias collision {alias!r}: {owner} vs {entry_id}")
            aliases[norm] = entry_id
        refs = entry.get("refs", []) or []
        if not isinstance(refs, list):
            raise ProtocolValidationError(f"{entry_id}: refs must be a list")

    dangling: list[str] = []
    for section, index, entry in _iter_entries(codebook):
        for ref in entry.get("refs", []) or []:
            if ref not in ids:
                dangling.append(f"{section}[{index}] -> {ref}")
    if dangling:
        raise ProtocolValidationError("dangling codebook refs: " + ", ".join(dangling))


@dataclass(frozen=True)
class Phase1Protocol:
    config: Mapping[str, Any]
    codebooks: tuple[Mapping[str, Any], ...]
    config_hash: str
    codebook_hash: str

    @property
    def study_id(self) -> str:
        return str(self.config["study_id"])

    def provenance(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "study_id": self.study_id,
            "config_revision": self.config_hash,
            "codebook_revision": self.codebook_hash,
            "prompt_resources": copy.deepcopy(dict(self.config.get("prompts", {}))),
            "models": copy.deepcopy(dict(self.config.get("models", {}))),
            "execution_profile": self.config.get("execution", {}).get("profile", ""),
            "machine_profile": self.config.get("machine", {}).get("profile", ""),
        }

    def redacted_config(self) -> dict[str, Any]:
        return redact(self.config)

    def stale_against(self, *, config_revision: str = "", codebook_revision: str = "") -> bool:
        return bool(
            (config_revision and config_revision != self.config_hash)
            or (codebook_revision and codebook_revision != self.codebook_hash)
        )


def compose_protocol(
    *,
    defaults: Mapping[str, Any],
    profile: Mapping[str, Any],
    codebooks: Sequence[Mapping[str, Any]],
    private_overlay: Mapping[str, Any] | None = None,
    machine_overlay: Mapping[str, Any] | None = None,
    execution_overlay: Mapping[str, Any] | None = None,
    strict: bool = True,
) -> Phase1Protocol:
    config = deep_merge(
        defaults,
        profile,
        private_overlay or {},
        machine_overlay or {},
        execution_overlay or {},
    )
    validate_config(config, strict=strict)
    normalized_codebooks: list[dict[str, Any]] = []
    for source in codebooks:
        item = copy.deepcopy(dict(source))
        validate_codebook(item)
        normalized_codebooks.append(item)
    config_hash = fingerprint(config)
    codebook_hash = fingerprint(normalized_codebooks)
    return Phase1Protocol(
        config=config,
        codebooks=tuple(normalized_codebooks),
        config_hash=config_hash,
        codebook_hash=codebook_hash,
    )


def compose_protocol_from_files(
    *,
    defaults_path: str | Path,
    profile_path: str | Path,
    codebook_paths: Sequence[str | Path],
    private_overlay_path: str | Path | None = None,
    machine_overlay_path: str | Path | None = None,
    execution_overlay_path: str | Path | None = None,
    strict: bool = True,
) -> Phase1Protocol:
    return compose_protocol(
        defaults=load_mapping(defaults_path),
        profile=load_mapping(profile_path),
        codebooks=[load_mapping(path) for path in codebook_paths],
        private_overlay=load_mapping(private_overlay_path) if private_overlay_path else None,
        machine_overlay=load_mapping(machine_overlay_path) if machine_overlay_path else None,
        execution_overlay=load_mapping(execution_overlay_path) if execution_overlay_path else None,
        strict=strict,
    )
