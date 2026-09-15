"""LaclauGPT Data Analysis.

This package owns analytical transformations and evidence-producing model
interfaces. Collection, durable storage and visualization live in sibling
modules. Local files and SQLite are first-class defaults; remote services are
optional adapters.
"""

from .config import Settings, load_settings
from .models import (
    ClassificationResult,
    EmbeddingResult,
    EntityMention,
    NlpDocument,
    Provenance,
    Representation,
    Topic,
    TopicAssignment,
    TopicModelResult,
)

__all__ = [
    "ClassificationResult",
    "EmbeddingResult",
    "EntityMention",
    "NlpDocument",
    "Provenance",
    "Representation",
    "Settings",
    "Topic",
    "TopicAssignment",
    "TopicModelResult",
    "load_settings",
]
