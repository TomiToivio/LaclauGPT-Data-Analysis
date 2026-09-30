# Human-readable Phase 2 analysis pipeline

This is the framework requested in issue #315. It deliberately keeps the scientific
steps small and visible so Tomi can hand-write their analysis logic.

The seven steps are:

1. `step_01_preprocess.py` - normalize every incoming record.
2. `step_02_frame.py` - analyze attached images/video frames when present.
3. `step_03_summary.py` - make one multimodal-aware summary for every record.
4. `step_04_postprocess.py` - extract descriptive entities/topics/affects.
5. `step_05_laclau.py` - Laclaudian discourse analysis.
6. `step_06_dna.py` - Discourse Network Analysis projection.
7. `step_07_sna.py` - Social Network Analysis projection.

Auxiliary files are intentionally separate from those seven scientific steps:

- `pipeline_models.py` - small Pydantic contracts shared by the steps.
- `pipeline_io.py` - incoming/outgoing database boundary.
- `pipeline_prompts.py` - project prompt loading without embedding project-specific
  operational data in code.
- `pipeline_rdf.py` - transparent RDF projection helpers.

## Design rules

- Keep each scientific step readable in one sitting.
- Keep source identity (`source_url`) unchanged end-to-end.
- Preserve text-only records. Step 2 is conditional, not mandatory.
- Step 3 runs for both text-only and multimodal records.
- Descriptive outputs and theory-facing interpretations remain separate.
- DNA and SNA consume prior analysis; they do not silently rewrite it.
- Operational/private material belongs under ignored `data/` or private repositories.
- The existing `src/laclaugpt_data_analysis/` package remains available as infrastructure
  and reference code. This scaffold does not delete or rewrite it.
- Legacy `puhti_*.py` files are references for human reimplementation, not code to copy
  wholesale.

## Legacy reference mapping

- preprocess -> `LaclauGPT-Multimodal-Analysis/puhti_preprocess.py`
- frame -> `puhti_frame.py`
- summary -> `puhti_summary.py`
- postprocess -> `puhti_postprocess.py`
- Laclau -> `puhti_populism.py`

Phase 2 adds DNA and SNA after the Laclaudian layer.

## Expected orchestration

```text
incoming CanonicalRecord
        |
        v
01 preprocess
        |
        +---- media? ----> 02 frame
        |                    |
        +--------------------+
        |
        v
03 summary
        |
        v
04 postprocess
        |
        v
05 Laclau
        |
        v
06 DNA
        |
        v
07 SNA
        |
        +--> outgoing database / RDF / visualization adapters
```

The functions currently expose the intended inputs and outputs and raise
`NotImplementedError` where Tomi's hand-written method belongs.
