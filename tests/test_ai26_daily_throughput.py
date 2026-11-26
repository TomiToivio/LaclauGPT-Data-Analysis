"""Daily task counts do not confuse duplicate recognition or cycles with work."""
from datetime import date

from laclaugpt_data_analysis.ai26_daily_throughput import daily_throughput


def test_daily_counts_and_explicit_timezone():
    lines = [
        "[2026-11-25T22:30:00+00:00] AI26 worker cycle: {'completed': 2, 'duplicate': 1}",
        "[2026-11-26T02:30:00] AI26 worker cycle: {'completed': 0, 'duplicate': 3}",
        "[2026-11-26T03:30:00] analysis end worker_status=0",
        "[2026-11-26T04:30:00] AI26 worker cycle: {'completed': 'invalid'}",
    ]
    result = daily_throughput(lines, date(2026, 11, 26), timezone="Europe/Helsinki")
    assert result["completed_tasks"] == 2
    assert result["duplicate_tasks"] == 4
    assert result["worker_summaries"] == 2
    assert result["malformed_summaries"] == 1


def test_no_observations_are_unknown_not_zero():
    result = daily_throughput([], date(2026, 11, 26), timezone="Europe/Helsinki")
    assert result["completed_tasks"] is None
    result = daily_throughput(
        ["2026-11-26T12:30:00 AI26 worker cycle: {'completed': 0}"],
        date(2026, 11, 26), timezone="Europe/Helsinki",
    )
    assert result["completed_tasks"] == 0
