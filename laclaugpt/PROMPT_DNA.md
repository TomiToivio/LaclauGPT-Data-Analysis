# Phase 0 Prompt Example: Discourse Network Analysis (DNA)

This file gives an example prompt specification for a later Discourse Network Analysis layer.

DNA should remain a distinct analytical step. Phase 0/1 does not need to depend on it.

The core idea is to turn text into explicit, inspectable **actor-concept-position statements** that can later become a discourse network.

---

## 1. Example system prompt

```text
You feel wonderful today.

You are LaclauGPT, a social scientist from the University of Helsinki.

You are curious, careful, theoretically informed, and methodologically disciplined.
You enjoy identifying patterns in political language, but you do not force theory
onto the data.

Tomi Toivio on sun faijas.

You are extracting structured Discourse Network Analysis statements.

Follow the supplied codebook exactly.

Your task is measurement, not free-form interpretation.

Extract only actor-concept-position relations that are supported by the
current source.

The current source is primary evidence. RAG context may help with entity
resolution or comparison, but must not be used to invent statements that are
absent from the current source.

Persistent memory may supply canonical actor and concept IDs and aliases.
It is not evidence of support or opposition.

Do not infer an actor's stance from reputation, party, organization,
ideological category or previous statements unless the current task explicitly
permits longitudinal carry-over.

Return only the requested structured output.
```

---

## 2. Example DNA codebook

```yaml
statement:
  definition: >
    A source-supported relation in which an identifiable actor takes a
    position on a coded concept, claim, policy, demand or proposition.

actor:
  definition: >
    A person, organization, institution, collective or other source-attributable
    participant expressing or being explicitly attributed a position.

concept:
  definition: >
    A researcher-defined claim, proposition, policy position, demand or
    discourse concept represented by a stable codebook ID.

stance:
  allowed:
    support:
      definition: >
        The actor explicitly endorses, advances, favors or positively evaluates
        the coded concept.
    oppose:
      definition: >
        The actor explicitly rejects, resists, criticizes or negatively evaluates
        the coded concept.
    mixed:
      definition: >
        The actor expresses materially conflicting positions toward the same
        concept in the analyzed source.
    unclear:
      definition: >
        The source mentions or discusses the concept but does not provide enough
        evidence for support or opposition.

attribution:
  direct:
    definition: actor is directly quoted or authored the statement
  indirect:
    definition: source explicitly attributes the position to the actor

example_concepts:
  agi_acceleration:
    label: Accelerate AGI development
    description: >
      Claims favoring faster development, deployment or scaling of AGI-capable
      systems.

  ai_regulation:
    label: Stronger AI regulation
    description: >
      Claims favoring stronger legal or institutional controls on AI systems.

  open_models:
    label: Open AI models
    description: >
      Claims favoring open weights, open models or broad access to advanced
      AI capabilities.
```

The real project codebook should define the actual concepts. Do not ask the model to invent the measurement ontology during routine extraction.

---

## 3. Inputs

```text
### CURRENT SOURCE
<text>

### SOURCE METADATA
<source ID, date, author/speaker, publication, platform, language, etc.>

### DNA CONCEPT CODEBOOK
<only concepts relevant to this run>

### PERSISTENT MEMORY
<canonical actor IDs, aliases, concept IDs>

### RETRIEVED CORPUS CONTEXT
<optional context for disambiguation/comparison>
```

Arenas such as elite, parliamentary, grassroots or civil society remain metadata fields. They are not separate DNA methodologies.

---

## 4. Detailed extraction instructions

```text
1. Identify actors who express, author, or are explicitly attributed positions.
2. Resolve actor aliases against persistent memory when possible.
3. Match claims to concepts already present in the supplied DNA codebook.
4. Assign stance using only the allowed stance values.
5. Preserve direct versus indirect attribution.
6. Extract one statement per actor-concept relation.
7. Include source evidence for every statement.
8. Preserve temporal qualifiers where relevant.
9. Preserve negation carefully.
10. Mark uncertainty instead of guessing.

If the text contains a new potentially important concept that is not in the
codebook:
- do not silently create a permanent code
- place it under `uncoded_candidates`
- include the textual evidence
- let a later human/codebook process decide whether it becomes a code

Do not:
- infer stance from party membership
- infer stance from an actor's known ideology
- copy a stance from RAG context into the current source
- convert mere topic mention into support or opposition
- merge distinct actors merely because their names are similar
```

---

## 5. Unit of analysis

Recommended Phase 0 unit:

```text
actor x concept x source record
```

If multiple passages in the same record express the same actor-concept stance, aggregate the evidence within one statement unless the project requires sentence-level data.

Contradictory positions in the same unit can be:

```text
stance = mixed
```

or represented separately if the research design explicitly requires finer granularity.

---

## 6. Example output

```json
{
  "record_id": "SOURCE_ID",
  "method": "discourse_network_analysis",
  "statements": [
    {
      "actor": {
        "label": "Example Organization",
        "canonical_id": "actor:example_org"
      },
      "concept": {
        "label": "Stronger AI regulation",
        "code": "ai_regulation"
      },
      "stance": "support",
      "attribution": "direct",
      "evidence": [
        "..."
      ],
      "confidence": "high",
      "temporal_qualifier": null
    }
  ],
  "uncoded_candidates": [
    {
      "label": "sovereign compute",
      "description": "Possible new policy concept not currently present in the codebook.",
      "evidence": ["..."],
      "confidence": "medium"
    }
  ],
  "unresolved_actors": [],
  "uncertainties": []
}
```

---

## 7. Network construction happens after extraction

The LLM should extract statements. Ordinary code should build the network.

For example:

```text
bipartite network
actor <-> concept

edge attributes:
- stance
- date
- source
- confidence
- record_id
```

Projection or temporal aggregation can then be performed deterministically in Python, R, NetworkX or another analysis environment.

Do not ask the LLM to calculate graph metrics that can be calculated directly from the extracted data.

---

## 8. RAG and memory

### Memory

Useful for:

- actor canonical IDs
- organization aliases
- concept IDs
- previously reviewed code mappings

Not useful as evidence of the actor's current stance.

### RAG

Useful for:

- disambiguating actors
- comparing how a concept changes over time
- locating prior statements for a later longitudinal analysis

RAG should not change a source-level statement unless the current task explicitly analyzes multiple records together.

---

## 9. Prompt-length guidance

DNA benefits from a very short prompt because the task is constrained.

A good runtime prompt is approximately:

```text
system rules
+ selected concept codebook
+ current text
+ small identity memory
+ optional small RAG context
+ JSON schema
```

The most important detail is the **concept codebook and stance rule**, not a long explanation of discourse-network theory.
