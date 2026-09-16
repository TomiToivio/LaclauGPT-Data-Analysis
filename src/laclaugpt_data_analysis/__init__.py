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
from .context_profiles import ContextProfile, available_context_profiles, load_context_profile
from .context_runtime import ContextItem, ContextSnapshot, assemble_context
from .derived_structures import (
    Geocoder,
    GeocodeResult,
    LocationEntity,
    NetworkRelation,
    TimelineEvent,
    build_visualization_projection,
    normalize_location_name,
    project_locations,
    project_network_relations,
    project_timeline_events,
)
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
from .rag import (
    Neo4jRetrievalBackend,
    NullRetrievalBackend,
    RetrievalAudit,
    RetrievalBackend,
    RetrievalContext,
    RetrievalItem,
    backend_from_settings,
)
from .rag_pipeline import run_rag_pipeline
from .reporting import DailyReport, build_daily_report
from .runtime_config import EffectiveRunConfig, compose_run_config, compose_run_config_from_files

__all__ = [
    "AnalysisSection",
    "CanonicalRecord",
    "ClassificationResult",
    "ContentSection",
    "ContextItem",
    "ContextProfile",
    "ContextSnapshot",
    "DailyReport",
    "DiscourseObject",
    "EffectiveRunConfig",
    "EmbeddingResult",
    "EntityMention",
    "Evidence",
    "GeocodeResult",
    "Geocoder",
    "LocationEntity",
    "Neo4jRetrievalBackend",
    "NetworkRelation",
    "NlpDocument",
    "NullRetrievalBackend",
    "PipelineContext",
    "PromptEnvelope",
    "Provenance",
    "Representation",
    "RetrievalAudit",
    "RetrievalBackend",
    "RetrievalContext",
    "RetrievalItem",
    "ReviewSection",
    "SCHEMA_VERSION",
    "Settings",
    "SourceSection",
    "TimelineEvent",
    "Topic",
    "TopicAssignment",
    "TopicModelResult",
    "assemble_context",
    "available_context_profiles",
    "backend_from_settings",
    "build_daily_report",
    "build_prompt_envelope",
    "build_visualization_projection",
    "compose_run_config",
    "compose_run_config_from_files",
    "load_context_profile",
    "load_settings",
    "normalize_location_name",
    "project_locations",
    "project_network_relations",
    "project_timeline_events",
    "run_canonical_pipeline",
    "run_rag_pipeline",
]
