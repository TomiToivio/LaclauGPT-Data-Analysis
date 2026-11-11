"""#429: the seeding order must be measurable, or the starvation is invisible by construction.

Every individual cycle looks healthy — it examines a few thousand records and publishes its ten.
The property that is broken only exists across cycles, so it needs a measurement, not a log line.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import ai26_ready_frame_audit as audit_tool  # noqa: E402


def record(url: str, platform: str, priority: int, published: str) -> dict:
    return {
        "source_url": url,
        "source": {"platform": platform},
        "handoff": {"source_priority": priority, "published_at": published},
    }


def frame():
    """A miniature of the real frame: a P1 tier big enough to consume the whole cycle."""
    rows = [
        record(f"https://rss.example/{i}", "rss", 1, f"2026-11-{i:02d}T10:00:00Z")
        for i in range(1, 11)
    ]
    rows += [
        record("https://bsky.example/old-1", "bluesky", 2, "2026-10-01T10:00:00Z"),
        record("https://bsky.example/old-2", "bluesky", 2, "2026-10-02T10:00:00Z"),
        record("https://mastodon.example/old", "mastodon", 2, "2026-09-20T10:00:00Z"),
        record("https://x.example/one", "x", 3, "2026-10-05T10:00:00Z"),
    ]
    return rows


def test_the_order_is_the_worker_s_order_not_the_input_order():
    ordered = audit_tool.seeding_order(list(reversed(frame())))
    priorities = [row["handoff"]["source_priority"] for row in ordered]
    assert priorities == sorted(priorities), "the audit must walk priority first"
    # Inside a tier the worker walks newest-first, which is what buries October.
    rss = [row["source_url"] for row in ordered if row["source"]["platform"] == "rss"]
    assert rss[0].endswith("/10") and rss[-1].endswith("/1")


def test_a_starved_tail_is_visible_as_a_position_beyond_the_cycle_capacity():
    rows = frame()
    report = audit_tool.audit(rows, analysed_urls=[row["source_url"] for row in rows
                                                   if row["source"]["platform"] == "rss"])
    bluesky = report["platforms"]["bluesky"]
    assert bluesky["ready"] == 2
    assert bluesky["analysed"] == 0
    assert bluesky["share"] == 0.0
    # Ten RSS records sort ahead of it: a cycle of ten publications never reaches it.
    assert bluesky["first_never_analysed_position"] == 11
    assert report["first_never_analysed"]["bluesky"] == 11


def test_per_platform_shares_are_computed_independently():
    rows = frame()
    analysed = {row["source_url"] for row in rows if row["source"]["platform"] == "rss"}
    analysed.add("https://bsky.example/old-1")
    report = audit_tool.audit(rows, analysed)
    assert report["platforms"]["rss"]["share"] == 1.0
    assert report["platforms"]["bluesky"]["share"] == 0.5
    assert report["platforms"]["bluesky"]["never_analysed"] == 1


def test_the_backlog_is_attributed_to_publication_months():
    rows = frame()
    report = audit_tool.audit(rows, [])
    months = report["platforms"]["bluesky"]["never_analysed_by_month"]
    assert months == {"2026-10": 2}
    assert report["platforms"]["mastodon"]["never_analysed_by_month"] == {"2026-09": 1}


def test_a_closed_stratum_is_reported_but_never_raises_the_alarm():
    rows = frame()
    report = audit_tool.audit(rows, [row["source_url"] for row in rows
                                     if row["source"]["platform"] == "rss"])
    assert report["platforms"]["x"]["closed_stratum"] is True
    problems = audit_tool.verdict(report, fail_under=0.8)
    assert not any(problem.startswith("x:") for problem in problems), (
        "#401 closed X deliberately; a closed stratum must not look like a regression"
    )
    assert any(problem.startswith("bluesky:") for problem in problems)


def test_the_verdict_names_the_position_that_explains_the_starvation():
    rows = frame()
    report = audit_tool.audit(rows, [row["source_url"] for row in rows
                                     if row["source"]["platform"] == "rss"])
    problems = audit_tool.verdict(report, fail_under=0.8)
    assert "first unanalysed at position 11" in problems[0]


def test_datetime_objects_are_ordered_like_the_store_s_bson_dates():
    """The store returns BSON dates, not strings; both must produce the same order."""
    rows = frame()
    for row in rows:
        row["handoff"]["published_at"] = datetime.fromisoformat(
            row["handoff"]["published_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    ordered = audit_tool.seeding_order(rows)
    rss = [row["source_url"] for row in ordered if row["source"]["platform"] == "rss"]
    assert rss[0].endswith("/10") and rss[-1].endswith("/1")


def test_an_empty_frame_measures_zero_rather_than_dividing_by_zero():
    report = audit_tool.audit([], [])
    assert report["ready"] == 0 and report["never_analysed"] == 0
    assert report["platforms"] == {}
    assert audit_tool.verdict(report) == []


def test_the_report_renders_the_table_and_the_month_breakdown():
    rows = frame()
    text = audit_tool.render(audit_tool.audit(rows, []))
    assert "| platform | ready | analysed | share | first never-analysed |" in text
    assert "bluesky 2026-10: 2" in text
    assert "(closed stratum)" in text


def test_missing_store_configuration_is_an_error_not_an_empty_report(monkeypatch, capsys):
    monkeypatch.delenv("LACLAUGPT_MONGODB_URI", raising=False)
    assert audit_tool.main([]) == 2
    assert "missing store configuration" in capsys.readouterr().err
