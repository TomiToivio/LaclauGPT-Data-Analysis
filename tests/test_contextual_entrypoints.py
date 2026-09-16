"""Smoke tests for the production unified-context entry points."""


def test_contextual_pipeline_imports_and_exposes_runner():
    from laclaugpt_data_analysis.contextual_pipeline import run_contextual_canonical_pipeline

    assert callable(run_contextual_canonical_pipeline)


def test_contextual_cli_entrypoints_import():
    from laclaugpt_data_analysis.contextual_entrypoints import reprocessing_main, worker_main

    assert callable(reprocessing_main)
    assert callable(worker_main)
