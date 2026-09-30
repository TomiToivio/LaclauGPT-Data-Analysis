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

Support code around the steps (agent-owned; it never contains the method):

- `pipeline_context.py` - what a step is handed beyond the record
  (`PipelineContext`) and how an attempt is recorded (`StepStatus`, `StepOutcome`).
- `pipeline_runner.py` - sequencing of the seven steps, runnable from the command
  line. Reads the incoming database, writes the outgoing one.
- `pipeline_storage.py` - the concrete local incoming/outgoing databases (SQLite,
  under ignored `data/`), including the rule deciding which records a step is offered.

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

## Running the chain

`pipeline_runner.py` is the only thing that knows the run order, and it contains no
analysis. It can be run directly, in the same style as the rest of this directory:

```bash
# inspect the plan for the pending records; calls no step, writes nothing
python pipeline_runner.py --project ai26 --dry-run

# run the chain
python pipeline_runner.py --project ai26 --limit 100
```

Two decisions the runner makes, both of which are scientific rather than mechanical:

- a text-only record **skips** frame analysis; the skip is recorded as a normal
  result, never as an error, so a text-only study does not look broken;
- a step that **failed** stops that record's chain. DNA and SNA are never built on a
  summary that failed. The results of the steps that did succeed are kept.

While the seven step bodies raise `NotImplementedError`, running the chain stops at
step 1 and says so. That is deliberate: an unfinished step must never look like a
successful one.
## Ownership boundary

<!-- TOMI-LOCKED -->
The seven `step_*.py` modules listed above are the human-written scientific method. Agents work around them, not inside them. Agent-authored changes may add or repair I/O, Pydantic contracts, prompts, RDF/export layers, orchestration, tests, deployment code and adapters, but must not modify, rename, merge, replace or move the seven scientific step files without Tomi explicitly authorizing that specific step change.

This directory intentionally has one canonical seven-step scaffold. Do not create a second parallel step package or alternate pipeline tree.

