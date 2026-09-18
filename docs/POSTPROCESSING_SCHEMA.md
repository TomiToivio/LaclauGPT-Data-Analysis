# Postprocessing stage and its derived schema

Postprocessing is the final stage of the Phase 1 pipeline. It derives **compact,
typed, auditable structured fields** from the summary and Laclaudian discourse
outputs. It does not re-analyse the source and does not replace the richer
summary or discourse analysis.

## Role

The legacy `puhti_postprocess.py` produced machine-readable fields for
downstream use. The modern stage keeps that role but writes into the canonical
`record.analysis` section using schema-backed models rather than free-form
parsing.

## Ordering

Postprocessing runs **after** discourse analysis, because it projects the
discourse proposal into canonical fields:

```text
preprocess -> frame (conditional) -> summary -> discourse -> postprocess
```

## Derived fields

The stage populates the canonical analysis section (`postprocess_record`):

| Field | Derived from | Notes |
| --- | --- | --- |
| `analysis.summary` | summary | readable synthesis |
| `analysis.entities` | summary | only when `entities` capability enabled |
| `analysis.topics` | summary | only when `topics` capability enabled |
| `analysis.sentiments` | summary | **sentiment observations, never affective investment** |
| `analysis.signifiers` | discourse | floating + empty candidate objects |
| `analysis.floating_signifiers` | discourse | `corpus_validation_required=True` |
| `analysis.empty_signifier_candidates` | discourse | requires chain/fullness evidence |
| `analysis.nodal_points` | discourse | requires organising-relation evidence |
| `analysis.formations` | discourse | provisional, comparative candidates |
| `analysis.imaginaries` | discourse | only when `sociotechnical_imaginaries` enabled |
| `analysis.us` | discourse | collective subjects |
| `analysis.frontier` | discourse | antagonistic frontier |
| `analysis.affects` | discourse | affects with targets |
| `analysis.formula_of_populism` | discourse | Palonen formula; evidenced only |
| `analysis.equivalence_chains` | discourse | links + shared obstacle |
| `analysis.difference_chains` | discourse | maintained distinctions |
| `analysis.antagonisms` | discourse | blocking force + blocked project |
| `analysis.relations` | discourse | all articulated relations |
| `analysis.uncertainty` | summary + discourse | de-duplicated |
| `analysis.abstentions` | discourse | explicit non-findings |

Every projected object carries `review_status="PROVISIONAL"` and, where
applicable, `metadata["corpus_validation_required"]=True`. Evidence links use
the verified `evidence_ids` produced by the discourse stage.

## Relationship to summary and discourse outputs

- The **summary** and **discourse** stage outputs remain in
  `record.intermediate.stage_outputs` as the richer, auditable record.
- Postprocessing produces the **canonical projection** consumed by export,
  comparison and visualization.
- Postprocessing must not invent a value that upstream did not support; an
  absent value is recorded as absent/abstained.

## Structured-output normalizer

For projects that enable a postprocessing LLM normalizer (e.g. the AI26
profile), the prompt is `ai26.postprocess:v1`, which is constrained to derive
fields only from upstream outputs and to prefer typed, validated structures over
free-form parsing.
