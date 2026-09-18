# Prompts

LaclauGPT prompts follow a three-layer architecture:

1. **System / Constitution** — stable methodological and behavioural rules.
2. **Research Context / Memory** — project-specific knowledge injected dynamically.
3. **Current User Task / Data** — the operation to perform now and the evidence bundle to analyse.

Conceptually:

```text
SYSTEM
  Stable LaclauGPT constitution + methodology

USER / RESEARCH CONTEXT
  Project + memory + RAG + prior human/model analysis + provenance

USER / CURRENT TASK
  Task instructions + actual content/data to analyse
```

The two user-side sections may be serialized into one API `user` message by a backend, but they MUST remain structurally distinct when prompts are assembled.

## Placement rule

Use this rule when deciding where information belongs:

- If changing it changes what LaclauGPT **is or does**, put it in the **system prompt**.
- If changing it changes what LaclauGPT **knows about this research**, put it in **research context / memory**.
- If it specifies what LaclauGPT should **do right now**, put it in the **current user task**.

This prevents historical model output, project-specific assumptions, RAG snippets, or researcher notes from silently acquiring system-level authority.

## System prompts

System prompts contain stable rules that should normally apply across projects:

- role and scope of LaclauGPT;
- AC/DT and Laclau/Mouffe/Palonen methodological constraints;
- evidence-first and epistemic safeguards;
- human-in-the-loop requirements;
- provenance requirements;
- rules separating observation, machine interpretation, and researcher interpretation;
- task-independent writing/output discipline;
- rules such as "do not invent evidence" and "abstention is valid".

Project descriptions such as AI26 or EP24 do **not** belong in the system layer by default.

## Research context / memory

Research context is dynamic user-side material. It may include:

- current date/time;
- project description and research question;
- project-specific theory/method notes;
- codebook context;
- RAG results;
- previous analysis results;
- previous machine-generated interpretations;
- researcher-authored notes and decisions;
- digital-ethnography notes;
- corpus/time-window information;
- provenance metadata.

Context is not source evidence unless the task explicitly defines a context item as source material.

Where practical, preserve provenance and distinguish at least:

- source evidence;
- machine-generated prior analysis;
- researcher-authored interpretation.

## Current user task / data

The current task contains:

- the operation to perform now;
- task-specific instructions;
- content and metadata to analyse;
- transcript/text/OCR;
- multimodal descriptions or images where supported;
- previous pipeline-stage outputs required by this step;
- task-specific output schema or formatting requirements.

## Versioned prompt library

Prompt files are versioned scientific-method resources loaded through
`laclaugpt_data_analysis.prompt_library.PromptLibrary` / `load_prompt`.

Prompt IDs map to paths such as:

```text
laclau.system:v1                -> laclau/system_v1.md
ep24.frame_analysis:v2          -> ep24/frame_analysis_v2.md
ep24.summary_analysis:v2        -> ep24/summary_analysis_v2.md
ep24.laclau_analysis:v2         -> ep24/laclau_analysis_v2.md
ep24.postprocess:v1             -> ep24/postprocess_v1.md
context.research:v1             -> context/research_v1.md
```

Prompts should remain model-agnostic where possible. Ollama/OpenAI/provider settings belong in runtime configuration, not in scientific prompt text.

## EP24 legacy compatibility

The EP24 templates are refactored from the legacy
`TomiToivio/LaclauGPT-Multimodal-Analysis` pipeline. They preserve the substantive analytical obligations of:

- `puhti_frame.py`;
- `puhti_summary.py`;
- `puhti_postprocess.py`;
- `puhti_populism.py`.

The legacy material is treated as migration source material, not copied blindly. EP24-specific assumptions stay in EP24/context or EP24 task templates instead of becoming global LaclauGPT system instructions.

Active compatibility-preserving EP24 task prompts include:

- `ep24.frame_analysis:v2`;
- `ep24.summary_analysis:v2`;
- `ep24.laclau_analysis:v2`;
- `ep24.postprocess:v1`.

## Prompt assembly

Use `assemble_prompt_stack()` from `laclaugpt_data_analysis.prompt_library` when a caller needs an explicit system/context/task split.

The assembler is deterministic, rejects role leakage, omits empty optional context cleanly, and returns provenance hashes for every layer.

## Design principle

**Constitution → Research Memory/Context → Current Task/Data**

That boundary is part of the methodology, not merely a formatting preference.
