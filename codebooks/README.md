# Codebooks

Codebooks are controlled research vocabulary: canonical labels, stable IDs,
aliases, definitions and provenance for entities, actors, topics, signifiers,
affect targets and formations.

## Directory convention

```text
codebooks/
├── public/     # conceptual/methodological codebooks intended for publication
├── examples/   # fully synthetic example format files
└── private/    # NEVER COMMITTED — .gitignore enforces
```

## Public vs private rule

**Public codebooks are methodology.** They contain conceptual definitions,
seed vocabulary derived from published theory, and synthetic examples. A
public codebook must never contain: corpus-derived surface forms from real
research data, private target/entity lists, participant-identifying
information, or study-specific operational mappings grounded in research
diaries or unpublished data.

**Private codebooks are research data/configuration.** Study-specific
codebooks (e.g. election-entity mappings grounded in legacy research diaries)
stay in `codebooks/private/`, an ignored local path, a private repository or
external storage, selected through configuration.

Before migrating or committing any codebook, classify it:

| Classification | Meaning | Action |
|---|---|---|
| Public/methodological | conceptual definitions, published theory, synthetic examples | commit under `codebooks/public/` |
| Synthetic example | format demonstration only | commit under `codebooks/examples/` |
| Private/study-specific | unpublished study mappings, diary-derived, target lists | keep out of Git entirely |

## Loading

Private codebooks are selected by configuration (environment or local
non-committed config files). The seed loader assigns PROVISIONAL state to
every seeded object; promotion to CANONICAL happens only through the memory
resolution loop with human validation (THEORY.md INV_HUMAN_REVIEW).