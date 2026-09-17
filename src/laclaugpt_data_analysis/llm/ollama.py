"""Ollama provider implementation behind the neutral LLMProvider boundary.

Behaviour migrated from the monolith's ``llm.py``:

- mode resolution: explicit local/cloud/external/auto configuration wins;
- deployment aliases such as ``local-ollama`` and ``ollama-cloud`` are normalized;
- explicit host arguments win over ``OLLAMA_HOST``, which wins over the documented
  ``LACLAUGPT_LLM_ENDPOINT`` alias;
- local -> cloud fallback is forbidden by default and must be explicitly
  authorised per call or via ``LLM_ALLOW_CLOUD_FALLBACK=1``;
- thinking-mode budget burn on structured output is disabled unless
  ``OLLAMA_THINK`` opts in;
- deterministic sampling defaults keep analysis runs reproducible.

The ``ollama`` package is imported lazily: importing this module never touches
the network and works without ``ollama`` installed.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from typing import Any
from urllib.parse import urlparse

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
    ProviderError,
    merge_options,
)

logger = logging.getLogger(__name__)

LLM_MODE_ENV = "LLM_MODE"
LLM_MODE_ENV_ALIASES = ("LACLAUGPT_LLM_MODE", "LACLAUGPT_OLLAMA_MODE")
LLM_HOST_ENV = "OLLAMA_HOST"
LLM_ENDPOINT_ENV = "LACLAUGPT_LLM_ENDPOINT"
LLM_CLOUD_ENV = "LLM_CLOUD_MODEL"
LLM_LOCAL_MODEL_ENV = "LLM_LOCAL_MODEL"
LLM_ALLOW_CLOUD_FALLBACK_ENV = "LLM_ALLOW_CLOUD_FALLBACK"
LLM_LOCAL_MIN_VRAM_GB = float(os.environ.get("LLM_LOCAL_MIN_VRAM_GB", "16"))
LLM_DEFAULT_LOCAL = "gemma4:e4b"
LLM_DEFAULT_CLOUD = "gemma4:31b-cloud"
_CAPABLE_HOST_MARKERS = os.environ.get(
    "LACLAUGPT_GPU_HOST_MARKERS", "roihu,gpu,workstation"
).split(",")
_LOCAL_ENDPOINTS = {"", "127.0.0.1", "localhost", "::1"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_MODE_ALIASES = {
    "": "",
    "auto": "auto",
    "local": "local",
    "local-ollama": "local",
    "cloud": "cloud",
    "ollama-cloud": "cloud",
    "external": "external",
}


def normalize_llm_mode(value: str | None) -> str:
    """Normalize documented deployment/provider mode spellings.

    Empty input remains empty so callers can distinguish an unset mode from an
    explicit value. Unknown values fail closed instead of silently becoming a
    routing decision.
    """
    raw = (value or "").strip().casefold()
    try:
        return _MODE_ALIASES[raw]
    except KeyError as exc:
        allowed = ", ".join(sorted(value for value in _MODE_ALIASES if value))
        raise ValueError(f"LLM mode must be one of: {allowed}") from exc


def configured_llm_modes() -> list[tuple[str, str]]:
    """Return all explicitly configured mode variables after normalization."""
    configured: list[tuple[str, str]] = []
    for name in (LLM_MODE_ENV, *LLM_MODE_ENV_ALIASES):
        if name in os.environ and os.environ[name].strip():
            configured.append((name, normalize_llm_mode(os.environ[name])))
    return configured


def resolve_llm_host(explicit: str | None = None) -> str:
    """Resolve the Ollama endpoint using one repository-wide precedence rule.

    Explicit caller arguments take precedence, followed by the native
    ``OLLAMA_HOST`` variable and finally the documented
    ``LACLAUGPT_LLM_ENDPOINT`` setting.
    """
    if explicit is not None and explicit.strip():
        return explicit.strip()
    native = os.environ.get(LLM_HOST_ENV, "").strip()
    if native:
        return native
    return os.environ.get(LLM_ENDPOINT_ENV, "").strip()


def _endpoint_hostname(endpoint: str) -> str:
    if not endpoint:
        return ""
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    return (parsed.hostname or "").casefold()


def _external_endpoint(endpoint: str) -> bool:
    return _endpoint_hostname(endpoint) not in _LOCAL_ENDPOINTS


def _looks_cloud(model: str | None) -> bool:
    return bool(model) and (model.endswith("-cloud") or model.endswith(":cloud"))


def _detected_vram_gb() -> float:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return 0.0
    if result.returncode:
        return 0.0
    sizes = []
    for line in result.stdout.splitlines():
        try:
            sizes.append(float(line.strip()) / 1024)
        except ValueError:
            continue
    return max(sizes, default=0.0)


def _capable_local_machine() -> bool:
    hostname = platform.node().casefold()
    if any(marker in hostname for marker in _CAPABLE_HOST_MARKERS):
        return True
    if os.environ.get("SLURM_JOB_GPUS"):
        return True
    return _detected_vram_gb() >= LLM_LOCAL_MIN_VRAM_GB


def resolve_endpoint(model_hint: str | None = None) -> tuple[str, str]:
    """Resolve ``(mode, model)`` for a call. Never performs network I/O itself.

    ``auto`` probes the endpoint only through :func:`probe_host`, which callers
    may suppress in tests by setting an explicit mode.
    """
    configured_modes = configured_llm_modes()
    mode_env = configured_modes[0][1] if configured_modes else ""
    host = resolve_llm_host()
    if mode_env in ("", "auto"):
        if host and _external_endpoint(host):
            mode = "external"
        elif _capable_local_machine():
            mode = "local"
        else:
            probe = probe_host(host)
            vram = (probe or {}).get("vram_gb", 0) or 0
            mode = "local" if vram >= LLM_LOCAL_MIN_VRAM_GB else "cloud"
    else:
        mode = mode_env
    if mode == "external" and not host:
        raise ValueError("external Ollama mode requires OLLAMA_HOST or LACLAUGPT_LLM_ENDPOINT")
    if model_hint and model_hint.casefold() == "auto":
        model_hint = None
    configured = (
        os.environ.get("LACLAUGPT_LLM_MODEL")
        or os.environ.get("LACLAUGPT_OLLAMA_MODEL")
        or os.environ.get("OLLAMA_MODEL")
    )
    if mode == "cloud":
        model = (
            configured
            or (model_hint if _looks_cloud(model_hint) else None)
            or os.environ.get(LLM_CLOUD_ENV)
            or LLM_DEFAULT_CLOUD
        )
    else:
        model = (
            configured
            or (model_hint if not _looks_cloud(model_hint) else None)
            or os.environ.get(LLM_LOCAL_MODEL_ENV)
            or LLM_DEFAULT_LOCAL
        )
    return mode, model


def describe_routing(model_hint: str | None = None) -> str:
    mode, model = resolve_endpoint(model_hint)
    host = resolve_llm_host() or "default endpoint"
    if mode == "cloud":
        return f"cloud Ollama via {host} (weak-GPU machine) -> {model}"
    if mode == "external":
        return f"external Ollama at {host} -> {model}"
    return f"local Ollama at {host} -> {model}"


def _client(host: str | None = None):
    """Build an Ollama client lazily; requires the optional dependency."""
    try:
        import ollama
    except ImportError as exc:  # pragma: no cover - exercised via guard test
        raise ProviderError(
            "the ollama package is required for the Ollama provider; "
            "install laclaugpt-data-analysis[ollama] or use a mock provider"
        ) from exc
    host = resolve_llm_host(host)
    kwargs: dict[str, Any] = {"host": host} if host else {}
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if api_key and "ollama.com" in host:
        kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
    return ollama.Client(**kwargs)


def probe_host(host: str = "") -> dict[str, Any] | None:
    """Probe a host's reachability and VRAM. Returns None when unreachable."""
    try:
        client = _client(host or None)
        if hasattr(client, "heartbeat"):
            client.heartbeat()
        vram = 0
        try:
            props = client._request("GET", "/api/gpu") if hasattr(client, "_request") else None
            if props and isinstance(props, (list, dict)):
                items = props if isinstance(props, list) else [props]
                for item in items:
                    vram += int(item.get("vram", 0) or 0) / 1024
        except Exception:
            pass
        return {"ok": True, "vram_gb": vram}
    except Exception as exc:
        logger.debug("Ollama probe failed for %s: %s", host or "default", exc)
        return None


def model_digest(model: str) -> str:
    """Model build digest for provenance ('' when unavailable)."""
    try:
        client = _client()
        info = client.show(model)
        digest = getattr(info, "digest", "") or ""
        if not digest and isinstance(info, dict):
            digest = str(info.get("digest", "") or "")
        return str(digest)
    except Exception as exc:
        logger.debug("model digest unavailable for %s: %s", model, exc)
        return ""


def _fallback_allowed(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get(LLM_ALLOW_CLOUD_FALLBACK_ENV, "").strip().casefold() in _TRUE_VALUES


def _retryable_local_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    name = type(exc).__name__.casefold()
    if any(token in name for token in ("connect", "timeout", "network", "transport")):
        return True
    status = getattr(exc, "status_code", None)
    try:
        if status is not None and int(status) >= 500:
            return True
    except (TypeError, ValueError):
        pass
    return False


class OllamaProvider:
    """Local-first Ollama backend implementing LLMProvider."""

    def __init__(self, host: str | None = None, min_vram_gb: float | None = None):
        self._host_override = host
        self._min_vram_gb = min_vram_gb

    def chat(self, request: ChatRequest) -> LLMResponse:
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
        messages = [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ]
        if os.environ.get("OLLAMA_THINK", "").strip().casefold() not in _TRUE_VALUES:
            kwargs["think"] = False
        host = resolve_llm_host(self._host_override)
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
                raise ProviderError(f"Ollama call failed: {exc}") from exc
            cloud_model = os.environ.get(LLM_CLOUD_ENV) or LLM_DEFAULT_CLOUD
            logger.warning(
                "local Ollama failed with retryable error (%s); authorised fallback to %s",
                exc,
                cloud_model,
            )
            response = client.chat(model=cloud_model, messages=messages, options=opts, **kwargs)
            use_model = cloud_model
            actual_mode = "cloud"
            fallback_used = True
            fallback_reason = f"{type(exc).__name__}: {exc}"

        content = response["message"]["content"]
        provenance = LLMCallProvenance(
            requested_mode=mode,
            requested_model=request.model,
            resolved_model=resolved,
            actual_mode=actual_mode,
            actual_model=use_model,
            actual_model_digest=model_digest(use_model),
            endpoint=host or "default endpoint",
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        logger.debug(
            "LLM response requested=%s/%s actual=%s/%s fallback=%s",
            mode,
            resolved,
            actual_mode,
            use_model,
            fallback_used,
        )
        return LLMResponse(content=content, provenance=provenance)
