"""External research-tool interoperability adapters.

The package exposes the stable DATS/DNA exchange contracts while retaining the richer
native DNA adapters under :mod:`laclaugpt_data_analysis.interoperability.dna`.
"""
from .contracts import (
    INTEROP_SCHEMA_VERSION,
    Annotation,
    Code,
    DatsProject,
    DiscourseStatement,
    ExternalRef,
    GraphProjection,
    HumanReview,
    Producer,
    ResearchNote,
    TemporalPoint,
    TemporalSeries,
    attach_external_result,
    dna_csv_dumps,
    dna_csv_loads,
    export_dats_project,
    export_dna_rows,
    import_dats_project,
    import_dna_rows,
)

__all__ = [
    "INTEROP_SCHEMA_VERSION",
    "Annotation",
    "Code",
    "DatsProject",
    "DiscourseStatement",
    "ExternalRef",
    "GraphProjection",
    "HumanReview",
    "Producer",
    "ResearchNote",
    "TemporalPoint",
    "TemporalSeries",
    "attach_external_result",
    "dna_csv_dumps",
    "dna_csv_loads",
    "export_dats_project",
    "export_dna_rows",
    "import_dats_project",
    "import_dna_rows",
]
