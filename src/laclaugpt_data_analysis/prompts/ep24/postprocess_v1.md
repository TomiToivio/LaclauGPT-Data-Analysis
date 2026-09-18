Extract a structured summary from the supplied prior political-video analysis.

Current task:
- extract political topics;
- extract political entities;
- extract sentiment targets and classify each as positive, neutral, or negative.

Rules:
- Merge obvious duplicate/synonymous topic or entity labels when this does not erase a meaningful distinction.
- Preserve only claims supported by the supplied prior analysis.
- Do not add background knowledge, project assumptions, codebook-only entities, or inferred sentiment targets.
- If a category has no supported values, return an empty list.
- Output only a valid JSON object with exactly these keys:
  - `topics`
  - `entities`
  - `positive`
  - `neutral`
  - `negative`
- Every value MUST be a JSON array of strings.
- Do not include markdown fences, commentary, provenance fields, or extra keys.

Input analysis:

{source_analysis}
