"""Regression checks for issue #454: fallback labels are not formations."""
from datetime import date
from types import SimpleNamespace

from laclaugpt_data_analysis.formation_vocabulary import is_countable_formation
from laclaugpt_data_analysis.periodic_summary import SummaryScope, record_matches_scope
from laclaugpt_data_analysis.reporting import build_daily_report
from laclaugpt_data_analysis.prompt_library import load_prompt
from laclaugpt_data_analysis.stages.prompt_map import prompt_ids_for_stage


def formation(label, **metadata):
    return SimpleNamespace(label=label, metadata=metadata)


def test_fallbacks_are_excluded_but_historical_valid_labels_remain():
    assert not is_countable_formation(formation("unknown", formation_label_resolved=False))
    assert not is_countable_formation(formation("other", formation_label_resolved=True))
    assert not is_countable_formation(formation("critical_ai", formation_label_resolved=False))
    assert is_countable_formation(formation("critical_ai", formation_label_resolved=True))
    assert is_countable_formation(formation("historical_free_text"))


def test_report_and_scope_ignore_unresolved_fallbacks():
    record = SimpleNamespace(
        source=SimpleNamespace(
            created_at=None, collected_at=None, author="test", author_fullname="",
            platform="rss", country="FI",
        ),
        analysis=SimpleNamespace(
            entities=[], signifiers=[],
            formations=[formation("unknown", formation_label_resolved=False),
                        formation("critical_ai", formation_label_resolved=True)],
        ),
        human_readable=SimpleNamespace(summary="synthetic test"),
        source_url="https://example.org/synthetic",
    )
    report = build_daily_report([record], report_date=date(2026, 11, 22))
    assert report.top_formations == ["critical_ai"]
    assert "unknown" not in report.markdown
    assert not record_matches_scope(record, SummaryScope(dimension="formation", value="unknown"))
    assert record_matches_scope(record, SummaryScope(dimension="formation", value="critical_ai"))


def test_ai26_prompt_has_distinct_version_and_legacy_v1_is_preserved():
    prompt_id = prompt_ids_for_stage("ai26", "discourse")[1]
    original = load_prompt(prompt_id, version="v1")
    current = load_prompt(prompt_id, version="v3")
    assert "AI26 formation-candidate output contract" not in original.text
    assert "AI26 formation-candidate output contract" in current.text
    assert original.sha256 != current.sha256
