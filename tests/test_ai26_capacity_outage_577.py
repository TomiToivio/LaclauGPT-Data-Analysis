"""A capacity outage must be nameable from the journal, not inferred from a zero (#577).

The journal is the only structured record of what the worker did, so these tests build journals rather than
trusting a live host: every behaviour asserted here is something the report must get right when the same 18
hour park happens again.

The cases that matter:

* a zero completed-task count is not an outage until the journal says so;
* an outage has a start, a duration and a reason distribution;
* a lock (`already_running`) inside an outage does not itself make it a capacity claim;
* a success ends the outage, so a park that recovered is reported as ended, not ongoing;
* nothing sampled means unknown -- never a measured zero.
"""

from __future__ import annotations

import json
import pathlib

from laclaugpt_data_analysis.ai26_capacity_outage import main, summarise


def event(stamp: str, outcome: str, *, exit_code: int = 0) -> str:
    return json.dumps(
        {"timestamp_utc": stamp, "outcome": outcome, "exit_code": exit_code, "stage": "worker"}
    )


JOURNAL = [
    event("2026-11-25T18:38:40+00:00", "cycle_completed"),
    event("2026-11-25T19:40:00+00:00", "cycle_completed"),
    event("2026-11-25T20:48:45+00:00", "provider_unavailable", exit_code=75),
    event("2026-11-25T21:45:12+00:00", "provider_unavailable", exit_code=75),
    event("2026-11-25T22:11:19+00:00", "already_running", exit_code=3),
    event("2026-11-25T23:41:11+00:00", "provider_unavailable", exit_code=75),
]


class TestOutageShape:
    def test_an_ongoing_capacity_outage_has_a_start_duration_and_reasons(self):
        report = summarise(JOURNAL)
        assert report.events == 6
        assert report.completed_cycles == 2
        assert report.capacity_cycles == 3
        assert report.ongoing
        assert report.last_success_utc == "2026-11-25T19:40:00+00:00"
        interval = report.intervals[-1]
        assert interval.started_utc == "2026-11-25T20:48:45+00:00"
        assert interval.ended_utc == "2026-11-25T23:41:11+00:00"
        assert interval.reasons == {"provider_unavailable": 3, "already_running": 1}
        assert interval.duration_hours == 2.87

    def test_a_success_ends_the_outage_and_the_report_says_ended(self):
        report = summarise([*JOURNAL, event("2026-11-26T00:40:00+00:00", "cycle_completed")])
        assert not report.ongoing
        assert "capacity outage ended" in report.sentence()
        assert report.intervals[-1].capacity_parks == 3

    def test_a_lock_alone_is_not_a_capacity_outage(self):
        report = summarise(
            [
                event("2026-11-25T20:00:00+00:00", "already_running", exit_code=3),
                event("2026-11-25T21:00:00+00:00", "already_running", exit_code=3),
            ]
        )
        assert report.cycles == {"already_running": 2}
        assert not report.ongoing
        assert "no capacity outage" in report.sentence()

    def test_a_manual_preflight_neither_extends_nor_ends_an_outage(self):
        report = summarise(
            [
                event("2026-11-25T20:00:00+00:00", "provider_unavailable", exit_code=75),
                event("2026-11-25T20:30:00+00:00", "check_ok"),
                event("2026-11-25T21:00:00+00:00", "provider_unavailable", exit_code=75),
            ]
        )
        assert report.ongoing
        assert report.intervals[-1].cycles == 2
        assert "check_ok" not in report.cycles

    def test_two_outages_separated_by_work_are_two_intervals(self):
        report = summarise(
            [
                event("2026-11-25T10:00:00+00:00", "provider_unavailable", exit_code=75),
                event("2026-11-25T11:00:00+00:00", "cycle_completed"),
                event("2026-11-25T12:00:00+00:00", "provider_unavailable", exit_code=75),
            ]
        )
        capacity = [interval for interval in report.intervals if interval.is_capacity]
        assert len(capacity) == 2
        assert report.intervals[-1].started_utc == "2026-11-25T12:00:00+00:00"

    def test_a_provider_outage_mixed_with_pipeline_failures_names_both(self):
        report = summarise(
            [
                event("2026-11-25T10:00:00+00:00", "provider_unavailable", exit_code=75),
                event("2026-11-25T11:00:00+00:00", "cycle_failed", exit_code=1),
            ]
        )
        assert report.intervals[-1].reasons == {"provider_unavailable": 1, "cycle_failed": 1}
        assert report.ongoing


class TestHonestEmpties:
    def test_no_events_is_unknown_not_zero(self):
        report = summarise([])
        assert report.events == 0
        assert "unknown, not zero" in report.sentence()
        assert report.as_dict()["coverage"].startswith("no journal events")

    def test_malformed_lines_are_counted_not_silently_dropped(self):
        report = summarise(["not json", json.dumps({"outcome": "provider_unavailable"}), *JOURNAL])
        assert report.malformed == 2
        assert report.events == 6

    def test_an_unknown_outcome_is_counted_but_not_used_as_a_reason(self):
        report = summarise([event("2026-11-25T10:00:00+00:00", "something_new")])
        assert report.cycles == {"something_new": 1}
        assert report.intervals == []


class TestWrapperReporting:
    """The cycle must name its own outage, or the log stays eighteen identical failures (#577)."""

    def test_the_wrapper_reports_the_outage_after_appending_the_tick(self):
        script = (
            pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_ai26_laskin.sh"
        ).read_text()
        assert "ai26_capacity_outage" in script
        block = script.split("# #577: name a provider-capacity outage")[1].split("fi", 2)[0]
        assert "--journal" in block
        # A reporting failure must never fail the cycle: the report is evidence, not a gate.
        assert "|| true" in block
        # It runs inside the EXIT trap's telemetry block, i.e. after the cycle's status is settled.
        assert block in script.split("record_tick_on_exit() {", 1)[1]


class TestExitStatus:
    def test_an_ongoing_outage_exits_three(self, tmp_path):
        journal = tmp_path / "journal.jsonl"
        journal.write_text("\n".join(JOURNAL) + "\n", encoding="utf-8")
        assert main(["--journal", str(journal)]) == 3

    def test_a_recovered_journal_exits_zero(self, tmp_path):
        journal = tmp_path / "journal.jsonl"
        journal.write_text(
            "\n".join([*JOURNAL, event("2026-11-26T00:00:00+00:00", "cycle_completed")]) + "\n",
            encoding="utf-8",
        )
        assert main(["--journal", str(journal)]) == 0

    def test_a_missing_journal_exits_two(self, tmp_path):
        assert main(["--journal", str(tmp_path / "absent.jsonl")]) == 2

    def test_the_json_report_carries_the_intervals(self, tmp_path, capsys):
        journal = tmp_path / "journal.jsonl"
        journal.write_text("\n".join(JOURNAL) + "\n", encoding="utf-8")
        main(["--journal", str(journal), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["outage_ongoing"] is True
        assert payload["intervals"][-1]["capacity_outage"] is True
