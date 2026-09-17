# EP24 issue #99: Finland/Poland reprocessing on CSC Roihu

This is the operator runbook for the issue-#99 reprocessing workflow. The public repository contains only privacy-safe orchestration, audit logic, prompt contracts and schemas. The canonical private EP24 tree is `TomiToivio/LaclauGPT-Private/analysis/ep24/`.

## 1. Prepare the private repository

On a trusted machine with access to both private repositories:

```bash
cd /path/to/LaclauGPT-Private
git submodule update --init --recursive
bash analysis/ep24/migrate_from_legacy.sh
python analysis/ep24/codebooks/build_country_codebooks.py \
  --resources analysis/ep24/research_resources \
  --output analysis/ep24/codebooks/generated
python analysis/ep24/codebooks/review_generated_codebooks.py \
  analysis/ep24/codebooks/generated/ep24_fi.json \
  analysis/ep24/codebooks/generated/ep24_pl.json \
  --output analysis/ep24/codebooks/generated/review.json
```

Review every alias collision, incompatible duplicate and missing-provenance warning before a production run. Codebook presence is controlled grounding, not evidence that a category occurs in a specific source item.

The migration copies the January 9, 2026 dashboard inputs and the three researcher workbooks into the canonical private tree:

```text
analysis/ep24/source_data/ep24_finland_dashboard_9_1_2026.csv
analysis/ep24/source_data/ep24_poland_dashboard_9_1_2026.csv
analysis/ep24/research_resources/entities.xlsx
analysis/ep24/research_resources/themes.xlsx
analysis/ep24/research_resources/research_notes.xlsx
```

## 2. Stage a private Roihu runtime

Clone the public Data Analysis repo and the private repo into trusted CSC storage. Keep the runtime data root outside the public Git checkout.

```bash
export LACLAUGPT_DATA_DIR=/scratch/<project>/<user>/laclaugpt-data
cd /path/to/LaclauGPT-Private
bash analysis/ep24/stage_runtime.sh "$LACLAUGPT_DATA_DIR"
```

This stages only the private resources required by the public orchestration under `$LACLAUGPT_DATA_DIR/ep24/`, including the FI/PL source CSVs, generated private codebooks, run configs and the legacy-compatible private media driver.

## 3. Audit the January 2026 results before reprocessing

The Roihu orchestrator runs these automatically, but they can also be inspected manually:

```bash
cd /path/to/LaclauGPT-Data-Analysis
python -m laclaugpt_data_analysis.ep24_quality audit-legacy \
  --country finland \
  --source "$LACLAUGPT_DATA_DIR/ep24/csv/ep24_finland.csv" \
  --output "$LACLAUGPT_DATA_DIR/ep24/audits/finland_legacy_audit.md"

python -m laclaugpt_data_analysis.ep24_quality audit-legacy \
  --country poland \
  --source "$LACLAUGPT_DATA_DIR/ep24/csv/ep24_poland.csv" \
  --output "$LACLAUGPT_DATA_DIR/ep24/audits/poland_legacy_audit.md"
```

The audit is intentionally descriptive. It identifies duplicate IDs, missing transcript/OCR/frame evidence, interpretation fields populated without basic evidence, language/source distributions and places where political-preference metadata coexists with generated summaries. The latter is a leakage risk to inspect, not proof that leakage occurred.

The audit does not decide whether an entity, theme, signifier or populist interpretation is substantively correct. That still requires researcher review against source evidence.

## 4. Dry run

Dry run validates the staged private inputs, rebuilds deterministic pilot manifests and writes the legacy audit without starting model inference:

```bash
cd /path/to/LaclauGPT-Data-Analysis
export LACLAUGPT_REPO_ROOT=$PWD
export EP24_RUN_MODE=dry-run
bash scripts/ep24/run_country_reprocess_v2.sh finland
bash scripts/ep24/run_country_reprocess_v2.sh poland
```

## 5. Pilot regression run

Run a deterministic diversity-first sample before full-country processing:

```bash
export EP24_RUN_MODE=pilot
export EP24_SAMPLE_SIZE=20
sbatch --account=<CSC_PROJECT> --export=ALL scripts/ep24/ep24_roihu_reprocess.sbatch
```

Sampling uses source type, author and political-preference metadata only to diversify the regression sample. Political-preference metadata must not be injected into substantive model evidence.

The active EP24 contracts remain the legacy-complete evidence-first v2 prompts:

```text
ep24.frame_analysis:v2
ep24.translation:v1
ep24.summary_analysis:v2
ep24.laclau_analysis:v2
```

The public+private codebook merge fails closed if the private FI/PL human-grounded layer is absent.

## 6. Old-vs-new review

When a reprocessed dashboard CSV exists, the orchestrator writes:

```text
$LACLAUGPT_DATA_DIR/ep24/comparisons/finland_old_vs_new.md
$LACLAUGPT_DATA_DIR/ep24/comparisons/poland_old_vs_new.md
```

The comparison reports record matching, changed fields and provenance coverage. A changed or longer answer is not treated as better. Human review should focus on:

- entity canonicalization and alias resolution
- theme granularity and missed/new themes
- original-language/translation fidelity
- literal multimodal evidence versus interpretation
- unsupported ideological, formation, antagonism or signifier claims
- correct treatment of irony, quotation, satire, reposts and source/speaker ambiguity
- evidence/provenance traceability
- appropriate abstention where evidence is insufficient
- whether Finland and Poland remain analytically country-specific

## 7. Full Finland and Poland run

Only after reviewing the pilot audit/comparison:

```bash
export EP24_RUN_MODE=full
sbatch --account=<CSC_PROJECT> --export=ALL scripts/ep24/ep24_roihu_reprocess.sbatch
```

The private legacy-compatible driver historically expects the filename `finland_sample20.csv` / `poland_sample20.csv`. In `full` mode the orchestration preserves that compatibility filename but fills it with the complete country source CSV. This is a compatibility detail, not sampling.

## 8. Outputs and reproducibility

Expected private runtime outputs include:

```text
ep24/audits/*_legacy_audit.md
ep24/annotations/
ep24/canonical/
ep24/csv/ep24_*_reprocessed.csv
ep24/comparisons/*_old_vs_new.md
ep24/effective_codebooks/
ep24/human_reports/
ep24/reviews/
```

Keep run/model/prompt/codebook provenance in canonical outputs. Do not copy real EP24 rows, workbook-derived mappings, private codebooks, reports containing research data, CSC credentials or restricted paths back into this public repository.

## Analysis-quality policy for the rerun

The objective is not to reproduce the January 2026 dashboard verbatim. Preserve legacy field compatibility, but prefer the current modular and evidence-first architecture. Descriptive multimodal analysis comes before deeper Laclau analysis; optional DNA/Critical-AI steps remain project-configured and must not be forced onto EP24 merely because they exist for other projects.

Researcher notes provide context. Entity/theme workbooks provide normalization vocabulary. Neither may silently become document-level labels. Nodal/floating/empty signifiers, antagonisms and discourse formations remain empirical interpretations requiring source/corpus evidence and should use explicit uncertainty or abstention when support is weak.
