"""Task-difficulty stage routing for local Gemma-style model tiers.

Migrated from ``laclaugpt/model_routing.py`` with the same conservative
defaults: stage routing stays measurement-backed and operators override a
stage via ``LACLAUGPT_MODEL_<STAGE>`` without editing code. The resolved tag
is returned so provenance records what actually ran.

No network call happens at import time; ``_loaded_models`` and ``_free_vram_gb``
contact a host only when stage resolution is actually invoked.
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache

MODELS: dict[str, str] = {
    "e2b": "gemma4:e2b",
    "e4b": "gemma4:e4b",
    "12b": "batiai/gemma4-12b:q6",
    "26b": "gemma4:26b",
    "31b": "gemma4:31b",
}

EMBEDDING_MODEL = os.environ.get("LACLAUGPT_EMBEDDING_MODEL", "embeddinggemma")

# Ascending capability order for fallback walks. 31b is benchmark/reference
# capacity, not a current default pipeline route.
CAPABILITY_ORDER: list[str] = ["e2b", "e4b", "12b", "26b", "31b"]

# Public routing policy only. Host-specific capacity measurements and residency
# decisions belong in private deployment notes, not in this module.
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

# Texts longer than this escalate cheap e2b/e4b stages to the high-capability
# tier, preserving the historical behaviour without changing theory-sensitive
# stage defaults.
LONG_TEXT_CHARS = 8000

_TIER_VRAM_GB = {"e2b": 6, "e4b": 8, "12b": 13, "26b": 17, "31b": 20}


@lru_cache(maxsize=1)
def _loaded_models() -> set[str]:
    """Names of models present in the local Ollama instance (best effort)."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        raw = subprocess.run(
            ["curl", "-s", f"{host}/api/tags"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        return {m["name"] for m in json.loads(raw).get("models", [])}
    except Exception:
        return set()


@lru_cache(maxsize=1)
def _free_vram_gb() -> float:
    """Free VRAM across GPUs, best effort via nvidia-smi."""
    try:
        raw = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        per_gpu = [int(x) for x in raw.strip().splitlines() if x.strip()]
        return max(per_gpu, default=0) / 1024.0
    except Exception:
        return 0.0


def _stage_override(stage: str) -> str:
    key = "LACLAUGPT_MODEL_" + stage.upper().replace("-", "_")
    return os.environ.get(key, "").strip()


def pick_model(stage: str, text_len: int = 0) -> str:
    """Resolve the local model for one pipeline stage.

    An explicit ``LACLAUGPT_MODEL_<STAGE>`` tag wins and is returned unchanged
    so stage-level model choice can be configured externally and recorded in
    provenance. Without an override: stage routing -> long-text escalation ->
    availability/VRAM fallback. Raises ``RuntimeError`` when no configured
    local model is available on the host.
    """
    override = _stage_override(stage)
    if override:
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
    """Return the configured embedding-specific Ollama model tag."""
    return EMBEDDING_MODEL


def routing_table() -> dict[str, str]:
    """Resolved routing for logging/provenance."""
    return {stage: pick_model(stage) for stage in STAGE_ROUTING}