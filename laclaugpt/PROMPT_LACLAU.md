# Phase 0 Prompt Example: Laclauian Discourse Analysis

This file is an **example research prompt specification** for a Laclauian discourse-analysis step. It is not a framework requirement.

The purpose is to show how a small hand-coded script can combine:

- a short system prompt
- a researcher-authored codebook
- explicit task instructions
- optional memory
- optional RAG context
- structured output

The prompt should operationalize the method. It should not reteach all of Laclau and Mouffe.

---

## 1. Example system prompt

```text
You are a social-science text-analysis assistant performing a Laclauian
discourse-analysis task.

Follow the supplied research codebook and task instructions exactly.

Use the current source as the primary evidence for source-level claims.
Retrieved corpus context may be used for comparison and longitudinal context,
but must never be presented as if it appeared in the current source.

Persistent memory provides canonical IDs, aliases and researcher-reviewed
analytical objects. Memory is not evidence that an interpretation is correct.

Do not infer a discourse-theoretical concept merely because it would be
theoretically plausible. Require textual evidence.

Do not infer an actor's hidden motives, ideology or intentions unless the
source explicitly supports the claim.

Return only the requested structured output.
```

---

## 2. Example compact codebook

The codebook is the authoritative operational definition for this run.

```yaml
concepts:
  nodal_point:
    definition: >
      A privileged signifier around which other meanings are organized
      in the analyzed discourse.
    positive_indicators:
      - several claims or signifiers are articulated in relation to it
      - it organizes the meaning of a wider cluster
    negative_indicators:
      - frequency alone
      - ordinary topic labels without organizing function

  moment:
    definition: >
      A sign whose meaning appears relatively stabilized within the
      discourse under analysis.

  element:
    definition: >
      A sign whose meaning remains visibly contested, unstable or open
      to competing articulations.

  chain_of_equivalence:
    definition: >
      A set of demands, identities, actors or signifiers articulated
      together through a shared opposition or common political project.
    required_evidence:
      - at least two linked items
      - an explicit or strongly evidenced relation among them

  antagonistic_frontier:
    definition: >
      A boundary that constructs opposed camps, projects, identities or
      positions as mutually conflicting.

  empty_signifier_candidate:
    definition: >
      A signifier that appears capable of representing heterogeneous
      demands or identities while remaining relatively semantically open.
    positive_indicators:
      - heterogeneous demands linked through the same signifier
      - multiple actors or positions identify with it
      - semantic breadth combined with political organizing function
    negative_indicators:
      - merely broad or vague word
      - frequency alone
      - topic label alone

  floating_signifier_candidate:
    definition: >
      A signifier whose meaning is actively contested by competing
      discourses or articulations.

  subject_position:
    definition: >
      A discursively available identity or position from which an actor
      can be represented or can speak.

  demand:
    definition: >
      An explicit or implicit claim, request, grievance, expectation or
      political objective expressed in the source.

  articulation:
    definition: >
      A relation that links signs, demands, actors or identities in a way
      that partially fixes their meaning.
```

---

## 3. Inputs to the prompt

Keep the sections visibly separate.

```text
### CURRENT SOURCE
<source text>

### SOURCE METADATA
<date, source, actor, platform, language, country, arena, stable IDs>

### FIRST-PASS ANALYSIS
<optional summary/entities/topics produced by an earlier step>

### RESEARCH CODEBOOK
<selected relevant codebook entries>

### PERSISTENT MEMORY
<canonical actor/signifier IDs, aliases, researcher-reviewed objects>

### RETRIEVED CORPUS CONTEXT
<3-8 relevant prior records, clearly identified as separate documents>
```

Source metadata such as `arena` is a filter/description. It must not change the theoretical method by itself.

---

## 4. Detailed task instructions

```text
Analyze the CURRENT SOURCE using the supplied codebook.

1. Identify important signifiers in the source.
2. Identify nodal-point candidates only when the source shows an organizing
   relation around them.
3. Identify moments and elements where the distinction is supported.
4. Extract explicit or implicit demands.
5. Identify articulations among signifiers, actors, identities and demands.
6. Identify chains of equivalence only when at least two items are linked.
7. Identify antagonistic frontiers only when an opposed relation is evidenced.
8. Identify empty-signifier candidates using the supplied operational criteria.
9. Identify floating-signifier candidates when competing meanings are visible.
10. Identify subject positions constructed by the discourse.
11. Attach evidence from the CURRENT SOURCE to every interpretive claim.
12. Distinguish source-level findings from corpus-level comparisons.
13. Use memory only to normalize labels and IDs unless instructed otherwise.
14. If evidence is insufficient, return an empty list or mark the item
    uncertain instead of forcing a theoretical category.

Do not:
- classify every frequent word as a nodal point
- classify every vague word as an empty signifier
- invent antagonism where disagreement is not evidenced
- infer stable ideology from one isolated statement
- attribute RAG material to the current source
- treat researcher memory as empirical evidence
```

---

## 5. Evidence and uncertainty rules

Each finding should include:

- `evidence`: short excerpts or source-local references
- `reasoning_summary`: concise observable justification, not hidden chain-of-thought
- `confidence`: `high`, `medium`, or `low`
- `scope`: usually `current_source`; use `corpus_comparison` only for explicit comparisons

Suggested confidence interpretation:

```text
high   = direct and repeated evidence in the source
medium = plausible and textually supported but ambiguous
low    = weak candidate worth preserving for later comparison
```

Low confidence is not a failure. It is preferable to fabricated certainty.

---

## 6. Example output format

```json
{
  "record_id": "SOURCE_ID",
  "method": "laclauian_discourse_analysis",
  "signifiers": [
    {
      "label": "AGI",
      "canonical_id": "signifier:agi",
      "evidence": ["..."],
      "confidence": "high"
    }
  ],
  "nodal_points": [
    {
      "label": "progress",
      "canonical_id": null,
      "linked_items": ["innovation", "growth", "national competitiveness"],
      "evidence": ["..."],
      "reasoning_summary": "The source repeatedly organizes several claims around progress.",
      "confidence": "medium"
    }
  ],
  "moments": [],
  "elements": [],
  "demands": [],
  "articulations": [
    {
      "from": "AGI",
      "relation": "articulated_with",
      "to": "national competitiveness",
      "evidence": ["..."],
      "confidence": "high"
    }
  ],
  "chains_of_equivalence": [],
  "antagonistic_frontiers": [],
  "empty_signifier_candidates": [],
  "floating_signifier_candidates": [],
  "subject_positions": [],
  "corpus_comparisons": [],
  "uncertainties": []
}
```

---

## 7. Prompt-length guidance

Keep the runtime prompt small.

Prefer:

```text
short system prompt
+ selected codebook entries
+ current source
+ small memory context
+ 3-8 RAG records
+ explicit JSON schema
```

Avoid injecting long theoretical essays into every call. The LLM can use general background knowledge of Laclau and Mouffe; the prompt must specify **how this project operationalizes the concepts**.

---

## 8. Phase 0 implementation note

A plain Python function is enough:

```python
prompt = build_prompt(
    source=record,
    codebook=selected_codebook,
    memory=memory_context,
    rag=rag_context,
)
result = call_llm(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
validated = validate_result(result)
save_analysis(validated)
```

No agent framework is required.
