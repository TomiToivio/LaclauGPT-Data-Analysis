"""LaclauGPT Data Analysis.

Analysis enriches the project-wide canonical source record. Collection,
durable storage and visualization live in sibling modules; local files and
SQLite are first-class defaults and remote services are optional adapters.
"""

from .canonical import (
    SCHEMA_VERSION,
    AnalysisSection,
    CanonicalRecord,
    ContentSection,
    DiscourseObject,
    Evidence,
    ReviewSection,
    SourceSection,
)
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
    "AnalysisSection",
    "CanonicalRecord",
    "ClassificationResult",
    "ContentSection",
    "DiscourseObject",
    "EmbeddingResult",
    "EntityMention",
    "Evidence",
    "NlpDocument",
    "Provenance",
    "Representation",
    "ReviewSection",
    "SCHEMA_VERSION",
    "Settings",
    "SourceSection",
    "Topic",
    "TopicAssignment",
    "TopicModelResult",
    "load_settings",
]
