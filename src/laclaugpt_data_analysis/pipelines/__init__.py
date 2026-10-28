"""Selectable analysis pipelines (#399).

Importing a pipeline implementation is not the same as selecting it: the registry decides which one
runs, and `get_pipeline` refuses to guess.
"""
from .registry import (
    PIPELINES,
    PipelineSpec,
    UnknownPipeline,
    get_pipeline,
    list_pipelines,
    pipeline_keys,
    validate_pipeline_id,
)

__all__ = [
    "PIPELINES",
    "PipelineSpec",
    "UnknownPipeline",
    "get_pipeline",
    "list_pipelines",
    "pipeline_keys",
    "validate_pipeline_id",
]
