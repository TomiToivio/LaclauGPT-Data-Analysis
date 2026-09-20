# Codebooks

Codebooks are controlled research vocabulary: canonical labels, stable IDs,
aliases, definitions and provenance for entities, actors, topics, signifiers,
affect targets and formations.

Phase 1's canonical public methodological codebook is
`codebooks/public/phase1_v1.yaml`. Its configuration contract, layering,
validation and fingerprints are documented in
`docs/PHASE1_CODEBOOKS_SETTINGS.md`.

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

## Authority and discovery

Phase 1 distinguishes schema/taxonomy definitions, researcher-authoritative
entries, model-discovered candidates and derived outputs. A model-discovered
candidate must remain `state: discovered` with `provenance: model` until a
researcher explicitly promotes it. Validation rejects model-originated entries
that are silently marked authoritative.

## Loading

Private codebooks are selected by configuration (environment or local
non-committed config files). The legacy seed loader assigns PROVISIONAL state to
seeded objects; promotion to CANONICAL happens only through the memory resolution
loop with human validation (THEORY.md INV_HUMAN_REVIEW).

For the canonical Phase 1 protocol, use `laclaugpt-phase1-config` to validate,
render (with secret redaction), and fingerprint public plus private overlays.
