"""Phase 0 feed-validation behaviour (issue #171), offline.

These tests stub the network and exercise ``validate_source`` directly. They need
the Phase 0 extras (``feedparser``, ``requests``); the repository venv installs
only the Phase 1 stack, so the module skips cleanly there.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "laclaugpt"))

pytest.importorskip("feedparser", reason="Phase 0 extra not installed")
pytest.importorskip("requests", reason="Phase 0 extra not installed")

from laclaugpt_validate_rss import validate_source  # noqa: E402


class _FakeResponse:
    status_code = 200
    content = b"<rss/>"

    def raise_for_status(self) -> None:
        return None


def _fake_response(*args, **kwargs) -> _FakeResponse:
    return _FakeResponse()



# --------------------------------------------------------------------------

def test_validate_source_flags_a_filter_that_cannot_match(monkeypatch) -> None:
    """A feed can pass every other check yet yield nothing.

    yle_ai declared ``category: [Tekoäly]`` against a general news feed that
    carries no such category. Validation reported PASS while collection would
    have produced an empty corpus, so the filter is now part of validation.
    """
    class _Entry(dict):
        pass

    class _Parsed:
        bozo = False
        entries = [
            {"link": f"https://example.invalid/{index}",
             "title": "General news", "category": "Kotimaa"}
            for index in range(3)
        ]

    monkeypatch.setattr("laclaugpt_validate_rss.requests.get", _fake_response)
    monkeypatch.setattr("laclaugpt_validate_rss.feedparser.parse", lambda _payload: _Parsed())

    source = {
        "id": "synthetic_media",
        "feed_url": "https://example.invalid/feed",
        "filters": {"category": ["Tekoäly"]},
        "active": True,
    }
    ok, errors = validate_source(source, timeout=1)
    assert not ok
    assert any("category filter" in error for error in errors), errors


def test_validate_source_accepts_a_matching_filter(monkeypatch) -> None:
    class _Parsed:
        bozo = False
        entries = [
            {"link": "https://example.invalid/1",
             "title": "AI story", "category": "Tekoäly"},
        ]

    monkeypatch.setattr("laclaugpt_validate_rss.requests.get", _fake_response)
    monkeypatch.setattr("laclaugpt_validate_rss.feedparser.parse", lambda _payload: _Parsed())

    source = {
        "id": "synthetic_media",
        "feed_url": "https://example.invalid/feed",
        "filters": {"category": ["Tekoäly"]},
        "active": True,
    }
    ok, errors = validate_source(source, timeout=1)
    assert ok, errors


class _FakeResponse:
    status_code = 200
    content = b"<rss/>"

    def raise_for_status(self) -> None:
        return None


def _fake_response(*args, **kwargs) -> _FakeResponse:
    return _FakeResponse()
