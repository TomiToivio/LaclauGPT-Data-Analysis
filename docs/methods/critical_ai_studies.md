# Critical AI Studies analysis

## Scope

LaclauGPT implements Critical AI Studies as an optional, source-grounded, LLM-assisted qualitative interpretation layer. It is an explicit LaclauGPT operationalisation, not a canonical coding scheme authored by Simon Lindgren or any other single scholar. Outputs are provisional research proposals that require human inspection.

The stage is deliberately downstream of descriptive multimodal/light sociological analysis and Laclaudian discourse analysis, and can also consume DNA-compatible statement coding when that stage is present. It does not replace those methods. Cross-method disagreement is recorded rather than treated as an error.

The implementation follows the repository-wide human-in-the-loop rule: no generated interpretation becomes ground truth simply because a model produced it. There is no moral, ethical, ideological desirability or “criticality” score.

## Why this is not a generic AI ethics checklist

Simon Lindgren's *Critical Theory of AI* argues for analysis in terms of power and contention rather than reducing social analysis to narrow questions of ethics, responsibility and fairness. The broader *Handbook of Critical Studies of Artificial Intelligence* treats AI as a social, cultural, political and economic phenomenon. LaclauGPT therefore asks about ownership, political economy, labour, subjectification, data relations, infrastructures, governance, inequality, technological myths and alternatives in addition to system-level fairness.

Rosalie A. Waelen's 2025 review is an important methodological caution: Lindgren provides a broad critical orientation and productive set of questions, but not a fully specified empirical coding protocol. The schema and prompt in this repository are therefore transparent operational decisions made by LaclauGPT. They should not be described as “the Lindgren method.”

## Three ideology relations

The method follows the LaclauGPT paper's distinction between:

1. **Ideologies shaping AI**: assumptions, priorities, interests and social values embedded in development, deployment and governance.
2. **Ideologies reproduced through AI**: classifications, assumptions, viewpoints and social relations reproduced by systems and outputs.
3. **Ideological contestation over AI**: political struggle over what AI is, what it should become, whom it should serve, how it should be governed and what futures it represents.

These are analytically distinct. A source may contain one, several or none of them.

## AI as sociotechnical assemblage

The analysis never assumes that “AI” names an autonomous technical actor. Depending on the evidence, the object can be a model, application, platform, dataset, data pipeline, data centre, compute stack, company, state institution, human-machine workflow, labour process, regulatory arrangement, imagined future technology or a vague symbolic signifier. The wider assemblage can include datasets, GPUs, chips, energy and water systems, interfaces, platforms, users, firms, workers, law and institutional power.

## Analytical dimensions

The prompt offers dimensions as evidence-sensitive questions, not mandatory boxes that every source must fill.

- **Object / assemblage**: what concrete object is called AI, and what wider sociotechnical relations are actually evidenced?
- **Ideology shaping AI**: which values and assumptions are prioritised, whose interests are presented as common sense, and are political choices naturalised as technical necessities?
- **Ideology reproduced through AI**: are classification, normalisation, differential performance, discrimination, marginalisation, ranking, surveillance or subject positions evidenced in a real system or output?
- **Ideological contestation**: what struggle exists over AI's meaning, purpose, governance or desired future?
- **Power / political economy**: ownership, control, corporate/state concentration, compute/data/capital access, dependency, market structure, platform power, public/private authority, expertise and agenda-setting.
- **Labour**: annotation, moderation, microwork, professional/creative labour, deskilling/reskilling, algorithmic management, task transformation, displacement, uncompensated production and maintenance work.
- **Data / extraction / coloniality**: data provenance, consent, ownership, compensation, appropriation, language/geographic inequality, North/South dependencies and plural epistemologies. Decolonial claims are marked as a lens unless historical/material evidence supports a stronger statement.
- **Infrastructure / environment**: data centres, compute, chips, energy, water, minerals, supply chains, land, local infrastructure conflicts and distribution of costs and benefits.
- **Governance / democracy / surveillance**: accountability, participation, contestability, appeal, concrete surveillance practices, regulation and authority over acceptable risk.
- **Technological myths**: inevitability, autonomous-AI agency, intelligence/personhood metaphors, black-box or magical language, salvation/abundance, catastrophe/extinction, arms-race framing and techno-solutionism.
- **Distribution**: who benefits, who bears costs and uncertainty, who can opt out and who captures economic/social value; current effects are kept separate from speculative futures.
- **Alternatives**: only alternatives actually proposed in evidence/context, such as public/commons/cooperative ownership, labour rights, regulation, refusal, open source, decentralisation, participatory governance, redistribution, redesign or non-AI alternatives.
- **Subjectification**: evidenced ways systems or discourses classify, rank, normalise or constitute people as particular kinds of subjects.
- **Reflexive counter-reading**: alternative interpretations, missing evidence and concrete human-review tasks.

A source does not become structurally critical merely because it mentions AI. Minimal output or abstention is correct when the evidence does not support a substantive interpretation.

## Evidence hierarchy and provenance

The Critical AI prompt receives the canonical prompt envelope and keeps five evidence families distinct:

```text
SOURCE_EVIDENCE     = evidence directly in the current source record
PRIOR_ANALYSIS      = outputs of earlier LaclauGPT stages
PROJECT_CONTEXT     = study background and codebook material
RAG_CONTEXT         = externally retrieved contextual evidence
SITUATIONAL_CONTEXT = periodic summary/trend context
```

`SOURCE_EVIDENCE` has a special status for claims about the current item. Earlier analysis and RAG can guide or support interpretation but may never be silently promoted into source evidence. The generated stage stores the envelope provenance snapshot, prompt hashes, project/config/codebook revisions, resolved model metadata and the complete provisional structured output.

Exact source excerpts proposed by the model are also projected into the canonical `Evidence` collection with `analysis_method=critical_ai_studies`, dimension, finding ID and review status. This gives dashboard/export clients a stable path:

```text
Critical AI finding
→ canonical evidence ID
→ source excerpt
→ original source URL
→ context/provenance snapshot
→ model + prompt version
→ uncertainty / alternative reading
→ human review state
```

Human correction should be stored as a new review/version event according to repository conventions rather than destroying the original generated proposal.

## Relationship to the earlier pipeline

### Multimodal and light sociological pre-analysis

The multimodal stage is intentionally descriptive and may supply frame descriptions, cross-modal relations and light Castells-style context. Critical AI can use those outputs as `PRIOR_ANALYSIS`, but does not treat them as facts.

### Laclaudian discourse analysis

Laclau/Mouffe/Palonen analysis identifies articulations, signifiers, demands, collective subjects, frontiers, affects, equivalence/difference and candidate formations/imaginaries. Critical AI asks a different question about material/institutional power and sociotechnical organisation. A Laclaudian antagonism is not automatically a material power relation. Critical AI can agree with, refine or challenge a prior discourse proposal.

### DNA-compatible statement coding

When DNA statement coding is available and `include_prior_dna` is enabled, actor × concept × stance statements can be referenced. A DNA support/opposition code is not automatically an ideology and does not by itself justify a broader structural claim.

## Configuration

The feature is disabled by default and has zero additional LLM calls or stage outputs while disabled. It uses the provider object already supplied to the canonical pipeline, so Ollama remains an adapter selected by runtime configuration rather than being called directly from the method module.

```yaml
analysis:
  critical_ai:
    enabled: true
    provider: ollama
    model: gemma4:12b
    prompt_version: v1
    include_prior_laclau: true
    include_prior_dna: true
    include_rag: true
    include_periodic_context: true
    evidence_mode: strict
```

`provider` is retained as project metadata/configuration intent; execution still uses the canonical provider abstraction. `model` is stage-selectable. If no Critical AI model is specified, the canonical pipeline model is reused. Gemma4 is therefore supported for AI26 without being hard-coded globally.

The configuration reader accepts the canonical `analysis.critical_ai` subtree. A top-level `critical_ai` dictionary is accepted for compatibility, but new project configurations should use the nested form.

## Structured output

The versioned Pydantic contract is `CriticalAIAnalysis` (`critical-ai-v1`). Each finding contains:

- stable/assigned `finding_id`;
- analytical `dimension`;
- concise `claim`;
- `status`: `supported`, `tentative`, `insufficient_evidence` or `not_applicable`;
- analytical `scope`;
- actors, affected groups, institutions and resources when evidenced;
- exact `source_evidence` excerpts and canonical `evidence_ids`;
- separate prior-analysis/project/RAG/situational references;
- lens, short inspectable reasoning, alternative reading, missing evidence and optional uncalibrated confidence;
- human `review.status`, defaulting to `provisional`.

The output also contains the identified AI object/assemblage, cross-method convergence/tension, a concise overall synthesis and human-review priorities.

## Worked synthetic example

Source:

> “Our platform will become unavoidable in every office. We alone operate the hosted model API.”

Earlier multimodal/light stage: one speaker presents a product slide; no external ownership evidence beyond the speaker's statement.

Earlier Laclau proposal: “unavoidable AI” may function as an inevitability articulation; no stable discourse formation can be inferred from one item.

Optional DNA statement: actor=`Example Corp`, concept=`AI adoption`, stance=`support`.

Critical AI output can then contain two separate provisional findings:

1. **Technological myths / supported**: the actor explicitly frames adoption as inevitable. Source evidence is the word “unavoidable.” Alternative reading: promotional exaggeration rather than literal prediction.
2. **Power / tentative**: the actor claims sole operational control of the hosted API. The source supports the actor claim, but external verification of ownership/control remains a human-review priority.

It should *not* infer hidden labour, discrimination, colonial extraction, environmental costs or monopoly merely because the product is an AI platform.

## Methodological limitations

LLMs can reproduce the same ideological assumptions that Critical AI Studies is intended to examine. They can also overgeneralise from familiar critical vocabularies, hallucinate causal relations, turn RAG background into apparent source evidence, erase disagreement and produce fluent but weakly grounded structural critique. The implementation therefore uses structured provenance, explicit abstention, source excerpts, alternative readings and human review.

Waelen's review cautions against treating Lindgren's critical orientation as if it were already a complete empirical method. Offert and Dhaliwal identify three recurring methodological problems especially relevant to automated analysis: overgeneralising from individual benchmark samples (“benchmark casuistry”), using an underspecified black box as explanation (“black box casuistry”), and relying on overly simple stack-like cause/effect models of algorithmic harm (“stack casuistry”). LaclauGPT's prompt turns these warnings into operational constraints: do not generalise beyond the evidence unit, do not use “the algorithm/black box” as a causal explanation, and do not infer a linear harm chain when the assemblage is more complex.

No prompt can guarantee valid social-science inference. Corpus-level validation, triangulation, researcher reflexivity and domain knowledge remain necessary.

## Scientific sources

- Lindgren, S. (2023). *Critical Theory of AI*. Polity. ISBN 978-1-5095-5576-5 / 978-1-5095-5578-9. Publisher: https://www.wiley-vch.de/en/areas-interest/computing-computer-sciences/computer-science-17cs/artificial-intelligence-17csf/critical-theory-of-ai-978-1-5095-5576-5
- Lindgren, S. (ed.) (2023). *Handbook of Critical Studies of Artificial Intelligence*. Edward Elgar. https://www.e-elgar.com/shop/usd/handbook-of-critical-studies-of-artificial-intelligence-9781803928555.html
- Lindgren, S. (2023). “Introducing critical studies of artificial intelligence.” In *Handbook of Critical Studies of Artificial Intelligence*, 1–19.
- Richter, V., Katzenbach, C. & Schäfer, M. S. (2023). “Imaginaries of artificial intelligence.” In *Handbook of Critical Studies of Artificial Intelligence*.
- Waelen, R. A. (2025). “Simon Lindgren – A critical theory of AI.” *AI & Society* 40:5031–5033. https://doi.org/10.1007/s00146-025-02205-0
- Mohamed, S., Png, M.-T. & Isaac, W. (2020). “Decolonial AI: Decolonial Theory as Sociotechnical Foresight in Artificial Intelligence.” *Philosophy & Technology* 33:659–684. https://doi.org/10.1007/s13347-020-00405-8
- Buolamwini, J. & Gebru, T. (2018). “Gender Shades: Intersectional Accuracy Disparities in Commercial Gender Classification.” *Proceedings of Machine Learning Research* 81:77–91. https://proceedings.mlr.press/v81/buolamwini18a.html
- Bender, E. M., Gebru, T., McMillan-Major, A. & Mitchell, M. (2021). “On the Dangers of Stochastic Parrots: Can Language Models Be Too Big?” *FAccT '21*, 610–623. https://doi.org/10.1145/3442188.3445922
- Couldry, N. & Mejias, U. A. (2019). “Data Colonialism: Rethinking Big Data's Relation to the Contemporary Subject.” *Television & New Media* 20(4):336–349. https://doi.org/10.1177/1527476418796632
- Zajko, M. (2022). “Artificial intelligence, algorithms, and social inequality: Sociological contributions to contemporary debates.” *Sociology Compass* 16(3):e12962. https://doi.org/10.1111/soc4.12962
- Offert, F. & Dhaliwal, R. S. (2024). “The Method of Critical AI Studies, A Propaedeutic.” arXiv:2411.18833. https://arxiv.org/abs/2411.18833
- Crawford, K. (2021). *The Atlas of AI: Power, Politics, and the Planetary Costs of Artificial Intelligence*. Yale University Press. https://doi.org/10.2307/j.ctv1ghv45t

The prompt text is versioned under `src/laclaugpt_data_analysis/prompts/critical_ai/`. Changes to analytical instructions require a new prompt version when they would alter interpretation semantics.