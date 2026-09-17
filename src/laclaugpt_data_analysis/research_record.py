"""Four-layer researcher compatibility helpers.

The canonical nested record remains authoritative. These helpers retain lossless
intermediate stage outputs, generate the EP24-era wide dataframe aliases researchers
expect, and create a deterministic human-readable report that includes the complete
structured analysis.
"""
from __future__ import annotations

import json
from typing import Any

from .canonical import CanonicalRecord, HumanReadableSection

LEGACY_RESEARCH_COLUMNS = (
    "country", "author_username", "account_type", "source_type", "source_recording",
    "video_filename", "video_file", "frames", "whisper_transcript", "whisper_language",
    "whisper_translated", "ocr_1", "ocr_2", "ocr_3", "ocr_4", "ocr_5", "ocr_6",
    "frame_1", "frame_2", "frame_3", "frame_4", "frame_5", "frame_6",
    "summary_analysis", "entities", "topics", "spacy_entities", "positive", "neutral",
    "negative", "us_and_them", "us", "them", "social_contract", "social_contract_topics",
    "NER_entities", "NER_politicians", "NER_political_parties", "political_themes",
    "formula_of_populism_analysis", "formula_of_populism_us", "formula_of_populism_frontier",
    "recording_date", "day_number", "video_id", "sequence_number", "recording_datetime",
    "profile_name", "allas_filename", "lda_topic", "lda_minor_topics", "lda_topic_words",
    "political_preference", "manifestoberta_predicted_class", "manifestoberta_probabilities",
    "corrected_date", "original_date", "corresponding_date", "split_number", "new_entity",
    "new_theme", "video_duration", "new_id", "old_id", "puhti_filename",
    "raw_ref", "raw_payload_json", "human_readable_summary", "human_readable_markdown",
)


def _merge_dict_rows(existing: list[dict[str, Any]], rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result = [dict(item) for item in existing]
    seen = {str(item.get(key) or "") for item in result}
    for row in rows:
        identity = str(row.get(key) or "")
        if identity and identity in seen:
            continue
        result.append(row)
        if identity:
            seen.add(identity)
    return result


def sync_intermediate_from_content(record: CanonicalRecord) -> None:
    """Mirror source-derived stage results into the explicit intermediate history."""
    asr = [item.model_dump(mode="json") for item in record.content.transcripts]
    ocr = [item.model_dump(mode="json") for item in record.content.ocr]
    frames = [item.model_dump(mode="json") for item in record.content.frames]
    frame_analysis = [
        {
            "id": item.id,
            "timestamp_seconds": item.timestamp_seconds,
            "description": item.description,
            "provenance_id": item.provenance_id,
        }
        for item in record.content.frames
        if item.description
    ]
    translations = [
        {
            "id": item.id,
            "text": item.translated_text,
            "language": item.language,
            "provider": item.provider,
            "provenance_id": item.provenance_id,
        }
        for item in record.content.transcripts
        if item.translated_text
    ]
    if record.content.translated_text:
        translations.append(
            {
                "id": "content_translation",
                "text": record.content.translated_text,
                "language": record.content.language,
            }
        )
    record.intermediate.asr = _merge_dict_rows(record.intermediate.asr, asr, "id")
    record.intermediate.ocr = _merge_dict_rows(record.intermediate.ocr, ocr, "id")
    record.intermediate.frames = _merge_dict_rows(record.intermediate.frames, frames, "id")
    record.intermediate.frame_analysis = _merge_dict_rows(
        record.intermediate.frame_analysis, frame_analysis, "id"
    )
    record.intermediate.translations = _merge_dict_rows(
        record.intermediate.translations, translations, "id"
    )


def _labels(values: list[Any]) -> list[str]:
    labels: list[str] = []
    for value in values:
        if hasattr(value, "label"):
            text = str(value.label)
        elif hasattr(value, "canonical_label"):
            text = str(value.canonical_label)
        elif isinstance(value, dict):
            text = str(value.get("label") or value.get("canonical_label") or value.get("name") or "")
        else:
            text = str(value)
        if text.strip():
            labels.append(text.strip())
    return labels


def _semicolon(values: list[str]) -> str:
    return "; ".join(value for value in values if value)


def _relations(values: list[Any]) -> str:
    return _semicolon(
        [f"{item.source_ref} -[{item.relation_type}]-> {item.target_ref}" for item in values]
    )


def _chains(values: list[Any]) -> str:
    return _semicolon([" ≡ ".join(item.member_refs) for item in values if item.member_refs])


def _first_native(record: CanonicalRecord, *names: str) -> str:
    for name in names:
        value = record.source_native_ids.get(name)
        if value:
            return str(value)
    return ""


def legacy_projection(record: CanonicalRecord) -> dict[str, Any]:
    """Return the stable EP24-style wide row aliases without losing imported extras."""
    sync_intermediate_from_content(record)
    legacy: dict[str, Any] = dict(record.legacy)
    transcripts = record.content.transcripts
    transcript = "\n".join(item.text for item in transcripts if item.text)
    language = next((item.language for item in transcripts if item.language), "") or ""
    translated = "\n".join(
        item.translated_text for item in transcripts if item.translated_text
    ) or (record.content.translated_text or "")

    ocr_values = [str(item.get("text") or "") for item in record.intermediate.ocr]
    frame_values = [
        str(item.get("description") or item.get("text") or "")
        for item in record.intermediate.frame_analysis
    ]
    entities = _labels(record.analysis.entities)
    topics = _labels(record.analysis.topics)
    sentiments = _labels(record.analysis.sentiments)
    positive = [label for label in sentiments if "positive" in label.casefold()]
    neutral = [label for label in sentiments if "neutral" in label.casefold()]
    negative = [label for label in sentiments if "negative" in label.casefold()]
    formula = record.analysis.formula_of_populism or {}
    classifications = {item.task: item.label for item in record.analysis.classifications}
    object_ref = next(
        (item.object_ref for item in record.content.media_references if item.object_ref), None
    )
    native_video = _first_native(record, "videoId", "video_id", "video_filename")
    new_id = _first_native(record, "new_id") or native_video
    created = record.source.created_at.isoformat() if record.source.created_at else ""
    raw_payload = record.raw_capture.payload

    derived: dict[str, Any] = {
        "country": record.source.country,
        "author_username": record.source.author,
        "source_type": record.source.source_type or record.source.platform,
        "video_filename": _first_native(record, "video_filename"),
        "video_file": object_ref or "",
        "frames": json.dumps(record.intermediate.frames, ensure_ascii=False, sort_keys=True),
        "whisper_transcript": transcript,
        "whisper_language": language,
        "whisper_translated": translated,
        "summary_analysis": record.analysis.summary or "",
        "entities": _semicolon(entities),
        "topics": _semicolon(topics),
        "positive": _semicolon(positive),
        "neutral": _semicolon(neutral),
        "negative": _semicolon(negative),
        "us": _semicolon(_labels(record.analysis.us)),
        "them": _semicolon(_labels(record.analysis.them)),
        "formula_of_populism_analysis": (
            json.dumps(formula, ensure_ascii=False, sort_keys=True) if formula else ""
        ),
        "formula_of_populism_us": str(formula.get("us") or ""),
        "formula_of_populism_frontier": str(formula.get("frontier") or ""),
        "recording_date": created[:10] if created else "",
        "recording_datetime": created,
        "video_id": native_video,
        "allas_filename": object_ref or "",
        "political_preference": str(record.source.raw_metadata.get("political_preference") or ""),
        "manifestoberta_predicted_class": classifications.get("manifestoberta", ""),
        "new_entity": _semicolon(entities),
        "new_theme": _semicolon(_labels(record.analysis.themes) or topics),
        "new_id": new_id,
        "old_id": _first_native(record, "old_id"),
        "raw_ref": record.raw_capture.ref or record.source.raw_ref or "",
        "raw_payload_json": (
            "" if raw_payload is None else json.dumps(raw_payload, ensure_ascii=False, sort_keys=True)
        ),
        "human_readable_summary": record.human_readable.summary,
        "human_readable_markdown": record.human_readable.markdown,
    }
    for index in range(1, 7):
        derived[f"ocr_{index}"] = ocr_values[index - 1] if index <= len(ocr_values) else ""
        derived[f"frame_{index}"] = frame_values[index - 1] if index <= len(frame_values) else ""

    for key, value in derived.items():
        if value not in (None, "", [], {}):
            legacy[key] = value
        else:
            legacy.setdefault(key, value)
    for key in LEGACY_RESEARCH_COLUMNS:
        legacy.setdefault(key, "")
    return legacy


def _stable_generated_at(record: CanonicalRecord) -> str | None:
    if record.human_readable.generated_at:
        return record.human_readable.generated_at
    if record.analysis.completed_at:
        return record.analysis.completed_at.isoformat()
    if record.analysis.started_at:
        return record.analysis.started_at.isoformat()
    if record.provenance:
        return record.provenance[-1].created_at.isoformat()
    return None


def _latest_stage_proposal(record: CanonicalRecord, stage: str) -> dict[str, Any]:
    """Return the latest structured proposal for a named intermediate stage."""
    value = record.intermediate.stage_outputs.get(stage)
    if isinstance(value, list):
        value = value[-1] if value else None
    if not isinstance(value, dict):
        return {}
    proposal = value.get("proposal")
    return dict(proposal) if isinstance(proposal, dict) else {}


def _multimodal_research_sections(record: CanonicalRecord) -> tuple[str, str, str]:
    synthesis = _latest_stage_proposal(record, "multimodal_synthesis")
    castells = _latest_stage_proposal(record, "castells_context")
    if not synthesis and not castells:
        return "", "", ""

    synthesis_parts = [
        str(synthesis.get("narrative") or synthesis.get("summary") or "").strip()
    ]
    relations = [str(item) for item in synthesis.get("cross_modal_relations", []) if str(item)]
    if relations:
        synthesis_parts.append("Cross-modal relations: " + "; ".join(relations))
    synthesis_text = "\n\n".join(part for part in synthesis_parts if part)

    castells_text = ""
    if castells:
        labels = (
            ("Actors / organisations / institutions", "actors_organisations_institutions"),
            ("Networks / relations", "networks_relations"),
            ("Flows", "flows"),
            ("Nodes / hubs / channels", "nodes_hubs_channels"),
            ("Space of places", "space_of_places"),
            ("Space of flows", "space_of_flows"),
            ("Power / access / exclusion", "power_access_exclusion"),
            ("Uncertainty", "uncertainty"),
        )
        rows = []
        for label, key in labels:
            values = [str(item) for item in castells.get(key, []) if str(item)]
            if values:
                rows.append(f"{label}: " + "; ".join(values))
        castells_text = "\n".join(rows)

    cues = [str(item) for item in synthesis.get("later_analysis_cues", []) if str(item)]
    return synthesis_text, castells_text, "\n".join(f"- {cue}" for cue in cues)


def render_human_readable(record: CanonicalRecord) -> HumanReadableSection:
    """Render a deterministic researcher report containing all analysis categories."""
    sync_intermediate_from_content(record)
    transcript = "\n\n".join(item.text for item in record.content.transcripts if item.text)
    ocr = "\n".join(
        str(item.get("text") or "") for item in record.intermediate.ocr if item.get("text")
    )
    frames = "\n".join(
        f"- {item.get('id', 'frame')}: {item.get('description') or item.get('text') or ''}"
        for item in record.intermediate.frame_analysis
    )
    multimodal_synthesis, castells_context, later_analysis_cues = _multimodal_research_sections(record)
    analysis_json = json.dumps(
        record.analysis.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    raw_status = record.raw_capture.ref or (
        "inline raw payload" if record.raw_capture.payload is not None else "raw capture unavailable"
    )
    sections = {
        "source": f"{record.source.platform or record.source.source_type or 'source'} | {record.source.author} | {record.source_url}",
        "raw_capture": str(raw_status),
        "source_text": record.content.text or "",
        "transcript": transcript,
        "ocr": ocr,
        "frame_analysis": frames,
        "multimodal_synthesis": multimodal_synthesis,
        "castells_context": castells_context,
        "later_analysis_cues": later_analysis_cues,
        "analysis_summary": record.analysis.summary or "",
        "entities": _semicolon(_labels(record.analysis.entities)),
        "topics": _semicolon(_labels(record.analysis.topics)),
        "themes": _semicolon(_labels(record.analysis.themes)),
        "formations": _semicolon(_labels(record.analysis.formations)),
        "signifiers": _semicolon(_labels(record.analysis.signifiers)),
        "nodal_points": _semicolon(_labels(record.analysis.nodal_points)),
        "floating_signifiers": _semicolon(_labels(record.analysis.floating_signifiers)),
        "empty_signifier_candidates": _semicolon(_labels(record.analysis.empty_signifier_candidates)),
        "discourses": _semicolon(_labels(record.analysis.discourses)),
        "imaginaries": _semicolon(_labels(record.analysis.imaginaries)),
        "equivalence_chains": _chains(record.analysis.equivalence_chains),
        "difference_chains": _chains(record.analysis.difference_chains),
        "antagonisms": _relations(record.analysis.antagonisms),
        "actor_entity_relations": _relations(record.analysis.actor_entity_relations),
        "us": _semicolon(_labels(record.analysis.us)),
        "them": _semicolon(_labels(record.analysis.them)),
        "frontier": _semicolon(_labels(record.analysis.frontier)),
        "affects": _semicolon(_labels(record.analysis.affects)),
        "sentiments": _semicolon(_labels(record.analysis.sentiments)),
        "stances": _semicolon(_labels(record.analysis.stances)),
        "uncertainty": _semicolon(record.analysis.uncertainty),
        "abstentions": _semicolon(record.analysis.abstentions),
    }
    summary = record.analysis.summary or (record.content.text[:500] if record.content.text else "")
    markdown = (
        "# LaclauGPT researcher report\n\n"
        f"## Source\n{sections['source']}\n\n"
        f"## Raw capture\n{sections['raw_capture']}\n\n"
        f"## Collected text\n{sections['source_text'] or 'n/a'}\n\n"
        f"## Whisper / ASR transcript\n{transcript or 'n/a'}\n\n"
        f"## OCR\n{ocr or 'n/a'}\n\n"
        f"## Frame / multimodal analysis\n{frames or 'n/a'}\n\n"
        f"## Multimodal item synthesis\n{multimodal_synthesis or 'n/a'}\n\n"
        f"## Light Castells sociological context\n{castells_context or 'n/a'}\n\n"
        f"## Later analysis cues\n{later_analysis_cues or 'n/a'}\n\n"
        f"## Analysis summary\n{sections['analysis_summary'] or 'n/a'}\n\n"
        f"## Entities, topics and themes\nEntities: {sections['entities'] or 'n/a'}\n\n"
        f"Topics: {sections['topics'] or 'n/a'}\n\nThemes: {sections['themes'] or 'n/a'}\n\n"
        f"## Sentiment and stance\nSentiment: {sections['sentiments'] or 'n/a'}\n\n"
        f"Stance: {sections['stances'] or 'n/a'}\n\n"
        f"## Signifiers and formations\nFormations: {sections['formations'] or 'n/a'}\n\n"
        f"Signifiers: {sections['signifiers'] or 'n/a'}\n\n"
        f"Nodal points: {sections['nodal_points'] or 'n/a'}\n\n"
        f"Floating signifiers: {sections['floating_signifiers'] or 'n/a'}\n\n"
        f"Empty-signifier candidates: {sections['empty_signifier_candidates'] or 'n/a'}\n\n"
        f"Discourses: {sections['discourses'] or 'n/a'}\n\n"
        f"Imaginaries: {sections['imaginaries'] or 'n/a'}\n\n"
        f"## Relational discourse structure\nEquivalence chains: {sections['equivalence_chains'] or 'n/a'}\n\n"
        f"Difference chains: {sections['difference_chains'] or 'n/a'}\n\n"
        f"Antagonisms: {sections['antagonisms'] or 'n/a'}\n\n"
        f"Actor/entity relations: {sections['actor_entity_relations'] or 'n/a'}\n\n"
        f"## Us / them / frontier / affects\nUs: {sections['us'] or 'n/a'}\n\n"
        f"Them: {sections['them'] or 'n/a'}\n\n"
        f"Frontier: {sections['frontier'] or 'n/a'}\n\n"
        f"Affects: {sections['affects'] or 'n/a'}\n\n"
        f"## Uncertainty / abstentions\nUncertainty: {sections['uncertainty'] or 'n/a'}\n\n"
        f"Abstentions: {sections['abstentions'] or 'n/a'}\n\n"
        "## Complete structured analysis\n```json\n"
        f"{analysis_json}\n```\n"
    )
    return HumanReadableSection(
        summary=summary,
        markdown=markdown,
        generated_at=_stable_generated_at(record),
        generator="laclaugpt-data-analysis/research_record.py",
        sections=sections,
    )


def ensure_research_layers(record: CanonicalRecord) -> CanonicalRecord:
    """Synchronize stage history, report and legacy projection before persistence/export."""
    sync_intermediate_from_content(record)
    record.human_readable = render_human_readable(record)
    record.legacy = legacy_projection(record)
    record.legacy["human_readable_summary"] = record.human_readable.summary
    record.legacy["human_readable_markdown"] = record.human_readable.markdown
    return record
