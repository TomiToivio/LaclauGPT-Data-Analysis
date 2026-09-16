# EP24 reprocessing requires the private research layer

> **STOP before running Finland or Poland EP24 reprocessing on CSC Roihu.**
>
> The public repository is intentionally incomplete. It does **not** contain the researcher-generated entity mappings, theme mappings, research notes, restricted manifests, legacy row-level research data, private run configuration, or media. A scientifically valid EP24 rerun must load those materials from the authorized private runtime environment.

## Mandatory private inputs

For each real Roihu rerun, stage the corresponding private country codebook generated from the controlled researcher workbooks under:

```text
$LACLAUGPT_DATA_DIR/ep24/private_codebooks/ep24_fi.json
$LACLAUGPT_DATA_DIR/ep24/private_codebooks/ep24_pl.json
```

The private codebooks are derived from the controlled researcher sources, including the entity, theme, and research-note workbooks. Do not copy those workbooks, their row-level contents, or the generated private codebooks into this public repository.

The restricted EP24 media driver must also be available outside the public repo, normally via:

```bash
export EP24_PRIVATE_REPO_ROOT=/private/path/LaclauGPT-Discourse-Analysis-Private
export EP24_PIPELINE_SCRIPT="$EP24_PRIVATE_REPO_ROOT/ep24_mm_pipeline.py"
```

Real manifests, old EP24 dataframes, run configs, media and credentials likewise remain under the private runtime/data roots.

## Use the public runner, not an ad-hoc command

Run EP24 through:

```bash
scripts/ep24/run_country_reprocess.sh finland
scripts/ep24/run_country_reprocess.sh poland
```

or the Roihu Slurm wrapper that invokes those commands.

The country runner intentionally **fails closed**. Before analysis starts it:

1. verifies that the private country codebook exists;
2. merges it with `codebooks/public/ep24_fi_pl_v2.yaml` outside Git;
3. checks that the effective codebook contains researcher-derived private entities;
4. checks that it contains researcher-derived private themes;
5. reports the number of private research notes loaded;
6. refuses to continue when the mandatory private entity/theme grounding is absent.

A successful preflight prints a block resembling:

```text
PRIVATE EP24 GROUNDING VERIFIED
  country: FI
  private entities loaded: <non-zero>
  private themes loaded: <non-zero>
  private research notes loaded: <count>
  effective codebook: .../ep24_fi_effective.json
```

If you do not see this verification during a real Roihu rerun, stop and check the runtime configuration. Do not silently continue with the public/example codebook alone.

## Why this matters

The public codebook contains reusable methodology, language safeguards and public normalization aids. It is **not a substitute** for the human-generated EP24 research grounding. The private layer is needed to reproduce the intended Finland/Poland entity and theme normalization and to make the rerun comparable with the researcher-guided EP24 analysis.

The private grounding is contextual assistance, not source evidence. Entity/theme mappings or researcher notes must never by themselves prove that a source contains a discourse, signifier, antagonism, populist frontier, sentiment, or political claim. Those analytical claims still require evidence from the actual source material.

See also `docs/ep24-reprocessing.md` for the full privacy-safe runtime layout and Roihu workflow.
