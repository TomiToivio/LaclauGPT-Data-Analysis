"""Explicit Gemma 4 routing for canonical Analysis stages.

Deployment profiles may suggest a model, but operators can override them. Cloud
models are never selected implicitly. No network call happens at import time.
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache

from ..deployment import CLOUD_MODELS, DeploymentProfile
from .ollama import resolve_llm_host

MODELS: dict[str, str] = {
    "e2b": "gemma4:e2b",
    "e4b": "gemma4:e4b",
    "12b": "gemma4:12b",
    "26b": "gemma4:26b",
    "31b": "gemma4:31b",
    "31b-cloud": "gemma4:31b-cloud",
}

EMBEDDING_MODEL = os.environ.get("LACLAUGPT_EMBEDDING_MODEL", "embeddinggemma")
CAPABILITY_ORDER: list[str] = ["e2b", "e4b", "12b", "26b", "31b"]
STAGE_ROUTING: dict[str, str] = {
    "summary": "e4b",
    "discourse": "12b",
    "postprocess": "e2b",
    "populism": "12b",
    "entities": "e2b",
    "sentiment": "e2b",
    "topics": "12b",
    "temporal": "12b",
}
LONG_TEXT_CHARS = 8000
_TIER_VRAM_GB = {"e2b": 6, "e4b": 8, "12b": 13, "26b": 17, "31b": 20}


@lru_cache(maxsize=1)
def _loaded_models() -> set[str]:
    host = (resolve_llm_host() or "http://127.0.0.1:11434").rstrip("/")
    try:
        raw = subprocess.run(
            ["curl", "-s", f"{host}/api/tags"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
        return {str(m["name"]) for m in json.loads(raw or "{}").get("models", [])}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError):
        return set()


@lru_cache(maxsize=1)
def _free_vram_gb() -> float:
    try:
        raw = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
        per_gpu = [int(x) for x in raw.strip().splitlines() if x.strip()]
        return max(per_gpu, default=0) / 1024.0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0.0


def _stage_override(stage: str) -> str:
    key = "LACLAUGPT_MODEL_" + stage.upper().replace("-", "_")
    return os.environ.get(key, "").strip()


def validate_model_for_profile(model: str, profile: DeploymentProfile) -> None:
    """Enforce explicit cloud permission without constraining future model tags."""
    if model in CLOUD_MODELS and not profile.cloud_allowed:
        raise ValueError("cloud model requires explicit cloud permission")
    if model in CLOUD_MODELS and profile.llm != "ollama-cloud":
        raise ValueError("cloud model requires ollama-cloud mode")
    if profile.llm == "local-ollama" and model in CLOUD_MODELS:
        raise ValueError("local Ollama mode cannot silently route to cloud")


def resolve_profile_model(
    profile: DeploymentProfile,
    *,
    stage: str | None = None,
    override: str | None = None,
) -> str:
    """Resolve configured model without probing hardware or silently falling back."""
    model = (override or "").strip() or profile.model
    if stage:
        stage_override = _stage_override(stage)
        if stage_override:
            model = stage_override
    validate_model_for_profile(model, profile)
    return model


def pick_model(stage: str, text_len: int = 0) -> str:
    """Legacy local availability routing retained for existing callers."""
    override = _stage_override(stage)
    if override:
        if override in CLOUD_MODELS:
            raise ValueError("stage override may not silently route legacy local mode to cloud")
        return override

    tier = STAGE_ROUTING.get(stage, "26b")
    if text_len > LONG_TEXT_CHARS and tier in ("e2b", "e4b"):
        tier = "26b"
    loaded = _loaded_models()
    free = _free_vram_gb()
    start = CAPABILITY_ORDER.index(tier)
    for name in reversed(CAPABILITY_ORDER[: start + 1]):
        tag = MODELS[name]
        if tag not in loaded:
            continue
        if free == 0 or free >= _TIER_VRAM_GB[name] * 0.9:
            return tag
    for name in CAPABILITY_ORDER:
        if MODELS[name] in loaded:
            return MODELS[name]
    raise RuntimeError("no configured local model available on this Ollama host")


def pick_embedding_model() -> str:
    return EMBEDDING_MODEL


def routing_table() -> dict[str, str]:
    return {stage: pick_model(stage) for stage in STAGE_ROUTING}
