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
from .canonical_pipeline import PipelineContext, run_canonical_pipeline
from .config import Settings, load_settings
from .context_envelope import PromptEnvelope, build_prompt_envelope
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
from .reporting import DailyReport, build_daily_report

__all__ = [
    "AnalysisSection",
    "CanonicalRecord",
    "ClassificationResult",
    "ContentSection",
    "DailyReport",
    "DiscourseObject",
    "EmbeddingResult",
    "EntityMention",
    "Evidence",
    "NlpDocument",
    "PipelineContext",
    "PromptEnvelope",
    "Provenance",
    "Representation",
    "ReviewSection",
    "SCHEMA_VERSION",
    "Settings",
    "SourceSection",
    "Topic",
    "TopicAssignment",
    "TopicModelResult",
    "build_daily_report",
    "build_prompt_envelope",
    "load_settings",
    "run_canonical_pipeline",
]
