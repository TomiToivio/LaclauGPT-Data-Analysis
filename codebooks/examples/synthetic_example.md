# Synthetic example codebook

Fully synthetic example demonstrating the codebook file format used by the
seed loader. Safe to commit: every label, definition and identifier here is
invented for documentation and tests — no corpus-derived content.

## Parties (kind=actor)

| Canonical label | Short | Family (example bucket) |
|---|---|---|
| Synthetic Progressive Party | SPP | Centre left |
| Synthetic Conservative Union | SCU | Centre right |
| Synthetic Green Movement | SGM | Green |
| Synthetic Populist Alliance | SPA | Populist right |

## Topics (kind=topic)

| Canonical label | Aliases |
|---|---|
| synthetic climate policy | climate, environment |
| synthetic migration policy | migration, border |
| synthetic digital policy | digital, platform regulation |

## Signifiers (kind=signifier)

| Canonical label | Seed definition |
|---|---|
| the synthetic people | Candidate nodal point; must be demonstrated from evidence |
| synthetic elite | Candidate frontier element; criticism alone is not antagonism |
| synthetic change | Candidate floating signifier; competing fixations must be compared |

## Usage

Use this file as a template for private study codebooks: same structure,
same kind vocabulary (`actor`, `entity`, `topic`, `signifier`, `target`,
`formation`), same PROVISIONAL seeding semantics. Private study codebooks
follow this format but live outside Git (see `codebooks/README.md`).