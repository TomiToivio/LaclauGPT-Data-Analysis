"""spaCy backend ported from LaclauGPT-Discourse-Analysis.

Entity labels are candidate mention types, never canonical research entities.
"""
from __future__ import annotations

from typing import Any

from . import BackendUnavailable
from ..models import EntityMention, NlpDocument, Provenance, Representation

_BACKEND = "spacy"
_LOADED: dict[str, Any] = {}
_SPACY_TO_CANDIDATE_TYPE = {
    "PERSON": "person", "NORP": "group", "FAC": "facility",
    "ORG": "organization", "GPE": "place", "LOC": "place",
    "PRODUCT": "product", "EVENT": "event", "WORK_OF_ART": "work_of_art",
    "LAW": "law", "LANGUAGE": "language", "DATE": "temporal",
    "TIME": "temporal", "PERCENT": "quantity", "MONEY": "quantity",
    "QUANTITY": "quantity", "ORDINAL": "quantity", "CARDINAL": "quantity",
}


def is_available() -> bool:
    try:
        import spacy  # noqa: F401
        return True
    except ImportError:
        return False


def _load(model_name: str):
    if model_name in _LOADED:
        return _LOADED[model_name]
    if not is_available():
        raise BackendUnavailable("spaCy is not installed")
    import spacy
    try:
        nlp = spacy.load(model_name)
    except Exception as exc:
        raise BackendUnavailable(f"spaCy model {model_name!r} unavailable: {exc}") from exc
    _LOADED[model_name] = nlp
    return nlp


def analyze(
    representation: Representation,
    model_name: str | None = None,
    provenance: Provenance | None = None,
) -> NlpDocument:
    model_name = model_name or "en_core_web_sm"
    parsed = _load(model_name)(representation.text or "")
    result = NlpDocument(
        representation_id=representation.representation_id,
        sentences=[sent.text.strip() for sent in parsed.sents],
        tokens=[token.text for token in parsed],
        lemmas=[token.lemma_ for token in parsed],
        pos=[token.pos_ for token in parsed],
        dependencies=[
            {"token": token.text, "dep": token.dep_, "head": token.head.text, "head_index": token.head.i}
            for token in parsed if token.dep_ not in ("", "punct")
        ],
        language=representation.language,
        backend=_BACKEND,
        model=f"spacy:{model_name}",
        provenance_id=provenance.provenance_id if provenance else "",
    )
    for ent in parsed.ents:
        result.mentions.append(EntityMention(
            representation_id=representation.representation_id,
            surface_form=ent.text,
            spacy_label=ent.label_,
            start_offset=ent.start_char,
            end_offset=ent.end_char,
            candidate_entity_type=_SPACY_TO_CANDIDATE_TYPE.get(ent.label_, "other"),
        ))
    return result
