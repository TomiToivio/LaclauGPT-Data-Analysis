"""Issue #153: the distributed Redis queue must build its keys from the namespace.

The crash was an ``AttributeError`` on ``namespace.redis_stream(...)`` — helpers
that no class ever defined. It reached production because
``redis_queue_from_settings`` had **no test coverage at all**, so the broken
attribute access never executed in CI. It was also masked behind the stale-manifest
failure: the worker died earlier, at the freeze check, so this second breakage was
invisible.

These tests exercise the function directly and assert the keys match the
documented namespace scheme.
"""
from __future__ import annotations

import pytest

from laclaugpt_data_analysis.distributed import ProjectNamespace
from laclaugpt_data_analysis.task_queue import RedisStreamQueue, redis_queue_from_settings


class _Settings:
    """Minimal stand-in; avoids depending on the full Settings surface."""

    def __init__(self, *, project_id: str = "ai26", redis_url: str = "redis://127.0.0.1:6379/0") -> None:
        self.project_id = project_id
        self.redis_url = redis_url
        self.distributed_namespace = ProjectNamespace(project_id)


def _queue(**kwargs) -> RedisStreamQueue:
    return redis_queue_from_settings(
        _Settings(**kwargs), run_id="ai26-distributed-001", worker_id="worker-1"
    )


def test_queue_construction_does_not_raise(monkeypatch) -> None:
    """The regression guard: constructing the queue must not touch a missing helper.

    Before the fix this raised
    ``AttributeError: 'ProjectNamespace' object has no attribute 'redis_stream'``.
    """
    # RedisStreamQueue.__init__ connects lazily, but guard anyway so the test is
    # about key construction, not about a live server.
    monkeypatch.setattr(RedisStreamQueue, "__init__", lambda self, *a, **k: None)
    try:
        _queue()
    except AttributeError as exc:  # pragma: no cover - only on regression
        pytest.fail(f"redis_queue_from_settings raised AttributeError: {exc}")


def test_stream_key_matches_documented_scheme(monkeypatch) -> None:
    """docs/REDIS_COORDINATION.md: laclaugpt:<project>:stream:analysis:<run_id>:tasks."""
    monkeypatch.setattr(RedisStreamQueue, "__init__", _capture)
    _queue()
    assert _captured["stream"] == "laclaugpt:ai26:stream:analysis:ai26-distributed-001:tasks"


def test_dead_letter_stream_is_namespaced(monkeypatch) -> None:
    monkeypatch.setattr(RedisStreamQueue, "__init__", _capture)
    _queue()
    assert _captured["dead_letter_stream"] == (
        "laclaugpt:ai26:stream:analysis:ai26-distributed-001:dead"
    )


def test_heartbeat_key_uses_the_worker_key_helper(monkeypatch) -> None:
    """docs/REDIS_COORDINATION.md: laclaugpt:<project>:worker:<module>:<worker_id>."""
    monkeypatch.setattr(RedisStreamQueue, "__init__", _capture)
    _queue()
    assert _captured["heartbeat_key"] == "laclaugpt:ai26:worker:analysis:worker-1"


def test_every_key_uses_the_same_namespace_family(monkeypatch) -> None:
    """Issue #153 direction 1: one helper family for every Redis key.

    A mixed family is what allowed the original drift — the stream came from a
    namespaced helper while the group came from a bare string.
    """
    monkeypatch.setattr(RedisStreamQueue, "__init__", _capture)
    _queue()
    namespace = ProjectNamespace("ai26")
    for name in ("stream", "dead_letter_stream", "heartbeat_key"):
        value = _captured[name]
        assert value.startswith(f"{namespace.redis_base}:"), (
            f"{name}={value!r} is outside the project namespace {namespace.redis_base!r}"
        )


def test_consumer_is_the_worker_id(monkeypatch) -> None:
    monkeypatch.setattr(RedisStreamQueue, "__init__", _capture)
    _queue()
    assert _captured["consumer"] == "worker-1"


def test_missing_redis_url_is_rejected(monkeypatch) -> None:
    """A distributed run without a Redis URL must fail loudly, not silently."""
    monkeypatch.setattr(RedisStreamQueue, "__init__", lambda self, *a, **k: None)
    with pytest.raises(ValueError):
        redis_queue_from_settings(
            _Settings(redis_url=""), run_id="run-1", worker_id="worker-1"
        )


_captured: dict[str, str] = {}


def _capture(self, url, *, stream, group, consumer, dead_letter_stream=None, heartbeat_key=None):
    _captured.update(
        {
            "url": url,
            "stream": stream,
            "group": group,
            "consumer": consumer,
            "dead_letter_stream": dead_letter_stream,
            "heartbeat_key": heartbeat_key,
        }
    )
