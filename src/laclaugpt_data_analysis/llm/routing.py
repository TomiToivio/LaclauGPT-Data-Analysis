"""Ollama model routing without import-time network work."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    mode: str
    model: str
    allow_cloud: bool = False


def resolve_model(*, machine: str = "laptop", requested_model: str | None = None,
                  cloud_allowed: bool = False) -> ModelRoute:
    if requested_model:
        is_cloud = requested_model.endswith("-cloud") or requested_model.endswith(":cloud")
        if is_cloud and not cloud_allowed:
            raise ValueError("cloud model requested but cloud inference is not allowed")
        return ModelRoute("cloud" if is_cloud else "local", requested_model, cloud_allowed)
    if machine == "roihu":
        return ModelRoute("local", "gemma4:26b", cloud_allowed)
    if machine == "linux-server":
        return ModelRoute("local", "gemma4:12b", cloud_allowed)
    if cloud_allowed:
        return ModelRoute("cloud", "gemma4:31b-cloud", True)
    return ModelRoute("local", "gemma4:e4b", False)
