# Bourdieu field / social-space layer

Status: **optional, experimental, disabled by default**.

This layer adds a relational representation of actor/document positions for AI26 and other studies. It complements discourse analysis; it does not infer ideology, class, field membership, equivalence, antagonism, or hegemony from geometric proximity.

## Research question

> Which social positions, institutional locations and forms of capital are associated with which discursive positions, imaginaries, signifiers and frames?

Keep three things analytically distinct:

1. **field/social position**: institutional and relational location;
2. **position-taking**: claims, frames, imaginaries and policy stances;
3. **ideological interpretation**: higher-order researcher interpretation.

## Source review

The prototype is designed around the following methodological lessons.

- **Bourdieu, _Distinction_ (1979/1984):** social space is relational; practices and political position-takings should be analyzed in relation to distributions and compositions of capital rather than as isolated traits. Correspondence analysis is attractive precisely because it "thinks in relations."
- **Bourdieu, _Homo Academicus_ (1984/1988), _The State Nobility_ (1989/1996), and Bourdieu & Wacquant, _An Invitation to Reflexive Sociology_ (1992):** fields are structured spaces of positions and position-takings; the relevant forms of capital and boundaries are empirical questions, not labels to assign automatically.
- **Le Roux & Rouanet, _Geometric Data Analysis_ (2004/2005) and _Multiple Correspondence Analysis_ (2010/2011):** MCA/GDA represents categorical relations geometrically. Interpretation should rely on contributions, quality of representation, active/supplementary status, and substantive theory rather than visually naming axes from a plot.
- **Hjellbrekke, _Multiple Correspondence Analysis for the Social Sciences_ (2018):** MCA is especially useful for relational social-science analysis when variable construction, modality frequencies, supplementary projections, and interpretation are documented.
- **Lebaron & Le Roux; Duval, Oxford Handbook of Pierre Bourdieu chapters (2018):** GDA is a methodological partner to field analysis, not an automatic field detector.
- **Atkinson (2023/2024), "Charting fields and spaces quantitatively":** MCA should not be fetishized. CatPCA/optimal scaling may produce a different and sometimes substantively useful representation, so method comparison belongs in the workflow.
- **"Viewpoints and points of view" (European Societies, 2018):** social-space maps become more useful when related back to qualitative boundary drawing and meaning-making rather than treated as self-explanatory geometry.
- **Lebaron, "Pierre Bourdieu, Geometric Data Analysis and the Analysis of Economic Spaces and Fields":** empirical GDA can be used across institutions/economic fields, but field construction depends on theoretically justified variables.
- **Boelaert & Ollion (2025), "Representing the Social Space":** geometric representations helped shape Bourdieu's field theory, but they remain selective representations rather than literal pictures of society.

## Implemented prototype

`laclaugpt_data_analysis.analysis.social_space` implements correspondence analysis of a complete disjunctive table, i.e. a basic MCA core, using NumPy from the existing `analysis` extra.

Supported now:

- actor-space or document-space rows;
- explicit active categorical variables;
- supplementary categorical variables projected as barycentres;
- canonical row IDs retained in every coordinate table;
- eigenvalues and inertia ratios;
- row and category coordinates;
- category contributions;
- row/category cos² quality measures;
- category frequencies;
- explicit missing-value category;
- provenance for active/supplementary variables, sampling frame, codebook version, weighting and discretization;
- optional Ward hierarchical clustering on retained coordinates;
- neutral cluster/category enrichment summaries;
- stable visualization payload schema `laclaugpt.social-space.v1`.

The implementation intentionally does **not** auto-name dimensions or clusters.

## Actor-space schema

Example:

```python
from laclaugpt_data_analysis.analysis.social_space import SocialSpaceConfig, fit_mca

result = fit_mca(
    actor_rows,
    SocialSpaceConfig(
        unit="actor",
        id_field="actor_id",
        active_variables=(
            "actor_type",
            "institution_type",
            "arena",
            "recurrent_frame_cluster",
        ),
        supplementary_variables=(
            "country",
            "platform",
            "seed_imaginary",
        ),
        codebook_version="ai26-vX",
        sampling_frame="AI26 actor census/sample description",
    ),
)
```

Candidate variables include actor/institution type, elite/parliamentary/grassroots arena, country/region, platform, organizational affiliation, profession/role, visibility/status bands, recurrent frames/signifiers, and reviewed policy positions.

Continuous measurements such as audience size or network centrality should be preserved in their original form. If a categorical band is used for MCA, record the discretization rule in `SocialSpaceConfig.discretization` and keep the continuous source value elsewhere.

## Document/communication-space schema

Rows can instead be canonical documents/posts/speeches with active variables such as frame, stance, signifier cluster, policy position, system context, or reviewed claim categories. Actor metadata, time and provisional imaginary labels are often better treated as supplementary variables first so they do not mechanically construct the geometry being interpreted.

## Interpretation workflow

Recommended order:

1. define the empirical unit and sampling frame;
2. justify active variables;
3. keep provisional ideological labels supplementary when possible;
4. fit MCA;
5. inspect inertia/eigenvalues;
6. inspect category contributions and cos² before interpreting each dimension;
7. project supplementary actor metadata or discourse labels;
8. optionally cluster the retained coordinates;
9. inspect enrichment tables and original records;
10. write a human interpretation with provenance.

A dimension description should cite the categories that contribute to it. A cluster should remain `cluster 1`, `cluster 2`, etc. until a researcher interprets it from evidence.

## Position-taking analysis

The social-space result can be joined by canonical ID to discourse outputs:

```text
field/social-space coordinates
        ↕
frame / claim / imaginary / signifier / policy stance
```

Current prototype support is deliberately minimal: supplementary projections and cluster/category enrichment. Future statistical comparisons may include multinomial/logistic models, permutation tests, correspondence tables and regression on retained coordinates. These should test associations, not convert geometry into causal explanation.

## Method comparison

MCA is the implemented reference method, not the only allowed one.

- **specific MCA:** useful when selected modalities should be excluded/downweighted; not yet implemented.
- **CA:** preferable for a genuine contingency table rather than individual-level complete disjunctive coding.
- **CatPCA / optimal scaling:** important comparator, especially following Atkinson; not yet implemented natively.
- **PCA:** appropriate only for genuinely continuous standardized variables.
- **UMAP:** may be useful for exploratory visualization but is not a substitute for MCA/GDA and should never be reported as if dimensions/contributions had the same interpretation.

Python candidates for future parity: `prince`, `scikit-learn`, pandas/polars, NumPy/SciPy. R should remain a first-class optional benchmark backend: `FactoMineR`, `factoextra`, `ca`, `GDAtools`, and `soc.ca`. Arrow/Parquet is the preferred interchange format for a future Python↔R benchmark harness.

## Temporal comparison

Do not compare independently fitted MCA axes across periods as if they were stable coordinates. Future temporal work should test one of:

- a stable reference space with later observations projected as supplementary;
- Procrustes alignment with explicit diagnostics;
- pooled-period active space with time as supplementary;
- another methodologically justified alignment strategy.

A dashboard time slider should be exposed only after coordinate comparability is established.

## Visualization contract

`SocialSpaceResult.visualization_payload()` returns:

- `points`: actor/document coordinates keyed by canonical ID;
- `categories`: active-category coordinates;
- `category_contributions`;
- `row_cos2` / `category_cos2`;
- `supplementary` barycentres;
- `frequencies`;
- `eigenvalues` / `inertia_ratio`;
- provenance and interpretation warning.

Data Visualization can render actor maps, category maps, filters by supplementary metadata, justified cluster hulls, and click-through to canonical evidence without reinterpreting geometric distance as a literal social tie.

## Safeguards

- disabled by default;
- do not use automatic ideological labels as an unquestioned active variable;
- do not auto-name axes from the first visible categories;
- report rare-category frequencies;
- preserve source IDs and original continuous measurements;
- record active/supplementary choices, missing-data strategy, discretization, sampling, weighting, codebook version and library/method version in run provenance;
- compare alternative category definitions before substantive interpretation;
- geometric proximity is descriptive, not causal and not a social-network edge;
- computational clusters are not automatically social classes, fields, ideologies or hegemonic blocs.

## AI26 experiment

For the first AI26 run, prefer an actor-space model in which institutional/arena metadata and empirically recurring discourse categories construct the space, while provisional labels such as accelerationist, x-risk/doomer, Critical AI, or governance are supplementary. Then compare this geometry with DNA coalitions and framing outputs. Agreement between methods is evidence worth interpreting; disagreement is equally informative and must not be "repaired" by relabeling the data.
