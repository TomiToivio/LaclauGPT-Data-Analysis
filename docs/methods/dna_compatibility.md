# DNA-compatible statement coding

This document describes the optional LaclauGPT Data Analysis step that proposes evidence-linked statements compatible with the core semantics of Discourse Network Analyzer (DNA) and rDNA. The step is disabled by default and LLM-produced statements remain provisional until reviewed by a human researcher.

## What DNA encodes

Discourse Network Analysis combines qualitative content analysis with network analysis. Its basic analytical move is to code statements by actors about reusable concepts or claims, retain the actor's support/opposition qualifier, and project repeated actor-concept positions into affiliation, congruence, conflict and longitudinal networks.

The current DNA source model (`model.Statement`) stores document identity, statement type, coder, selected source text, start/stop character positions, date/time and typed statement-variable values. DNA 3.x supports extensible statement types and variables, while the conventional DNA statement uses person, organization, concept and agreement variables.

As verified on 2026-09-17, the current public release is **DNA 3.1.2 / rDNA 3.1.2** (published 2026-07-26). This implementation targets the existing LaclauGPT DNA/rDNA adapters and records 3.1.2 as the reference release for compatibility testing.

## Pipeline position

The canonical order is:

```text
CanonicalRecord
  -> preprocessing / multimodal frame analysis
  -> multimodal summary + light sociology
  -> Laclau/Mouffe/Palonen discourse analysis
  -> optional DNA statement coding
  -> optional Critical AI Studies
  -> canonical post-processing / graph / vector sinks
```

The DNA step is invoked from the canonical optional-analysis dispatch before Critical AI Studies. This lets Critical AI consume DNA proposals as prior analysis when configured, while DNA itself does not depend on Critical AI interpretation.

## Configuration

```yaml
analysis:
  dna_statement_coding:
    enabled: false
    provider: ollama
    model: gemma4:12b
    prompt_version: v1
    concept_mode: codebook_or_provisional
    require_binary_agreement: false
    duplicate_policy: preserve
    include_prior_analysis: true
    include_rag: true
    include_periodic_context: false
```

`enabled: false` is the default and causes zero additional model calls. `require_binary_agreement: false` is the safe default: ambiguous statements are retained as abstentions/proposals and excluded from binary support/opposition use until reviewed. `duplicate_policy: preserve` retains statement-level evidence; downstream DNA/rDNA projection may collapse duplicates according to network-construction settings.

## Canonical field mapping

The implementation reuses `laclaugpt_data_analysis.discourse_network.DiscourseStatement` rather than defining another competing statement model.

| LaclauGPT field | DNA meaning | Mapping |
| --- | --- | --- |
| `source_record_id`, `source_url` | document identity | lossless when source identity exists |
| `metadata.dna_statement_type` | statement type | `DNA Statement` |
| `actor_name`, `actor_id` | person or institutional speaker | canonical actor projection |
| `metadata.person` | person variable | preserved extension, directly projectable |
| `metadata.organization` | organization variable | preserved extension, directly projectable |
| `concept_id`, `concept_label` | concept variable | direct |
| `stance=support` | `agreement=true` | direct |
| `stance=oppose` | `agreement=false` | direct |
| `stance=unknown`, `abstained=true` | no reliable binary agreement | excluded from binary DNA projection until reviewed |
| `metadata.agreement` | explicit DNA boolean/null | direct |
| `evidence.quote` | selected statement text | direct |
| `evidence.start_char`, `end_char` | start/stop offsets | direct, zero-based Python span with exclusive stop |
| `timestamp` | statement/document date-time | direct when available |
| coder/model/provenance fields | coder/provenance | preserved; exporter decides DNA-native representation |
| confidence/review fields | LaclauGPT extension | not interpreted as DNA variables |

The DNA-compatible core projection is therefore:

```text
(person OR organization) × concept × agreement
```

with source/document/date/evidence anchoring retained.

## Agreement semantics

`agreement` has one meaning only: whether the coded speaker supports/affirms or opposes/rejects the concept **as formulated**.

It is not synonymous with Laclaudian `Us`, `Them`, frontier, equivalence, difference, antagonism, nodal point, floating signifier or formation. The coding prompt explicitly forbids automatic mappings such as `Us -> true` or `antagonism -> false`.

Ambiguous wording, irony, sarcasm, a quoted opponent, reporter narration or second-hand attribution must produce a null agreement with an explicit abstention/ambiguity status rather than a fabricated binary code.

## Evidence and offsets

The model proposes exact `evidence_text` plus start/stop offsets. The implementation validates them against `CanonicalRecord.content.text`:

1. accept supplied offsets only when the exact substring matches;
2. otherwise search for the exact quotation and repair the offsets deterministically when found;
3. if the exact quotation cannot be located, keep the proposal but mark it `needs_review` and do not claim an exact span.

Unicode offsets use Python string character indexing. This is covered by deterministic tests with Finnish, Polish and English source material.

## Speaker and organization handling

The speaker must be distinguished from actors merely mentioned in the source. A person and their organization are preserved separately. If only an organization speaks institutionally, that organization becomes the canonical actor. If a person is known but affiliation is unsupported, organization remains null.

Stable IDs are reused when the model/codebook/entity context supplies them. Otherwise deterministic IDs are derived from normalized labels. Concept candidates likewise use an existing concept ID when supported and otherwise receive a deterministic provisional ID.

## Concept normalization

DNA networks only make sense when repeated concepts are genuinely comparable. The default `codebook_or_provisional` mode therefore instructs the model to use a codebook concept only for a supported semantic match and otherwise create a provisional concept candidate.

Prefer proposition-like concepts with stable polarity, for example:

```text
AI development should be paused
Open-source AI models should remain legally available
Data-centre electricity consumption requires stricter regulation
```

rather than vague topics such as `AI`, `regulation` or `energy`.

## Duplicate handling

Each proposal receives a deterministic duplicate key based on:

```text
(document, actor, concept, agreement)
```

Statement-level evidence is preserved by default. The extraction stage does not silently collapse repeated claims. DNA/rDNA export or network projection may apply duplicate handling later and should record the chosen policy in output metadata.

## Human review and provenance

Every LLM-produced statement stores:

- exact/proposed evidence and offsets;
- person and organization;
- concept ID/label/original wording;
- agreement and agreement status;
- confidence and uncertainty reason;
- model and prompt provenance;
- codebook revision;
- duplicate key/policy;
- validation status.

The full optional-stage payload is written to `intermediate.stage_outputs.dna_statement_coding` and mirrored into `analysis.plugin_results.dna_statement_coding` for dashboard/review clients. Human review should create a reviewed/validated revision without destroying the original proposal.

## Interoperability

This stage produces the statement layer consumed by the existing/planned DNA interoperability work:

- issue #31: DNA `.dna` / CSV interoperability;
- issue #42: multi-method analysis and DNA network projections;
- issue #57: DATS/DNA portable exchange.

The repository already contains `interoperability/dna` adapters and actor/concept network construction helpers. Native `.dna` or rDNA integration should treat this stage's statements as inputs, not reinterpret their semantics.

## Reproducible example

Source:

```text
Minister A said: “Open-source AI models should remain legally available.”
```

Provisional canonical statement:

```yaml
person: Minister A
organization: null
concept: Open-source AI models should remain legally available
agreement: true
evidence_text: Open-source AI models should remain legally available
start: <validated character offset>
stop: <validated exclusive character offset>
validation_status: provisional
```

The DNA projection becomes actor `Minister A` × concept `Open-source AI models should remain legally available` × agreement `true`. Across documents, rDNA/DNA can use repeated actor-concept positions to build actor-concept affiliation networks and derived congruence/conflict networks.

## Limitations

LLMs can misidentify speakers, normalize distinct claims into one concept, miss irony, overread affiliations and fabricate certainty. Context retrieval can also bias normalization. Therefore the prompt separates source evidence from prior analysis/RAG/context, uncertain stances can abstain, exact spans are programmatically checked, and all model-produced coding remains provisional.

Network outputs are only as valid as the coding and normalization decisions beneath them. Community structure must not be treated as an automatic ideological classification.

## References

- Leifeld, P. (2017). “Discourse Network Analysis: Policy Debates as Dynamic Networks.” In *The Oxford Handbook of Political Networks*, 301–326. https://doi.org/10.1093/oxfordhb/9780190228217.013.25
- Leifeld, P. (2013). “Reconceptualizing Major Policy Change in the Advocacy Coalition Framework: A Discourse Network Analysis of German Pension Politics.” *Policy Studies Journal* 41(1), 169–198. https://doi.org/10.1111/psj.12007
- Leifeld, P. & Mastroianni, L. (2025). “Discourse network analysis and its use in education.” https://doi.org/10.4337/9781035312191.00019
- Leifeld, P., Gruber, J. & Bossner, F. *Discourse Network Analyzer Manual* (DNA 2.x coding model). https://github.com/leifeld-lab/dna/releases/download/v2.0-beta.24/dna-manual.pdf
- Current DNA source and releases: https://github.com/leifeld-lab/dna
- Current `Statement` source model: https://github.com/leifeld-lab/dna/blob/master/dna/src/main/java/model/Statement.java
- rDNA source: https://github.com/leifeld-lab/dna/tree/master/rDNA

Where the older manual and current 3.x source/release behavior differ, current source/release behavior wins.