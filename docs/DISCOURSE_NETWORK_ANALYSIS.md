# Discourse Network Analysis (experimental)

This optional layer implements the methodological core of issues #30 and #31. It treats discourse-network statements as derived, evidence-linked analytical events over canonical LaclauGPT records.

## Methodological boundary

The basic unit is:

```text
actor -> concept/claim -> stance -> time
```

LaclauGPT extends this with concept type, evidence span, coder/model provenance, confidence, codebook version and validation state. DNA network structure is descriptive evidence. Actor congruence is not automatically a chain of equivalence; concept centrality is not automatically a nodal point; cross-coalition breadth is not automatically an empty signifier; and network conflict is not automatically a Laclaudian antagonistic frontier.

The experimental bridge should be used to compare or challenge discourse-theoretical interpretations, not define them by network metrics.

## Literature baseline

The implementation follows the broad DNA methodology associated with Philip Leifeld: policy debates represented as dynamic actor-concept statement networks, with reproducible two-mode matrices, congruence/conflict projections and longitudinal comparison. The project should cite and review Leifeld (2012, 2013, 2017, 2020), Leifeld & Haunss, and applied work such as Fergie et al. and Buckton et al. before publication-facing use.

## Statement schema

`laclaugpt_data_analysis.discourse_network.DiscourseStatement` stores:

- stable statement and canonical `source_url` identity;
- actor and concept IDs/labels;
- concept type;
- stance and optional signed polarity;
- relation type and timestamp;
- exact/fallback evidence span;
- collection ID;
- coder type/model;
- confidence, codebook version and validation status;
- provenance.

Raw statement events are retained. Matrices and projections are derived reproducibly.

## Network operations

The initial descriptive API provides:

```python
actor_concept_matrix(statements)
actor_projection(statements, conflict=False)
actor_projection(statements, conflict=True)
concept_projection(statements, conflict=False)
concept_projection(statements, conflict=True)
fixed_windows(statements, days=7)
coverage_summary(statements)
```

Unknown/mixed/neutral stances are not forced into positive or negative positions. Confidence weighting is explicit and off by default.

Advanced inferential methods such as temporal ERGMs, relational event models and stochastic block models remain future optional layers after statement coding has been validated.

## Validation expectations

Before substantive use, evaluate actor recognition, concept coding and stance coding against human-coded material and report precision/recall/F1 or agreement measures as appropriate. Report corpus coverage, unknown stance rate, evidence-anchor quality, duplicate/repeated-statement sensitivity and projection-threshold robustness.

## DNA interoperability

The adapter lives under:

```text
laclaugpt_data_analysis.interoperability.dna
```

It is adapted from the predecessor `LaclauGPT-Discourse-Analysis/dna_adapter` rather than being a clean-room replacement.

Supported operations:

```python
export_dna_project(...)
export_dna_statements_csv(...)
import_dna_project  # represented by document + statement + concept import functions
import_dna_documents(...)
import_dna_statements(...)
import_dna_concepts(...)
import_dna_statements_csv(...)
validate_dna_project(...)
```

### Native `.dna`

`.dna` is SQLite. The current adapter targets the DNA 3.0/3.1 on-disk family used by the predecessor adapter. `validate_dna_project()` checks required tables and version before import. Export refuses to overwrite an existing project.

The native project preserves actor, concept, stance, concept type, relation type, canonical source URL, statement ID, evidence and metadata/provenance. Stable actor/concept IDs that DNA cannot represent directly are carried in metadata rather than discarded.

DNA's boolean `agreement` field is populated only as a compatibility aid. It is not interpreted as Laclaudian equivalence/difference or Us/Frontier semantics.

### Human coding workflow

Recommended round trip:

```text
canonical records / extracted statements
 -> DNA export
 -> human coding, recoding, concept merging
 -> DNA import
 -> DiscourseStatement(coder_type=human, validation_status=validated)
 -> descriptive DNA projections
 -> optional comparison with discourse-theoretical analysis
```

Imported human edits receive explicit DNA-import provenance. Machine annotations are not destructively overwritten.

### CSV

CSV is the transparent fallback and R/rDNA interchange route. It contains human-readable fields plus canonical IDs, evidence offsets and JSON provenance. UTF-8 is used explicitly.

## Evidence anchoring

Exact offsets are preserved where possible. When text has changed or evidence cannot be located exactly, `EvidenceSpan.exact` is false. A fallback anchor must never be presented as exact evidence.

Multilingual/Unicode round-trip coverage should include Finnish, Polish, Hungarian and emoji/non-BMP text.

## R interoperability

The CSV/native DNA outputs can be consumed externally and then moved into R workflows using DNA/rDNA-compatible paths and packages such as `igraph`, `network`, `sna`, `statnet` or `btergm`. R is not a Python package dependency.

## Privacy

Generated `.dna`, CSV and derived network files are runtime research data and must remain under ignored `data/` or other private storage. Do not commit real DNA projects. Exporting restricted source text requires explicit researcher authorization.
