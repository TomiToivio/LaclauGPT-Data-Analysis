from laclaugpt_data_analysis.hungary26_media import MediaProfile, plan_segments, segment_manifest
from laclaugpt_data_analysis.hungary26_quality import aggregate_comparison, compare_pair


def test_short_video_stays_whole() -> None:
    plans = plan_segments("m1", 75.0)
    assert len(plans) == 1
    assert plans[0].whole_video is True
    assert plans[0].start_seconds == 0.0
    assert plans[0].end_seconds == 75.0


def test_long_video_segments_preserve_parent_and_bounds() -> None:
    profile = MediaProfile(whole_video_max_seconds=60, min_segment_seconds=20, max_segment_seconds=120, overlap_seconds=5)
    plans = plan_segments("m2", 310.0, profile)
    assert len(plans) >= 3
    assert all(plan.parent_media_id == "m2" for plan in plans)
    assert plans[0].start_seconds == 0.0
    assert plans[-1].end_seconds == 310.0


def test_segment_manifest_never_silently_drops_invalid_media() -> None:
    manifest = segment_manifest("m3", 0.0, "abc")
    assert manifest["status"] == "failed"
    assert manifest["guardrails"]["silent_drop_forbidden"] is True


def test_comparison_requires_human_review() -> None:
    old = {"source_url": "x:1", "analysis": {"entities": [], "uncertainty": []}, "evidence": []}
    new = {"source_url": "x:1", "analysis": {"entities": [{"label": "X"}], "uncertainty": ["ambiguous"]}, "evidence": [{"id": 1}], "provenance": [{"id": 1}]}
    pair = compare_pair(old, new)
    assert pair["human_review_required"] is True
    assert "Do not infer quality from output length" in pair["guardrail"]
    summary = aggregate_comparison([pair])
    assert summary["records"] == 1
    assert summary["human_review_required"] is True
