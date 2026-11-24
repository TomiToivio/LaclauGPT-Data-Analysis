# Consuming the shared label-merge registry (#311)

The corpus has one durable, versioned record of what a label is called: the merge registry produced by the
curation tooling (`dashboards/ep24_merge_lab` in `LaclauGPT-Data-Visualization`, with the review evidence kept
in `LaclauGPT-Private`). This repository consumes it; it does not own it and must not fork it.

## The contract

`src/laclaugpt_data_analysis/merge_registry.py` reads the registry's JSONL schema — one decision per line:

| Field | Meaning |
| --- | --- |
| `category` | `entity`, `person`, `theme`, `topic` or `sentiment` |
| `alias` | the label as it appears in the data |
| `canonical` | what it is called after the decision |
| `status` | `approved`, `keep_separate`, `proposed`, `rejected`, `superseded` |
| `canonical_id`, `wiki_url`, `wikidata_qid`, `fallback_reason` | the identity and its evidence |
| `polarity` | required for sentiment decisions |
| `scope` | `{country, language, source}` restrictions; empty means everywhere in the category |
| `reviewers`, `evidence` | who decided and on what |
| `revision`, `supersedes` | history; a correction is a new line, never an edit |

`src/laclaugpt_data_analysis/stages/merge_registry_stage.py` applies it to a record after the analysis has
written its labels: entities (as `person` when `entity_type` says so, otherwise `entity`), topics, themes and
sentiments.

## Rules the consumer enforces

- **Only settled decisions rewrite output.** `approved` and `keep_separate` apply; `proposed`, `rejected` and
  `superseded` never do. A proposal is evidence for the review queue, not a canonicalisation.
- **The most specific scope wins**, and a scoped decision does not leak into another country, language or
  source. Equally specific decisions that disagree resolve to `review` and leave the label alone — the
  resolver does not pick a winner the evidence does not pick.
- **A configured registry that cannot be trusted is an error.** Missing file, unparsable line, unknown
  category or status, `approved` without three reviewers or without evidence, sentiment without polarity, or
  a checksum that does not match the pinned value all raise `RegistryUnavailable`. There is no fallback to
  raw labels that still claims canonicalisation.
- **The raw label survives.** Entities keep the original in `aliases`; topics, themes and sentiments keep it
  in `metadata.raw_label`. A wrong merge stays reversible, and a later registry revision can be applied to
  the same record.
- **The version is recorded.** A record that had at least one label rewritten carries
  `analysis.plugin_results.merge_registry = {registry_sha256, source, entries, labels_canonicalised}` so an
  export can name exactly which registry it was canonicalised against.

## Pinning

```bash
export LACLAUGPT_MERGE_REGISTRY=/path/to/merge_registry.jsonl
export LACLAUGPT_MERGE_REGISTRY_SHA256=<sha256 of that file>
```

Unset means "this run does not canonicalise labels". Set-but-broken means the run fails. A pipeline on a
compute host copies the registry with the run inputs and pins the same digest; the registry version then
travels in the run manifest, and a regenerated output can be compared against the version that produced it.

## Verifying a pin before a long run

```bash
sha256sum "$LACLAUGPT_MERGE_REGISTRY"
python -c "from laclaugpt_data_analysis.merge_registry import registry_from_env; \
r = registry_from_env(); print(r.sha256, len(r.entries)) if r else print('canonicalisation off')"
```

The second command loads and validates the registry exactly as a run would, so a bad pin fails in a second
rather than after hours of inference.

## What this adapter does not do

- It does not write the registry. Decisions are appended by the curation tooling, where the review evidence
  and the human Merge Lab live.
- It does not invent decisions for labels it cannot resolve: those keep their raw text, and a shared review
  queue is the place they surface.
- It does not re-run expensive inference. Because the raw label is preserved on every record, a new registry
  version can be applied to existing outputs offline.
