"""Layered, inspectable run configuration for LaclauGPT Data Analysis.

Composition order is deliberately explicit:
project/study -> arena -> machine -> execution -> explicit overrides.
The resulting snapshot is immutable from the caller's point of view, hashable,
and safe to store in provenance without exposing private source files.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

_LAYER_ORDER = ("project", "arena", "machine", "execution")
_IDENTITY_KEYS = {"project", "arena", "machine", "execution"}


def _deep_merge(target: dict[str, Any], patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _load_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    text = os.path.expandvars(source.read_text(encoding="utf-8"))
    if source.suffix.casefold() in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
    elif source.suffix.casefold() == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"unsupported configuration format: {source.suffix}")
    if not isinstance(data, dict):
        raise ValueError(f"configuration root must be a mapping: {source}")
    return data


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(frozen=True)
class EffectiveRunConfig:
    project: str
    arena: str
    machine: str
    execution: str
    values: Mapping[str, Any]
    config_hash: str
    source_fingerprints: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return _jsonable(self.values)

    def provenance(self) -> dict[str, Any]:
        values = self.as_dict()
        return {
            "project_id": self.project,
            "arena": self.arena,
            "machine_profile": self.machine,
            "execution_profile": self.execution,
            "effective_config_hash": self.config_hash,
            "context_profile": values.get("context_profile", "balanced"),
            "codebook": values.get("codebook", {}),
            "model_routing": values.get("models", values.get("model", {})),
            "storage": values.get("storage", values.get("backends", {})),
            "rag_enabled": bool(values.get("rag", {}).get("enabled", False)),
            "pipeline_version": values.get("pipeline_version", ""),
            "source_fingerprints": dict(self.source_fingerprints),
        }


def compose_run_config(
    *,
    project: str,
    arena: str = "",
    machine: str = "local",
    execution: str = "cli",
    project_config: Mapping[str, Any] | None = None,
    arena_config: Mapping[str, Any] | None = None,
    machine_config: Mapping[str, Any] | None = None,
    execution_config: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
    source_fingerprints: Mapping[str, str] | None = None,
) -> EffectiveRunConfig:
    """Compose one immutable configuration snapshot.

    The function is intentionally storage-agnostic. Callers may load public or
    private configuration files externally and pass mappings here. Explicit
    overrides are last and may change runtime values, but may not replace layer
    identities or project-owned analysis switches wholesale.
    """
    layers = (
        project_config or {},
        arena_config or {},
        machine_config or {},
        execution_config or {},
    )
    merged: dict[str, Any] = {}
    for layer in layers:
        _deep_merge(merged, layer)

    if overrides:
        forbidden = _IDENTITY_KEYS & set(overrides)
        if forbidden:
            raise ValueError(f"overrides may not replace layer identities: {sorted(forbidden)}")
        _deep_merge(merged, overrides)

    merged["project"] = project
    merged["arena"] = arena
    merged["machine"] = machine
    merged["execution"] = execution
    merged.setdefault("context_profile", "balanced")

    canonical = json.dumps(_jsonable(merged), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return EffectiveRunConfig(
        project=project,
        arena=arena,
        machine=machine,
        execution=execution,
        values=_freeze(merged),
        config_hash=digest,
        source_fingerprints=MappingProxyType(dict(source_fingerprints or {})),
    )


def compose_run_config_from_files(
    *,
    project: str,
    project_path: str | Path,
    arena: str = "",
    arena_path: str | Path | None = None,
    machine: str = "local",
    machine_path: str | Path | None = None,
    execution: str = "cli",
    execution_path: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> EffectiveRunConfig:
    paths = {
        "project": Path(project_path),
        "arena": Path(arena_path) if arena_path else None,
        "machine": Path(machine_path) if machine_path else None,
        "execution": Path(execution_path) if execution_path else None,
    }
    configs: dict[str, dict[str, Any]] = {}
    fingerprints: dict[str, str] = {}
    for name in _LAYER_ORDER:
        path = paths[name]
        if path is None:
            configs[name] = {}
            continue
        raw = path.read_bytes()
        fingerprints[name] = hashlib.sha256(raw).hexdigest()
        configs[name] = _load_mapping(path)

    return compose_run_config(
        project=project,
        arena=arena,
        machine=machine,
        execution=execution,
        project_config=configs["project"],
        arena_config=configs["arena"],
        machine_config=configs["machine"],
        execution_config=configs["execution"],
        overrides=overrides,
        source_fingerprints=fingerprints,
    )
