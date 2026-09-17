"""First-class debug/verbose mode for manual bring-up on a new machine.

Enabled through configuration/environment only — never by editing code:

    LACLAUGPT_DEBUG=1          verbose operational diagnostics
    LACLAUGPT_TRACE=1          additionally allow full prompt/evidence bodies

Debug mode increases *operational* detail (profile composition, connectivity,
stage transitions, prompt identity, staging status, timings, persistence). It
must never weaken the privacy boundary:

- credentials, tokens and authenticated URLs are redacted by pattern before
  they can reach a log record;
- full prompt/evidence bodies are withheld even in debug mode unless trace mode
  is explicitly opted into, because they may contain research data.

The redaction helpers are deliberately conservative: an unknown string that
looks like a credential is redacted rather than logged.
"""
from __future__ import annotations

import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_DEBUG_ENV = "LACLAUGPT_DEBUG"
_TRACE_ENV = "LACLAUGPT_TRACE"

_TRUTHY = {"1", "true", "yes", "on"}

# Patterns that must never appear in a log record. Ordered most-specific first.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # scheme://user:password@host  -> keep scheme+host, drop credentials
    (re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@", re.I),
     r"\g<scheme><redacted>@"),
    # s3/bucket access keys and common token shapes
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-aws-key>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"), "<redacted-api-key>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "<redacted-token>"),
    # bearer headers must be matched BEFORE the generic key=value rule, which
    # would otherwise consume only the "Authorization:" label and leave the
    # token itself in the record.
    (re.compile(r"(?i)\b(Authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._\-]{8,}"),
     r"\1<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer <redacted>"),
    # key=value / key: value for credential-ish keys. The optional namespace
    # prefix (LACLAUGPT_S3_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, ...) is matched
    # so an environment dump cannot smuggle a secret through unredacted.
    (re.compile(
        r"(?i)\b([A-Za-z0-9_]*"
        r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key"
        r"|secret[_-]?access[_-]?key|authorization|auth[_-]?token|private[_-]?key))"
        r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
    ), r"\1\2<redacted>"),
    # long opaque hex/base64 blobs that are very likely secrets
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "<redacted-hex>"),
)


def redact(text: Any) -> str:
    """Return ``text`` with credential-shaped substrings replaced.

    Used for every diagnostic that may embed a runtime value. Non-string input
    is stringified first so a caller cannot accidentally bypass redaction by
    passing a dict.
    """
    rendered = text if isinstance(text, str) else str(text)
    for pattern, replacement in _REDACTION_PATTERNS:
        rendered = pattern.sub(replacement, rendered)
    return rendered


def sanitize_url(url: str) -> str:
    """Reduce a URL to scheme+host+path, dropping userinfo and query secrets."""
    if not url:
        return ""
    without_userinfo = re.sub(
        r"^([a-z][a-z0-9+.\-]*://)[^/\s:@]+:[^/\s@]+@", r"\g<1>", url, flags=re.I
    )
    return re.sub(r"[?&]([^=&\s]*(key|token|secret|password|sig)[^=&\s]*)=[^&\s]*",
                  r"\1=<redacted>", without_userinfo, flags=re.I)


def debug_enabled() -> bool:
    return os.environ.get(_DEBUG_ENV, "").strip().casefold() in _TRUTHY


def trace_enabled() -> bool:
    """Trace mode requires an explicit opt-in and implies debug mode."""
    return os.environ.get(_TRACE_ENV, "").strip().casefold() in _TRUTHY


def bodies_allowed() -> bool:
    """Full prompt/evidence bodies are only ever emitted in trace mode."""
    return trace_enabled()


def configure_logging(*, force: bool = False) -> int:
    """Install a stderr handler sized for the current mode. Returns the level."""
    level = logging.DEBUG if debug_enabled() else logging.INFO
    root = logging.getLogger("laclaugpt_data_analysis")
    if force or not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        root.addHandler(handler)
    root.setLevel(level)
    return level


class DebugReport:
    """Accumulates structured diagnostic events for one run.

    Events are (event, payload) pairs kept in memory for a bounded summary at
    the end of a run. Payloads are sanitized on the way in, so a leaked
    credential cannot survive in ``events``.
    """

    def __init__(self, *, enabled: bool | None = None, max_events: int = 500) -> None:
        self.enabled = debug_enabled() if enabled is None else enabled
        self.max_events = max_events
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.started = time.monotonic()

    def emit(self, event: str, **payload: Any) -> None:
        """Record one diagnostic event (no-op when debug mode is off)."""
        if not self.enabled:
            return
        if len(self.events) < self.max_events:
            self.events.append((event, _sanitize_payload(payload)))
        logger.debug("%s %s", event, _sanitize_payload(payload))

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started

    def summary(self) -> dict[str, Any]:
        """Bounded run summary suitable for the final log line."""
        return {
            "debug": self.enabled,
            "trace": trace_enabled(),
            "event_count": len(self.events),
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
            "events": [name for name, _ in self.events],
        }

    @contextmanager
    def stage(self, name: str, **payload: Any) -> Iterator[None]:
        """Time one pipeline stage and emit its duration and failure class."""
        self.emit(f"{name}.start", **payload)
        started = time.monotonic()
        try:
            yield
        except Exception as exc:  # noqa: BLE001 - diagnostics must not alter control flow
            self.emit(
                f"{name}.error",
                failure_class=type(exc).__name__,
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            raise
        self.emit(
            f"{name}.end",
            elapsed_seconds=round(time.monotonic() - started, 3),
        )


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact every value; drop bodies unless trace mode is explicitly on."""
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.casefold()
        if lowered in {"prompt", "evidence", "text", "body", "source_text", "context"}:
            if not bodies_allowed():
                clean[key] = f"<withheld: {len(str(value))} chars; set LACLAUGPT_TRACE=1>"
                continue
        if lowered in {"url", "uri", "endpoint", "object_ref"} and isinstance(value, str):
            clean[key] = sanitize_url(value)
            continue
        if lowered in {"token", "password", "secret", "api_key", "access_key"}:
            clean[key] = "<redacted>"
            continue
        clean[key] = redact(value)
    return clean


def describe_environment() -> dict[str, Any]:
    """Credential-free description of the composed runtime environment."""
    from .config import load_settings

    try:
        settings = load_settings()
    except Exception as exc:  # noqa: BLE001 - report, do not crash diagnostics
        return {"settings_error": type(exc).__name__}
    return {
        "project_id": settings.project_id,
        "machine": settings.machine,
        "execution": settings.execution,
        "storage": settings.storage,
        "storage_backend": settings.storage_backend,
        "llm_mode": settings.llm_mode,
        "llm_model": settings.llm_model,
        "llm_endpoint": sanitize_url(settings.llm_endpoint),
        "object_backend": settings.object_backend,
        "cache_backend": settings.cache_backend,
        "data_dir": str(settings.data_dir),
        "mongodb_configured": bool(settings.mongo_url),
        "redis_configured": bool(settings.redis_url),
        "s3_bucket": settings.s3_bucket or "",
    }
