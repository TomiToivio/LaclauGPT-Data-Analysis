import sys

import pytest

import laclaugpt_collect_rss


def test_collector_cli_exits_zero_when_all_sources_succeed(monkeypatch, capsys):
    monkeypatch.setattr(
        laclaugpt_collect_rss,
        "active_sources",
        lambda: [{"id": "one"}, {"id": "two"}],
    )
    monkeypatch.setattr(laclaugpt_collect_rss, "collect_source", lambda *args, **kwargs: 2)
    monkeypatch.setattr(sys, "argv", ["laclaugpt_collect_rss.py"])

    laclaugpt_collect_rss.main()

    output = capsys.readouterr().out
    assert "one: 2 entries upserted" in output
    assert "two: 2 entries upserted" in output
    assert "Total: 4 entries upserted" in output


def test_collector_cli_exits_nonzero_if_any_source_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        laclaugpt_collect_rss,
        "active_sources",
        lambda: [{"id": "good"}, {"id": "bad"}],
    )

    def fake_collect(source, **kwargs):
        if source["id"] == "bad":
            raise RuntimeError("feed unavailable")
        return 1

    monkeypatch.setattr(laclaugpt_collect_rss, "collect_source", fake_collect)
    monkeypatch.setattr(sys, "argv", ["laclaugpt_collect_rss.py"])

    with pytest.raises(SystemExit) as caught:
        laclaugpt_collect_rss.main()

    assert caught.value.code == 1
    output = capsys.readouterr().out
    assert "good: 1 entries upserted" in output
    assert "bad: ERROR feed unavailable" in output
    assert "Total: 1 entries upserted" in output
