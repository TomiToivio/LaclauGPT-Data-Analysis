# EP24 legacy prompt archive and compatibility contract

This document archives the prompt contracts recovered from `TomiToivio/LaclauGPT-Multimodal-Analysis` at legacy commit `eb40dda0413ac68b1c65a2bd6253d22632015cbe`. These prompts are historical scientific-method inputs for EP24. The EP24 re-analysis must retain their analytical coverage while using the improved staged/evidence-first pipeline.

Source files:

- `puhti_frame.py`
- `puhti_summary.py`
- `puhti_postprocess.py`
- `puhti_populism.py`

The active compatibility-preserving replacements are:

- `ep24.frame_analysis:v2`
- `ep24.summary_analysis:v2`
- `ep24.laclau_analysis:v2`
- `ep24.translation:v1`

The v1 EP24 prompts remain immutable for reproducibility.

## Legacy frame system prompt (`puhti_frame.py`)

> You are a political scientist analyzing a single frame from a TikTok video concerning the 2024 European Parliament elections.
>
> For each category, provide a thorough, objective analysis, focusing on details that may reveal framing techniques, contextual cues, and visual emphasis in the video content.
>
> 1. **Framing**: identify shot types such as close-ups and wide-angle shots; note framing choices highlighting objects or gestures; observe split-screen layouts.
> 2. **Visual Elements**: describe background context such as public squares, government buildings, natural landscapes, vehicles, campaign events, flags and office interiors; specify outdoors/indoors/studio.
> 3. **Activity**: identify visible activity such as speeches, demonstrations or voter participation.
> 4. **Color Scheme**: analyse the palette and possible European/national context or mood.
> 5. **Objects**: note campaign posters, ballots, microphones, flags, signs, podiums, digital graphics and minor items such as mugs, on-screen text, emojis or image-in-image features.
> 6. **Subjects**: identify visible individuals/groups such as politicians, influencers, campaigners, voters, activists or citizens; note pets.
> 7. **Screen Recording Indicators**: observe TV, YouTube, social media or people filming another screen.

Legacy frame user task:

> Analyze the provided video frame based on the categories outlined in the system prompt. Provide a detailed description of the visual elements, activities, and subjects present in the frame. Focus on how these elements contribute to the overall message or framing of the video content.

The v2 prompt preserves every category above, but turns interpretive claims from colour/framing/appearance into evidence-gated candidates rather than automatic findings.

## Legacy summary prompt (`puhti_summary.py`)

The user prompt supplied three evidence groups:

1. multimodal Llama + EasyOCR frame analysis (1–6 frames),
2. TikTok metadata,
3. Whisper transcript.

The task was to use all three to conduct a comprehensive political analysis.

The system prompt required these nine categories:

1. **Narrative Construction**: reconstruct sequence of events/actions and identify what shapes the narrative.
2. **Political Classification**: political vs non-political; if political, subtype such as candidate personal video, campaign speech, protest, political meme, election advertisement or media coverage.
3. **Difficult Language**: find difficult-to-translate, ambiguous or politically charged words/phrases and explain them.
4. **Key Political Topics**: identify major topics and explain presentation.
5. **Political Entities**: list politicians, parties, movements and organisations and describe their roles.
6. **Sentiment Analysis**: positive/negative/neutral sentiment, target and justification.
7. **Political Populism**: use Ernesto Laclau to identify empty signifiers, chains of equivalence and the people-versus-elite narrative.
8. **Social Contract**: analyse implied/explicit agreements, obligations or expectations between citizens and political authorities and their relation to political behaviour.
9. **Grievance Politics**: identify grievances/perceived injustices and discuss their possible relation to mobilisation or conflict.

`ep24.summary_analysis:v2` explicitly retains all nine categories, plus evidence synopsis, multimodal contradiction/uncertainty handling, claims/demands/promises/futures and a researcher-readable synthesis. The Laclau content at summary stage is intentionally preliminary; the dedicated discourse stage performs the deep analysis.

## Legacy structured postprocess prompt (`puhti_postprocess.py`)

Historical postprocessing instructed the model to extract from the generated analysis:

1. political topics, merging obvious duplicates/synonyms;
2. political entities, merging obvious duplicates/synonyms;
3. sentiment targets classified as positive, neutral or negative.

It required exactly the JSON keys `topics`, `entities`, `positive`, `neutral`, `negative`, each as an array of strings, with empty arrays for absent categories.

The current canonical pipeline preserves the substance of this extraction in structured `SummaryProposal`/canonical fields instead of making the postprocess CSV extraction the only durable representation. Legacy dashboard export remains a compatibility layer.

## Legacy Laclau/Palonen populism prompt (`puhti_populism.py`)

The historical prompt described the model as a political scientist re-analysing an existing EP24 political-video analysis through Ernesto Laclau and Emilia Palonen. Its substantive contract was:

- construct **Us / the people** from demands, values or identities;
- identify **chains of equivalence** among demands;
- identify positive affects supporting Us;
- construct the **Frontier / Them** from elites, institutions or symbolic enemies;
- identify equivalential links on the frontier side;
- identify negative affects aimed at the frontier;
- analyse chains of equivalence, antagonism/frontier, empty signifiers, affective polarisation and multimodal cues;
- explicitly restate Palonen's formula:

```text
Populism = Us (Demand ≡ Demand ≡ …) [Positive Affects]
         + Frontier (Other ≡ Other ≡ …) [Negative Affects]
```

The machine-readable result used a `FormulaOfPopulism` object with:

```text
populism_analysis: str
populism_us: list[PopulismElement]
populism_frontier: list[PopulismElement]

PopulismElement:
  populism_element: str
  populism_affect: str
```

The legacy prompt also required simplified/generalised symbolic labels, grouping synonyms, single-word affect labels, valid structured output and support from the preceding analysis.

`ep24.laclau_analysis:v2` keeps these obligations but adds the current safeguards: co-occurrence is not articulation; criticism is not automatically antagonism; empty signifiers require a wider equivalential project; a Formula of Populism is populated only when Us, demands/equivalence, frontier and affects are evidenced; corpus-level claims are marked as requiring corpus validation; `no supported populist articulation` is a valid result.

## EP24 re-analysis invariant

For EP24 Finland/Poland re-analysis, the old and new pipeline are **additive**:

```text
legacy analytical coverage
  + original-language ASR / translation safeguards
  + 30-second legacy frame anchors (plus optional newer key/scene frames)
  + OCR and literal visual observation
  + evidence/provenance/uncertainty
  + private researcher codebook grounding
  + structured summary/postprocess fields
  + dedicated Laclau/Mouffe/Palonen stage
  + current optional NLP/social-data-science plugins
  + canonical persistence and legacy-compatible dashboard export
```

Do not simplify EP24 re-analysis by replacing the historical categories with a generic prompt. New stages may refine, split or evidence-gate old tasks, but they must not silently remove them.