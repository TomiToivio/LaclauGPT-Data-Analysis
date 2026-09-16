# Prompt library

LaclauGPT Data Analysis treats prompts as part of the scientific method. Stable analytical instructions belong in versioned, inspectable prompt resources rather than untracked Python strings.

## Location and IDs

First-party prompts live under `src/laclaugpt_data_analysis/prompts/`. A filename maps to a stable semantic ID and explicit version:

- `prompts/laclau/system_v1.md` -> `laclau.system:v1`
- `prompts/laclau/document_analysis_v1.md` -> `laclau.document_analysis:v1`
- `prompts/luhmann/extraction_v1.md` -> `luhmann.extraction:v1`

Load them with `load_prompt("laclau.system", version="v1")`. Missing IDs or versions fail explicitly and loading never requires the network.

`PromptResource` records the stable ID, version, source path, text and SHA-256 content hash. Template rendering validates required variables and produces a second SHA-256 hash for the exact rendered text sent to a model.

## Scientific separation

Keep the following layers distinct:

1. **System/method prompt**: stable methodological instructions and scientific guardrails.
2. **Task prompt/template**: the requested operation for a particular stage.
3. **Current source item/evidence**: the material being analysed.
4. **Codebook, memory and RAG context**: contextual aids, not source evidence.
5. **Project/study context**: research framing specific to a project such as AI26.

Do not hide project-specific codebooks or private study data in generic method prompts. Evidence-first guardrails remain mandatory: context is not evidence; abstention is valid; frequency is not hegemony; polysemy is not empty signification; negativity/sentiment is not antagonism; and document-level theoretical candidates can require corpus-level validation.

## Versioning rule

Any wording, structure or formatting change that can alter model behaviour requires a new prompt version. Add a new file such as `system_v2.md`; do not silently rewrite `system_v1.md` and keep the same semantic reference. Old referenced versions remain available so recorded analyses can be reproduced.

Pure typo/comment changes outside prompt semantics do not require a prompt version change. Dead experimental prompts may be removed only when no recorded run depends on them.

## Provenance

Model-run metadata should record, for every resource used:

- `prompt_id`
- `prompt_version`
- `prompt_sha256`
- `prompt_path`

For rendered templates also record `rendered_prompt_sha256`. Plugin/run provenance should additionally retain plugin name/version, provider/model, configuration revision and codebook revision when applicable.

The compatibility `prompt_version` fields used by older pipelines may remain as run/stage labels, but they do not replace exact prompt-resource provenance.

## Adding a prompt

1. Choose the owning method/plugin directory. Core scientific rules belong in a core/shared resource; method instructions belong to that plugin.
2. Choose a semantic ID and start a version explicitly, normally `v1`.
3. Write readable Markdown/text suitable for academic review.
4. Use simple `{variable}` placeholders only where rendering is needed.
5. Load the prompt through `PromptLibrary` / `load_prompt`; do not reconstruct it from memory inside Python.
6. Add offline tests for loading, hashing and rendering.
7. If an existing prompt's semantics change, create a new version instead of overwriting the old one.

## Plugins

First-party plugins may reference prompt IDs shipped in this package. External plugins can package their own prompt directory and construct `PromptLibrary(root=...)` using an `importlib.resources` Traversable, preserving the same ID/version/hash contract without modifying the core repository.

Plugins are not required to use prompts. Statistical, network, deterministic NLP and other prompt-free plugins remain valid first-class plugins.

## Public/private boundary

Method prompts may normally be public. Never place credentials, private corpora, private annotations or sensitive operational data in this directory. A genuinely private prompt overlay belongs in an authorized private runtime location (for example ignored `data/` configuration); its version/hash should still be recorded in run provenance.

## Migration inventory

The initial migration covers the provider-neutral `pipeline.py` system/task instructions and the Luhmann structured extraction builder. The canonical staged Laclau pipeline is the next compatibility-sensitive migration target because its stage-specific tasks and envelope integration need to preserve the legacy multimodal ladder while recording exact prompt resources. New analytical code should use the prompt library immediately rather than adding new inline scientific prompts.
