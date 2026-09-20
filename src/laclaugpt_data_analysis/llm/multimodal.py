"""Audited multimodal adapter for frame-analysis model calls.

Text-only provider behavior is unchanged. For a frame-analysis request whose task
identifies a canonical frame with a readable local ``media_ref``, the adapter attaches
the actual image to Ollama's user message and records exactly which frame/path was sent.
Remote object references must first be materialized by the preprocessing/storage layer.
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from .base import ChatRequest, LLMCallProvenance, LLMResponse, ProviderError, merge_options
from .ollama import (
    LLM_CLOUD_ENV,
    LLM_DEFAULT_CLOUD,
    OllamaProvider,
    _client,
    _fallback_allowed,
    _looks_cloud,
    _retryable_local_error,
    model_digest,
    resolve_endpoint,
    resolve_llm_host,
)

logger = logging.getLogger(__name__)


def _local_image(ref: str | None) -> str | None:
    if not ref:
        return None
    raw = str(ref)
    if raw.startswith("file://"):
        raw = raw[7:]
    if "://" in raw:
        return None
    path = Path(raw).expanduser()
    return str(path) if path.is_file() else None


def _ollama_chat_with_images(provider: OllamaProvider, request: ChatRequest) -> LLMResponse:
    """Ollama call equivalent to OllamaProvider.chat, adding user-message images."""
    mode, resolved = resolve_endpoint(request.model)
    use_model = resolved
    actual_mode = mode
    fallback_used = False
    fallback_reason = ""
    opts = merge_options(request.options)
    kwargs: dict[str, Any] = {"format": request.schema} if request.schema is not None else {}
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "").strip()
    if keep_alive:
        kwargs["keep_alive"] = keep_alive
    if os.environ.get("OLLAMA_THINK", "").strip().casefold() not in {"1", "true", "yes", "on"}:
        kwargs["think"] = False
    user_message: dict[str, Any] = {"role": "user", "content": request.user}
    if request.images:
        user_message["images"] = list(request.images)
    messages = [
        {"role": "system", "content": request.system},
        user_message,
    ]
    host = resolve_llm_host(provider._host_override)
    client = _client(host)
    try:
        response = client.chat(model=use_model, messages=messages, options=opts, **kwargs)
    except Exception as exc:
        can_fallback = (
            mode == "local"
            and not _looks_cloud(use_model)
            and _fallback_allowed(request.allow_cloud_fallback)
            and _retryable_local_error(exc)
        )
        if not can_fallback:
            raise ProviderError(f"Ollama multimodal call failed: {exc}") from exc
        cloud_model = os.environ.get(LLM_CLOUD_ENV) or LLM_DEFAULT_CLOUD
        response = client.chat(model=cloud_model, messages=messages, options=opts, **kwargs)
        use_model = cloud_model
        actual_mode = "cloud"
        fallback_used = True
        fallback_reason = f"{type(exc).__name__}: {exc}"
    return LLMResponse(
        content=response["message"]["content"],
        provenance=LLMCallProvenance(
            requested_mode=mode,
            requested_model=request.model,
            resolved_model=resolved,
            actual_mode=actual_mode,
            actual_model=use_model,
            actual_model_digest=model_digest(use_model),
            endpoint=host or "default endpoint",
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        ),
    )


class FrameAwareProvider:
    """Attach actual local frame pixels to matching frame-analysis requests."""

    def __init__(self, provider, frames, media_references=()) -> None:
        self.provider = provider
        local_media = {
            str(media.ref): media.local_ref
            for media in media_references
            if getattr(media, "ref", None) and getattr(media, "local_ref", None)
        }
        self._frames: dict[str, str] = {}
        for frame in frames:
            ref = getattr(frame, "media_ref", None)
            candidate = local_media.get(str(ref), ref)
            image = _local_image(candidate)
            if image is not None:
                self._frames[str(frame.id)] = image
        self.attachments: list[dict[str, Any]] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        selected: tuple[str, str] | None = None
        for frame_id, image in self._frames.items():
            generic_marker = f"Analyse frame {frame_id} at "
            ep24_marker = f"Frame: {frame_id}\n"
            if generic_marker in request.user or ep24_marker in request.user:
                selected = (frame_id, image)
                break
        if selected is None:
            return self.provider.chat(request)
        frame_id, image = selected
        enriched = replace(request, images=(image,))
        if isinstance(self.provider, OllamaProvider):
            response = _ollama_chat_with_images(self.provider, enriched)
        else:
            response = self.provider.chat(enriched)
        self.attachments.append(
            {
                "frame_id": frame_id,
                "media_ref": image,
                "attachment_type": "direct_image_pixels",
            }
        )
        return response

    def audit(self) -> dict[str, Any]:
        return {
            "declared": "direct_image_pixels" if self.attachments else "textual_derivatives_only",
            "attachments": list(self.attachments),
            "eligible_local_frames": sorted(self._frames),
        }
