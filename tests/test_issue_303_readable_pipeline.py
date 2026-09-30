"""Regression tests for issue #303: the Phase 1 pipeline is readable by construction."""
from __future__ import annotations

import inspect

from laclaugpt_data_analysis.phase1_pipeline import runner
from laclaugpt_data_analysis.phase1_pipeline.frame import plan_modalities, run_frame_analysis
from laclaugpt_data_analysis.phase1_pipeline.laclau import run_laclau_analysis
from laclaugpt_data_analysis.phase1_pipeline.postprocess import run_postprocess
from laclaugpt_data_analysis.phase1_pipeline.preprocess import run_preprocess
from laclaugpt_data_analysis.phase1_pipeline.summary import run_summary


def test_each_scientific_stage_has_an_obvious_public_function() -> None:
    """A researcher can discover all five steps without reading infrastructure code."""
    assert callable(run_preprocess)
    assert callable(plan_modalities)
    assert callable(run_frame_analysis)
    assert callable(run_summary)
    assert callable(run_laclau_analysis)
    assert callable(run_postprocess)


def test_runner_reads_in_the_same_order_as_the_research_pipeline() -> None:
    """Guard the intentionally simple left-to-right execution order."""
    source = inspect.getsource(runner.run_phase1_pipeline)

    positions = [
        source.index("run_preprocess("),
        source.index("run_frame_analysis("),
        source.index("run_summary("),
        source.index("run_laclau_analysis("),
        source.index("run_postprocess("),
    ]
    assert positions == sorted(positions)


def test_runner_explains_multimodal_default_in_source() -> None:
    """Keep the media-present/text-only branch visible instead of hiding it in config."""
    source = inspect.getsource(runner.run_phase1_pipeline)
    assert "Media present => multimodal processing" in source
    assert "Text-only => cleanly skip vision" in source
