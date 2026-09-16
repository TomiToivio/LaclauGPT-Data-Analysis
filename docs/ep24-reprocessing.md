# EP24 Finland/Poland reprocessing on CSC Roihu

This public repository contains the reusable, privacy-safe orchestration and methodology for reprocessing the EP24 Finland and Poland material. Real research data, researcher workbooks, row-level annotations and private run configuration stay outside Git.

## Privacy boundary

Do **not** commit any of the following here:

- Finland/Poland EP24 manifests or legacy row-level CSVs
- videos, transcripts, OCR output, annotations, researcher exports or reports
- human-generated workbooks (`entities.xlsx`, `themes.xlsx`, `research_notes.xlsx`)
- generated private country codebooks or effective merged codebooks
- private run configurations that reveal restricted source lists, paths, identifiers or credentials
- CSC project IDs, private scratch paths, Allas credentials, tokens, cookies, API keys or authenticated URLs

Public code may contain algorithms, schemas, generic methodology prompts, synthetic tests and public election/language normalization aids. Generated outputs are written below `LACLAUGPT_DATA_DIR`, which must point outside the repository.

## Public + private codebook layering

The public methodology layer is:

```text
codebooks/public/ep24_fi_pl_v2.yaml
```

It contains only privacy-safe material: evidence rules, multimodal safeguards, Finnish/Polish language notes, public party/coalition aliases, and Laclau/Palonen operationalization rules.

The private repository compiles the three controlled human workbooks into country JSON resources. At runtime the public adapter imports the private entities/themes/notes and merges them with the public methodology layer:

```bash
laclaugpt-ep24 merge-codebooks \
  --public codebooks/public/ep24_fi_pl_v2.yaml \
  --private "$LACLAUGPT_DATA_DIR/ep24/private_codebooks/ep24_fi.json" \
  --output "$LACLAUGPT_DATA_DIR/ep24/effective_codebooks/ep24_fi_effective.json"
```

The same applies to `ep24_pl.json`. The effective file is itself private research material and must remain under the runtime data root.

Human workbook mappings normalize mentions and provide research context. They are **not** proof that a theme, signifier, antagonism or populist articulation occurs in a source item.

## Versioned EP24 prompts

The reprocessing-specific scientific prompts are public and versioned:

- `ep24.frame_analysis:v1`
- `ep24.translation:v1`
- `ep24.summary_analysis:v1`
- `ep24.laclau_analysis:v1`

They preserve useful tasks from the historical multimodal pipeline while changing the epistemic defaults. The old frame prompt could turn neutral visual features such as close-ups or colour schemes into political interpretations. The new prompt requires literal description first and prohibits inferring ideology, candidate status, importance, sentiment or populism from appearance/composition alone. The old summary/populism flow could also complete a plausible `people versus elite` story even when no frontier was stated; the new prompt treats `not_evidenced` and abstention as valid results.

## Finnish and Polish language handling

Original-language evidence is authoritative. English translation is stored beside it as an analytical aid.

For Finnish:

- preserve inflected surface forms while resolving them to canonical entities/themes
- account for compounds, colloquial speech, dialect, youth/meme language and code-switching
- preserve party abbreviations such as Kok., Kesk., Vas., Vihr., RKP/SFP, SDP, PS and KD during NER
- detect Swedish segments instead of assuming all Finland material is Finnish
- do not normalize intentionally absurd or memetic language into a serious political claim

For Polish:

- resolve case/gender-inflected proper names without losing the original surface form
- preserve Polish diacritics in preferred labels
- protect abbreviations such as PiS, KO and PSL before translation
- distinguish `Lewica`/`Nowa Lewica` as an entity from generic `lewica` (the political left) by context
- distinguish `Trzecia Droga` as a coalition name from generic “third way” language
- treat rapid rally speech, chants, repeated slogans and names as ASR-risk spans and corroborate with OCR/metadata where possible

Quoted/reported speech must remain attributed to the quoted speaker rather than automatically to the uploader or narrator.

## Target reprocessing flow

The reprocessing contract combines the useful historical EP24 stages with the current canonical pipeline:

```text
CSC Allas source video/object reference
  -> stage + checksum/identity validation
  -> media preprocessing / duration / deterministic frame plan
  -> ASR in original language with timestamped segments
  -> translation/gloss with difficult-language and uncertainty notes
  -> legacy-compatible 30-second frame anchors + optional scene/key frames
  -> per-frame OCR
  -> evidence-first literal frame analysis
  -> multimodal evidence bundle (metadata + ASR + OCR + frames)
  -> source-linked political summary
  -> entity/theme normalization using public + private codebooks
  -> canonical Laclau/Mouffe/Palonen pre-analysis
  -> optional additional current plugins (NER/topics/embeddings/classification/RAG etc.)
  -> canonical postprocessing and human-readable summary
  -> durable database/object-store persistence
  -> frequent CSV checkpoints
  -> combined legacy + canonical EP24 dashboard dataframe
```

Every expensive stage should be idempotent/resumable and every derived claim should retain evidence/provenance references. Intermediate ASR, translations, OCR and frame analyses are first-class outputs rather than temporary prompt material.

## Laclau/Palonen rules used for EP24

The current LaclauGPT paper is the methodological source of truth even though EP24 concerns electoral politics rather than AI. In particular:

- start with claims, signifiers, relations, demands, subjects and affects rather than fixed ideological labels
- co-occurrence is not articulation
- negative sentiment/criticism is not automatically antagonism
- a social group mention is not automatically a collective political subject
- nodal points require evidence of organizing relations within the discourse
- floating signifiers normally require comparison across competing articulations and are therefore corpus-level candidates
- empty signifiers require evidence that the signifier represents a wider equivalential chain/project; ambiguity or slogan status is insufficient
- Formula of Populism fields are populated only when Us, Frontier, elements/relations and affects are supported; “no supported populist articulation” is a valid result

The model performs theory-guided pre-analysis. Human researchers remain responsible for acceptance, rejection and revision.

## Historical field compatibility

The old Finland/Poland dashboard dataframes contain a large stable column contract, including:

- raw/source metadata
- Whisper transcript/language/translation
- `ocr_1..ocr_6`
- `frame_1..frame_6`
- `summary_analysis`
- entities/topics/sentiment
- political themes
- Formula-of-Populism fields
- LDA variants
- ManifestoBERTa predictions/probabilities
- corrected/original/corresponding date fields
- old/new IDs and filenames
- spaCy entities and `us`/`them`

`laclaugpt_data_analysis.ep24_reprocessing` preserves every historical column when present and backfills only deterministic values from the canonical record. It then appends:

- `canonical_schema_version`
- `human_summary`
- `human_readable_markdown`
- full `canonical_json`
- `intermediate_json`
- `analysis_json`
- `evidence_json`
- codebook/model-run provenance
- uncertainty and abstentions
- review state

This lets legacy dashboards continue to consume their old fields while new dashboards can expose the richer canonical analysis.

Example export:

```bash
laclaugpt-ep24 export-dashboard \
  --records "$LACLAUGPT_DATA_DIR/ep24/canonical/finland.jsonl" \
  --output "$LACLAUGPT_DATA_DIR/ep24/csv/ep24_finland_reprocessed.csv"
```

## Private runtime layout

A recommended runtime structure is:

```text
$LACLAUGPT_DATA_DIR/
  ep24/
    csv/
      finland_sample20.csv
      poland_sample20.csv
      ep24_finland.csv
      ep24_poland.csv
    private_codebooks/
      ep24_fi.json
      ep24_pl.json
    effective_codebooks/
      ep24_fi_effective.json
      ep24_pl_effective.json
    run_configs/
      arena_ep24_finland_pilot.yaml
      arena_ep24_poland_pilot.yaml
    canonical/
    videos/
    annotations/
    human_reports/
    reviews/
    tmp/
```

## Current compatibility bridge

The historical end-to-end media driver still imports restricted project modules and human-codebook support. Until all concrete ASR/OCR/vision/media adapters are fully disentangled, keep that project driver private and provide it at runtime:

```bash
export LACLAUGPT_DATA_DIR=/private/runtime/root
export EP24_PRIVATE_REPO_ROOT=/path/to/LaclauGPT-Discourse-Analysis-Private
export EP24_PIPELINE_SCRIPT="$EP24_PRIVATE_REPO_ROOT/ep24_mm_pipeline.py"
```

`scripts/ep24/run_country_reprocess.sh` now creates the effective public+private codebook before invoking the restricted driver and exports the four versioned EP24 prompt IDs. If the driver writes canonical JSONL, the script automatically emits the combined dashboard CSV.

## Roihu environment

The batch harness follows the current Roihu pattern:

- GH200 GPU allocation
- `gcc/14.3.0`, `python-pytorch/2.13`, and `ffmpeg`
- ARM64 virtual environment created on `roihu-gpu.csc.fi`
- local Ollama only, with cloud fallback disabled
- job-specific Ollama port
- configurable analysis and translation models
- private human country codebook required

Machine- and project-specific values are supplied at submission/runtime rather than committed.

Example:

```bash
cd /path/to/LaclauGPT-Data-Analysis
export LACLAUGPT_DATA_DIR=/scratch/<project>/<user>/laclaugpt-data
export EP24_PRIVATE_REPO_ROOT=/scratch/<project>/LaclauGPT-Discourse-Analysis-Private
export EP24_PIPELINE_SCRIPT="$EP24_PRIVATE_REPO_ROOT/ep24_mm_pipeline.py"
sbatch --account=<CSC_PROJECT> --export=ALL scripts/ep24/ep24_roihu_reprocess.sbatch
```

## Remaining migration work

The following generic algorithms are safe to continue moving from restricted/legacy code into this repository when backed by synthetic tests:

1. concrete Whisper/faster-whisper adapter with timestamped segments
2. concrete OCR adapter and language-aware OCR selection
3. concrete Ollama vision adapter using `ep24.frame_analysis:v1`
4. scene-change + legacy-anchor frame extraction
5. canonical media-manifest adapter from the historical EP24 rows
6. direct record-store to combined-dashboard exporter

The migration rule remains simple: algorithms, schemas, prompts and public normalization may be public; real research rows, identifiers, private workbook-derived mappings, credentials and project-local configuration may not.
