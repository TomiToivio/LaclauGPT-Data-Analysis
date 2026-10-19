"""Regression tests for prompt/evidence budgeting (issue #372).

Upstream multimodal #241/#262/#285: a prompt that spends its whole budget on input leaves
the model no room to answer, the model-visible size was never logged, and truncation was
a single global flag. AI26's envelope had the same hole from the other direction —
``current_source`` and ``previous_analysis`` are lossless record dumps, so a large record
produced a prompt larger than the context window, which the server then truncated from
the front, i.e. from the system prompt and the task.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from laclaugpt_data_analysis.canonical import CanonicalRecord
from laclaugpt_data_analysis.context_envelope import (
    EMPTY_CONTEXT,
    SECTION_PLAN,
    build_prompt_envelope,
)
from laclaugpt_data_analysis.prompt_budget import (
    MIN_TOTAL_CHARS,
    OMITTED_MARKER,
    TRUNCATION_MARKER,
    BudgetError,
    Section,
    allocate,
    resolve_budget,
)


def _record(text_length: int = 200) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.invalid/issue-372/budget",
        raw_capture={"payload": {"synthetic": True}},
        source={"platform": "synthetic", "created_at": datetime(2026, 10, 19, tzinfo=UTC)},
        content={"text": "word " * max(1, text_length // 5)},
    )


# --------------------------------------------------------------------------------------
# The budget arithmetic
# --------------------------------------------------------------------------------------


def test_a_budget_must_leave_room_for_input_after_the_reserves() -> None:
    with pytest.raises(BudgetError, match="leaves no room"):
        resolve_budget(10_000, reserve_output=8_000, reserve_schema=2_000)
    with pytest.raises(BudgetError, match="at least"):
        resolve_budget(MIN_TOTAL_CHARS - 1)


def test_a_zero_budget_is_the_documented_escape_hatch() -> None:
    assert resolve_budget(0) == (0, 0, 0)


def test_rendered_text_never_exceeds_the_model_visible_budget() -> None:
    sections = [
        Section(f"s{index}", f"[S{index}]", "x" * 50_000, priority=index)
        for index in range(6)
    ]
    packet = allocate(sections, total=12_000, reserve_output=2_000, reserve_schema=500)

    assert packet.used <= 12_000 - 2_000 - 500
    assert packet.budget == 12_000
    assert packet.reserve_output == 2_000


def test_a_truncated_section_says_so_in_band() -> None:
    packet = allocate(
        [Section("evidence", "[EVIDENCE]", "y" * 10_000, priority=10, cap=1_000)],
        total=12_000,
        reserve_output=2_000,
        reserve_schema=500,
    )

    assert "evidence" in packet.truncated_fields
    assert TRUNCATION_MARKER.strip() in packet.text
    report = packet.render_report()
    assert "evidence: " in report and "truncated" in report


def test_a_section_with_no_room_left_is_reported_as_omitted_not_dropped() -> None:
    packet = allocate(
        [
            Section("big", "[BIG]", "z" * 20_000, priority=100),
            Section("small", "[SMALL]", "kept", priority=1),
        ],
        total=10_000,
        reserve_output=2_000,
        reserve_schema=500,
    )

    assert packet.omitted_fields == ("small",)
    assert OMITTED_MARKER in packet.text
    assert "[SMALL]" in packet.text


# --------------------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------------------


def test_every_section_header_survives_a_tiny_budget() -> None:
    envelope = build_prompt_envelope(
        _record(50_000), task="Analyse this item.", budget=6_000
    )
    text = envelope.render()

    for _attribute, header, _priority, _cap in SECTION_PLAN:
        assert f"[{header}]" in text
    assert len(text) <= 6_000


def test_the_task_is_what_survives_when_the_record_does_not_fit() -> None:
    """The instruction the stage exists to give must never be the thing that is lost."""
    task = "TASK-SENTINEL: code this item under the AI26 discourse contract."
    envelope = build_prompt_envelope(_record(400_000), task=task, budget=8_000)
    text, report = envelope.render_with_report()

    assert "TASK-SENTINEL" in text
    assert "current_source" in report["truncated"]
    assert report["budget"] == 8_000
    assert report["used"] <= 8_000


def test_an_ordinary_record_is_not_truncated_at_all() -> None:
    envelope = build_prompt_envelope(_record(500), task="Analyse this item.")
    text, report = envelope.render_with_report()

    assert report["truncated"] == []
    assert report["omitted"] == []
    assert TRUNCATION_MARKER not in text
    assert EMPTY_CONTEXT in text  # the empty layers keep their explicit fallback


def test_the_report_records_the_model_visible_size_per_section() -> None:
    _text, report = build_prompt_envelope(_record(500), task="t").render_with_report()

    names = {entry["name"] for entry in report["sections"]}
    assert names == {name for name, _header, _priority, _cap in SECTION_PLAN}
    assert all("est_tokens" in entry for entry in report["sections"])
    assert report["est_tokens"] >= 1


def test_budgeting_is_deterministic() -> None:
    first = build_prompt_envelope(_record(20_000), task="t", budget=9_000).render()
    second = build_prompt_envelope(_record(20_000), task="t", budget=9_000).render()
    assert first == second


def test_budget_zero_restores_the_unbounded_envelope() -> None:
    envelope = build_prompt_envelope(_record(60_000), task="t", budget=0)
    text = envelope.render()

    assert envelope.budget == 0
    assert TRUNCATION_MARKER not in text
    assert len(text) > 60_000


def test_the_environment_can_lower_the_default_budget(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_PROMPT_BUDGET_CHARS", "7000")
    monkeypatch.setenv("LACLAUGPT_PROMPT_RESERVE_OUTPUT_CHARS", "1000")
    monkeypatch.setenv("LACLAUGPT_PROMPT_RESERVE_SCHEMA_CHARS", "500")
    envelope = build_prompt_envelope(_record(200_000), task="t")

    assert envelope.budget == 7_000
    assert len(envelope.render()) <= 7_000
