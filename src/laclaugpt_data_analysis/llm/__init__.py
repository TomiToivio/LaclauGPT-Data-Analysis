"""Provider-neutral LLM runtime: contracts, Ollama backend, routing, structured output.

Import-time contract: importing this package performs no network calls and
does not require the ``ollama`` dependency. See ``base.LLMProvider`` for the
provider boundary pipeline stages program against.
"""
from laclaugpt_data_analysis.llm.base import (
    DEFAULT_OPTIONS,
    ChatRequest,
    LLMCallProvenance,
    LLMProvider,
    LLMResponse,
    ProviderError,
    merge_options,
)
from laclaugpt_data_analysis.llm.routing import (
    CAPABILITY_ORDER,
    MODELS,
    STAGE_ROUTING,
    pick_embedding_model,
    pick_model,
    routing_table,
)
from laclaugpt_data_analysis.llm.structured_output import (
    build_structured_prompt,
    chat_structured,
    parse_structured,
    strip_code_fences,
)

__all__ = [
    "DEFAULT_OPTIONS",
    "CAPABILITY_ORDER",
    "MODELS",
    "STAGE_ROUTING",
    "ChatRequest",
    "LLMCallProvenance",
    "LLMProvider",
    "LLMResponse",
    "ProviderError",
    "build_structured_prompt",
    "chat_structured",
    "merge_options",
    "parse_structured",
    "pick_embedding_model",
    "pick_model",
    "routing_table",
    "strip_code_fences",
]