# Phase 0 Prompt Example: Social Network Analysis (SNA)

This file gives an example prompt specification for a later Social Network Analysis layer.

The LLM's role is mainly to extract **observable social relations** from text and normalize them into a structured edge list.

Actual network analysis should be done with deterministic graph software such as NetworkX, igraph, graph-tool or equivalent.

---

## 1. Example system prompt

```text
You are a social-science text-analysis assistant extracting structured social
network relations from text.

Follow the supplied relation codebook exactly.

Extract only relations that are supported by the current source.

Do not infer social ties merely because two actors appear in the same document,
share an ideology, belong to the same broad arena, or discuss the same topic.

Persistent memory may provide canonical actor IDs and aliases.
RAG context may assist disambiguation or later longitudinal comparison.
Neither is evidence that a relation exists in the current source.

Do not calculate network centrality, communities or structural importance.
Return only the requested structured relation data.
```

---

## 2. Example relation codebook

The SNA layer should define which edge types matter for the research question.

```yaml
node:
  definition: >
    A canonical social actor such as a person, organization, institution,
    collective, account or other research-relevant entity.

relations:
  communicates_with:
    definition: >
      Actor A directly communicates with or addresses actor B.
    directed: true

  supports:
    definition: >
      Actor A explicitly supports, endorses, assists or aligns with actor B
      in the source.
    directed: true

  opposes:
    definition: >
      Actor A explicitly opposes, attacks, rejects or contests actor B.
    directed: true

  collaborates_with:
    definition: >
      Actor A and actor B are explicitly described as cooperating on an
      activity, project, campaign or institution.
    directed: false

  member_of:
    definition: >
      Actor A is explicitly described as a member, employee, office-holder,
      participant or formal part of organization B.
    directed: true

  funds:
    definition: >
      Actor A is explicitly described as providing financial support to actor B.
    directed: true

  cites_or_references:
    definition: >
      Actor A explicitly cites, tags, links, quotes or references actor B.
    directed: true

evidence_levels:
  explicit:
    definition: relation directly stated or unambiguously represented
  inferred:
    definition: >
      relation follows from strong textual evidence but is not directly stated;
      use only if the project permits inferred edges
```

A project may choose a much smaller set. Fewer, clearer relation types usually produce better data.

---

## 3. Inputs

```text
### CURRENT SOURCE
<text>

### SOURCE METADATA
<source ID, author, account, date, platform, etc.>

### RELATION CODEBOOK
<allowed relation types>

### PERSISTENT MEMORY
<canonical actor IDs and aliases>

### RETRIEVED CORPUS CONTEXT
<optional records for identity resolution or comparison>
```

Source classifications such as `elite`, `grassroots`, `media`, `civil_society`, `parliamentary` are ordinary node/source metadata. Do not turn them into edges by themselves.

---

## 4. Detailed extraction instructions

```text
1. Identify research-relevant actors appearing in the current source.
2. Resolve actor labels to canonical IDs when memory provides a reliable match.
3. Extract relations only from the allowed relation codebook.
4. Preserve edge direction.
5. Attach source evidence to every edge.
6. Record whether the relation is explicit or inferred.
7. Preserve timestamps or temporal qualifiers when available.
8. Preserve platform/source provenance.
9. Keep repeated evidence for the same edge if useful for later weighting.
10. Put ambiguous identity matches into `unresolved_nodes`.
11. Put potentially important relation types absent from the codebook into
    `uncoded_relation_candidates` rather than inventing permanent edge types.

Do not:
- create an edge from simple co-mention
- create an edge from shared topic
- create an edge from shared ideology
- create an edge from shared arena category
- infer friendship, influence or coordination without evidence
- infer organizational membership from public sympathy
- calculate centrality or community membership with the LLM
```

---

## 5. Example output

```json
{
  "record_id": "SOURCE_ID",
  "method": "social_network_relation_extraction",
  "nodes": [
    {
      "label": "Actor A",
      "canonical_id": "actor:a",
      "type": "person"
    },
    {
      "label": "Organization B",
      "canonical_id": "actor:org_b",
      "type": "organization"
    }
  ],
  "edges": [
    {
      "source": "actor:a",
      "target": "actor:org_b",
      "relation": "member_of",
      "directed": true,
      "evidence_level": "explicit",
      "evidence": ["..."],
      "confidence": "high",
      "date": "2026-09-18"
    }
  ],
  "unresolved_nodes": [],
  "uncoded_relation_candidates": [],
  "uncertainties": []
}
```

---

## 6. Keep graph computation outside the LLM

After extraction, deterministic code can construct the graph:

```python
import networkx as nx

G = nx.MultiDiGraph()

for edge in edges:
    G.add_edge(
        edge["source"],
        edge["target"],
        relation=edge["relation"],
        record_id=record_id,
        date=edge.get("date"),
    )
```

Then calculate:

- degree
- betweenness
- eigenvector/PageRank where appropriate
- connected components
- communities
- temporal networks
- multiplex relations
- projections
- diffusion or simulation inputs

These are computational graph operations, not prompt tasks.

---

## 7. Castells/Luhmann compatibility without bloating extraction

A later SNA interpretation layer may use theoretical perspectives such as:

- Castells: networks, flows, nodes, communication power
- Luhmann: recursive communication and functionally differentiated social systems
- Harrison White: identities, relations and network domains
- Elena Esposito: communication, observation and digital society

Do not put long summaries of these theories into every relation-extraction prompt.

Instead, keep extraction close to observable relations and add theory in a **separate interpretation step** if needed.

For example:

```text
TEXT
  -> relation extraction
  -> graph database / edge list
  -> deterministic SNA
  -> optional theoretical interpretation
```

This prevents the model from manufacturing theoretically attractive edges.

---

## 8. Memory and RAG

### Memory

Use for:

- canonical actor IDs
- aliases
- account/person/organization mappings
- researcher-reviewed entity merges

### RAG

Use for:

- actor disambiguation
- checking whether the same relation appears across multiple records
- longitudinal comparison
- retrieving context before a separate interpretive step

Neither should silently create source-level edges.

---

## 9. Prompt-length guidance

A good SNA extraction prompt can be extremely small:

```text
short system rules
+ allowed relation types
+ current source
+ actor memory
+ optional small RAG context
+ JSON schema
```

The codebook should tell the model **which relations count**. Network theory belongs primarily in downstream analysis and interpretation, not in basic edge extraction.
