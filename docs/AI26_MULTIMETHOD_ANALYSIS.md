# AI26 multi-method discourse analysis

Issue #42 adds an experimental, less Laclau-centred analysis stack for AI26. It does **not** modify `paper/PAPER.md` and it does not treat any provisional ideological formation as ground truth.

## Shared statement / claim layer

`DiscourseStatement` is the common evidence-linked analytical unit. It now carries:

- stable statement, source-record, actor and concept identifiers;
- speaker distinct from optional target actor;
- normalized concept plus original wording;
- normalized proposition / claim;
- support, opposition, neutral, mixed or unknown stance;
- exact evidence span and source URL;
- project, arena, platform and timestamp metadata;
- model/provider/version, confidence, codebook and provenance;
- abstention and human-review/correction fields.

A non-abstained normalized proposition requires evidence. Missing support should be represented as abstention or an empty proposal rather than invented coding.

## Framing

`laclaugpt_data_analysis.framing` implements a compact operational layer grounded in:

- Robert M. Entman (1993), “Framing: Toward Clarification of a Fractured Paradigm.”
- Robert D. Benford & David A. Snow (2000), “Framing Processes and Social Movements.”
- Snow, Rochford, Worden & Benford (1986), “Frame Alignment Processes, Micromobilization, and Movement Participation.”
- Erving Goffman (1974), *Frame Analysis*, as conceptual background rather than a claim that the entire Goffman framework has been computationally operationalized.

Supported grounded frame-element kinds are:

- problem definition;
- causal attribution;
- normative evaluation;
- remedy;
- diagnostic framing;
- prognostic framing;
- motivational framing.

Every non-empty element carries its own evidence span. Multiple frames and competing elements can attach to the same statement/document. Counts are descriptive and must not be read as frame resonance or political effectiveness.

## Discourse Network Analysis

The existing Leifeld-inspired DNA layer remains the relational backbone. It now also provides:

- actor-concept signed matrices;
- actor congruence and conflict projections;
- concept congruence and conflict projections;
- reproducible temporal windows;
- descriptive community proposals on actor congruence;
- a conflict-share / fragmentation descriptor with an explicit warning that it is **not** a validated substantive polarization measure.

The implementation follows the methodological logic of Philip Leifeld (2016, 2017) and takes interoperability inspiration from `leifeld-lab/dna`, while remaining native Python and storage-neutral.

Abstained statements are retained in coverage/audit outputs but excluded from signed network construction.

## Bourdieu / MCA / GDA

Issue #29 supplied the experimental social-space layer in `analysis.social_space`. Issue #42 integrates it into the same artifact contract rather than creating a parallel pipeline.

Relevant sources include:

- Pierre Bourdieu, *Distinction* (1984 English edition).
- Pierre Bourdieu, *Homo Academicus* (1988 English edition).
- Brigitte Le Roux & Henry Rouanet, *Multiple Correspondence Analysis* (2010).
- Brigitte Le Roux & Henry Rouanet, *Geometric Data Analysis* (2004/2005).

Active variables construct the space. Sensitising AI26 labels such as accelerationist, existential-risk/x-risk, Critical AI, anti-AI or techno-optimist should normally be supplementary variables projected afterward, not active variables that predetermine the geometry.

The integration never manufactures MCA variables from arbitrary LLM labels. The caller must supply an explicitly reviewed categorical table plus `SocialSpaceConfig`.

## Integrated artifact

`build_multimethod_artifact()` returns schema `laclaugpt.multimethod.v1` with:

- `statements`: complete shared claim rows;
- `frames`: flattened grounded frame elements;
- `frame_frequency`: descriptive element counts;
- `dna.actor_congruence`;
- `dna.actor_conflict`;
- `dna.concept_congruence`;
- `dna.concept_conflict`;
- `dna.communities`;
- `dna.fragmentation`;
- `dna.temporal_windows`;
- optional `mca` payload using `laclaugpt.social-space.v1`;
- optional `mca_clusters`;
- cross-method IDs linking statements, frames, actors, communities and MCA points.

Visualization should consume these outputs rather than recomputing inferential analysis itself.

## AI26 usage

The convenience function `build_ai26_artifact()` fixes the project filter to `ai26` while preserving optional arena/platform filters. It is suitable for a bounded batch or an incremental worker cycle. Storage remains outside this pure transformation layer, so the same function can be fed from local CSV/SQLite or remote MongoDB and its artifact persisted through the existing MongoDB/S3/CSC Allas architecture.

A minimal pattern is:

```python
artifact = build_ai26_artifact(
    statements,
    frames=frames,
    social_space_records=actor_rows,
    social_space_config=SocialSpaceConfig(
        unit="actor",
        id_field="actor_id",
        active_variables=("actor_type", "arena", "organization_type"),
        supplementary_variables=("sensitising_formation",),
        codebook_version="ai26-...",
        sampling_frame="AI26 bounded validation sample",
    ),
    temporal_window_days=7,
    analysis_run_id="ai26-...",
)
```

For incremental processing, keep stable statement IDs and canonical source IDs. Rebuild projections from the current selected statement set or from a reproducibly versioned bounded window. Do not merge incompatible method/codebook versions silently.

## Human validation

At minimum, researchers should inspect:

1. claim boundaries and exact evidence;
2. speaker attribution vs mentioned/target actors;
3. concept normalization;
4. support/opposition coding;
5. frame elements and their evidence;
6. sensitivity of DNA communities/conflict to uncertain coding;
7. MCA sensitivity to variable selection and rare categories;
8. repeat-run/model disagreement where LLM extraction is used.

The public test fixture is synthetic. No private AI26 row-level data is committed.

## Interpretation boundary

The methods answer different questions:

- **Claims/statements:** what explicit position is evidenced in the source?
- **Framing:** how is a problem/cause/evaluation/remedy or mobilizing diagnosis/prognosis constructed?
- **DNA:** who shares or opposes which coded positions, and how does that relational structure change?
- **MCA/GDA:** what multidimensional categorical space is constructed by reviewed variables?
- **Laclau / sociotechnical imaginaries:** optional higher-order interpretation of articulation, frontiers, political subjects, futures and hegemonic contestation.

Agreement across methods is evidence worth investigating, not automatic theoretical confirmation. Disagreement is analytically useful rather than an error to be erased.
