# Legacy discourse-analysis parity

Issue #11 completes the backend-neutral migration of useful analytical fields from the earlier LaclauGPT discourse-analysis workflow into the canonical Data Analysis record.

## Canonical field map

| Legacy / conceptual field | Canonical home | Notes |
|---|---|---|
| entities / actors | `analysis.entities`, `analysis.entity_mentions` | canonical entities and source mentions remain distinct |
| topics | `analysis.topics`, `analysis.topic_assignments` | conventional/statistical topic methods may populate assignments |
| political themes | `analysis.themes` | evidence-linked LLM/researcher theme candidates |
| sentiment | `analysis.sentiments` | explicit evidence-linked observation; not affective investment |
| stance | `analysis.stances` | explicit evidence-linked stance toward a target/claim when supported |
| signifiers | `analysis.signifiers` | general signifier candidates |
| nodal points | `analysis.nodal_points` | provisional document-level analytical assignments |
| floating signifiers | `analysis.floating_signifiers` | always provisional at document level; corpus validation required |
| empty signifiers | `analysis.empty_signifier_candidates` | candidates only; polysemy/vagueness is insufficient |
| equivalence chains | `analysis.equivalence_chains` | explicit ordered chains; never inferred from co-occurrence alone |
| difference chains | `analysis.difference_chains` | explicit ordered chains |
| antagonisms / oppositional structure | `analysis.antagonisms` | evidence-linked relations; negative sentiment alone is insufficient |
| actor/entity relations | `analysis.actor_entity_relations` | descriptive/evidence-linked actor-to-entity relations |
| generic discourse relations | `analysis.relations` | storage-neutral relation surface for graph projection |
| formations | `analysis.formations` | candidates pending corpus validation |
| discourses | `analysis.discourses` | candidate discourse objects |
| imaginaries | `analysis.imaginaries` | document-level candidates, not automatically stabilized imaginaries |
| frame analysis | `intermediate.frame_analysis` plus `content.frames` | optional; text-only records remain valid |
| OCR | `intermediate.ocr` plus `content.ocr` | optional and provenance-linked |
| ASR / Whisper | `intermediate.asr` plus `content.transcripts` | optional and provenance-linked |
| uncertainty / abstention | `analysis.uncertainty`, `analysis.abstentions` | retained explicitly |
| researcher-readable synthesis | `human_readable` | stable Markdown plus named sections; JSON remains authoritative |

## Provider-neutral output

`pipeline.AnalysisProposal` exposes these fields directly. Theory-facing values use evidence-linked candidate objects or relations instead of hiding sentiment/stance/antagonism inside arbitrary classification keys. Structured output is Pydantic-validated before canonical records are mutated.

Codebooks and retrieved context are guidance, not source evidence. Project/country-specific codebooks stay outside the public repository.

## Review and provenance

LLM-produced analytical objects default to `PROVISIONAL`. Evidence excerpts become canonical `Evidence` objects linked by ID. Model/provider/prompt provenance is retained at the analysis run and copied onto explicit analytical objects, relations and relation chains.

Floating signifiers, empty-signifier candidates and formations carry the existing corpus-validation boundary. A document-level proposal is never promoted to a corpus-level finding merely because it serializes successfully.

## Human-readable output

`research_record.render_human_readable()` exposes named sections for topics/themes, sentiment/stance, floating and empty-signifier candidates, equivalence/difference chains, antagonisms and actor/entity relations. The report still embeds the complete structured JSON at the end for auditability, but researchers do not need to read JSON to inspect the major fields.

## Temporal and grouped aggregation

Temporal/grouped results are downstream corpus products rather than fields on a single document. Use `reporting.build_daily_report(records, report_date=..., filters=...)` for deterministic grouped reporting by supported dimensions such as signifier, author, formation, platform and country. More advanced temporal graph/statistical aggregation should operate over canonical records and preserve source/evidence links rather than writing corpus conclusions back into individual source records.

This separation avoids treating document frequency as hegemony or corpus recurrence as proof of a Laclaudian role.

## Deprecated patterns

The following legacy patterns are intentionally not canonicalized:

- arbitrary sentiment/stance hidden only in `classifications`;
- treating every opposition or negative statement as antagonism;
- treating frequent/polysemous terms as empty or hegemonic signifiers;
- manufacturing frame/OCR/ASR placeholders for text-only sources;
- deriving equivalence chains automatically from co-occurrence or semantic similarity.
